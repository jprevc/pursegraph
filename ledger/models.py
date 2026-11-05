from urllib.parse import urlsplit

from django.conf import settings
from django.db import models, transaction
from django.utils.translation import gettext_lazy as _
from django.utils.translation import ngettext

from pursegraph import figures

from .coverage import DateRange, coverage


class Bank(models.TextChoices):
    SPARKASSE_SI = "sparkasse_si", _("Sparkasse SI")
    N26 = "n26", _("N26")
    REVOLUT = "revolut", _("Revolut")
    # An Account with no Statements, known only so that money moved to it is a Transfer.
    OTHER = "other", _("Other")


class Account(models.Model):
    name = models.CharField(_("name"), max_length=100)
    bank = models.CharField(_("bank"), max_length=20, choices=Bank.choices)
    # Several owners make a joint Account.
    owners = models.ManyToManyField(
        settings.AUTH_USER_MODEL, related_name="accounts", verbose_name=_("owners")
    )

    class Meta:
        ordering = ["name", "id"]
        verbose_name = _("account")
        verbose_name_plural = _("accounts")

    def __str__(self):
        return self.name

    @property
    def receives_statements(self) -> bool:
        return self.bank != Bank.OTHER

    def coverage(self) -> list[DateRange]:
        """The dates this Account's Statements cover, as separate date ranges. Derived, not stored."""
        return coverage(self.statements.all())


class AccountIBAN(models.Model):
    """An IBAN of an Account; several when the bank re-issued it. Each identifies exactly one Account."""

    account = models.ForeignKey(
        Account, on_delete=models.CASCADE, related_name="ibans", verbose_name=_("account")
    )
    iban = models.CharField("IBAN", max_length=34, unique=True)

    class Meta:
        verbose_name = _("account IBAN")
        verbose_name_plural = _("account IBANs")

    def __str__(self):
        return self.iban


def _statement_file_path(statement, filename):
    return f"{statement.sha256}/{filename}"


class Statement(models.Model):
    class Format(models.TextChoices):
        PDF = "pdf", "PDF"
        CSV = "csv", "CSV"

    account = models.ForeignKey(
        Account, on_delete=models.PROTECT, related_name="statements", verbose_name=_("account")
    )
    format = models.CharField(_("format"), max_length=3, choices=Format.choices)
    period_start = models.DateField(_("period start"))
    period_end = models.DateField(_("period end"))
    opening_balance = models.DecimalField(_("opening balance"), max_digits=12, decimal_places=2)
    closing_balance = models.DecimalField(_("closing balance"), max_digits=12, decimal_places=2)
    imported_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="+",
        verbose_name=_("imported by"),
    )
    imported_at = models.DateTimeField(_("imported at"), auto_now_add=True)
    # Catches an exact re-upload of the same file.
    sha256 = models.CharField("SHA-256", max_length=64, unique=True)
    # The original file, kept so it can be re-parsed after a parser fix.
    file = models.FileField(_("file"), upload_to=_statement_file_path, max_length=255)

    class Meta:
        ordering = ["period_start", "id"]
        verbose_name = _("statement")
        verbose_name_plural = _("statements")

    def __str__(self):
        return f"{self.account} {self.period_start}–{self.period_end}"

    def can_be_deleted_by(self, member) -> bool:
        return member.is_admin or member.pk == self.imported_by_id

    def own_transactions(self) -> "TransactionQuerySet":
        """The Transactions that appear on this Statement only, and go when it is deleted."""
        on_other_statements = Transaction.statements.through.objects.exclude(statement=self)
        return self.transactions.exclude(pk__in=on_other_statements.values("transaction"))

    def lost_manual_outcome_count(self) -> int:
        """How many of the Transactions deleting this Statement would delete have a manual outcome."""
        return self.own_transactions().filter(source=Source.MANUAL).count()

    def delete_with_transactions(self) -> None:
        """Deletes this Statement, its own Transactions and its stored file; the Account's Coverage shrinks with it.

        A paired Transfer side that survives loses its counterpart and stays a one-sided Transfer.
        """
        with transaction.atomic():
            # Serialized with imports into the Account, whose Duplicate check reads these Transactions.
            Account.objects.select_for_update().get(pk=self.account_id)
            self.own_transactions().delete()  # the counterpart link is SET_NULL
            self.delete()
            # Only once the rows are gone for good; a rollback keeps the file.
            transaction.on_commit(lambda: self.file.delete(save=False))


class Source(models.TextChoices):
    RULE = "rule", _("Rule")
    CATEGORIZER = "categorizer", _("Categorizer")
    MANUAL = "manual", _("Manual")
    IBAN = "iban", _("IBAN")
    PAIRING = "pairing", _("Pairing")
    # Set by the parser itself, such as a bank fee row.
    PARSER = "parser", _("Parser")


SOURCE_CAPTIONS = {
    Source.RULE: _("by Rule"),
    Source.CATEGORIZER: _("by Categorizer"),
    Source.MANUAL: _("by hand"),
    Source.IBAN: _("by IBAN"),
    Source.PAIRING: _("paired"),
    Source.PARSER: _("by import"),
}


# Neither a Subcategory, a Transfer nor a Split: the Transactions waiting for an outcome.
UNRESOLVED = models.Q(subcategory__isnull=True, is_transfer=False, is_split=False)


def counts_in(subcategories: models.Q) -> models.Q:
    """The Transactions with money counted in `subcategories`: an unsplit one whose Subcategory is among them, a
    Split with a Part whose Subcategory is. `subcategories` is a condition on `subcategory`, which a Transaction and
    a Part both have, such as Q(subcategory__category=3)."""
    return models.Q(subcategories, is_split=False) | models.Q(
        models.Exists(Part.objects.filter(subcategories, transaction=models.OuterRef("pk")))
    )


class TransactionQuerySet(models.QuerySet):
    def unresolved(self):
        """Neither a Subcategory, a Transfer nor a Split."""
        return self.filter(UNRESOLVED)

    def in_review_queue(self):
        """The Review queue: the unresolved ones, and the Transfer sides with several possible counterparts."""
        return self.unresolved() | self.filter(ambiguous_pairing=True)

    def with_counted(self, subcategories: models.Q | None = None) -> "TransactionQuerySet":
        """Each with `counted`, the money it counts in `subcategories` (see `counts_in`), and its Parts, each with
        `counted`, whether it is one of those. An unsplit Transaction counts its whole amount; without
        `subcategories`, a Split counts every Part."""
        if subcategories is None:
            counted: models.F | models.Expression = models.F("amount")
            part_counted: models.Expression = models.Value(True)
        else:
            counted = models.Case(
                models.When(
                    is_split=True,
                    then=models.Subquery(
                        Part.objects.filter(subcategories, transaction=models.OuterRef("pk"))
                        .values("transaction")
                        .annotate(total=models.Sum("amount"))
                        .values("total")
                    ),
                ),
                default=models.F("amount"),
            )
            part_counted = models.ExpressionWrapper(
                subcategories, output_field=models.BooleanField()
            )
        return self.annotate(counted=counted).prefetch_related(
            models.Prefetch(
                "parts",
                Part.objects.select_related("subcategory__category").annotate(counted=part_counted),
            )
        )


class Transaction(models.Model):
    account = models.ForeignKey(
        Account, on_delete=models.PROTECT, related_name="transactions", verbose_name=_("account")
    )
    # The booking date: the day the bank applied it to the balance.
    date = models.DateField(_("date"))
    # Negative = out. Fee-free: a bank fee is a Transaction of its own.
    amount = models.DecimalField(_("amount"), max_digits=12, decimal_places=2)
    description = models.TextField(_("description"))
    counterparty_name = models.CharField(_("counterparty"), max_length=200, blank=True)
    counterparty_iban = models.CharField(_("counterparty IBAN"), max_length=34, blank=True)
    reference = models.CharField(_("reference"), max_length=200, blank=True)
    running_balance = models.DecimalField(
        _("running balance"), max_digits=12, decimal_places=2, null=True, blank=True
    )
    # A bank fee the parser split off its payment.
    is_fee = models.BooleanField(_("bank fee"), default=False)
    # Everything the parser saw for this row.
    raw = models.JSONField(_("raw"), default=dict)
    statements = models.ManyToManyField(
        Statement, related_name="transactions", verbose_name=_("statements")
    )

    # The outcome: a Subcategory, a Transfer or a Split into Parts, at most one; none means unresolved.
    subcategory = models.ForeignKey(
        "Subcategory",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="transactions",
        verbose_name=_("subcategory"),
    )
    is_transfer = models.BooleanField(_("transfer"), default=False)
    # Its Parts hold the outcome. Only a Member splits a Transaction, so `source` is MANUAL.
    is_split = models.BooleanField(_("split"), default=False)
    # The other side of a paired Transfer.
    counterpart = models.OneToOneField(
        "self",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        verbose_name=_("counterpart"),
    )
    # An unpaired Transfer side with several equally close candidates, waiting for a Member to pick one.
    ambiguous_pairing = models.BooleanField(_("ambiguous pairing"), default=False)
    # What set the outcome; blank while unresolved. Automatic processing never overwrites MANUAL.
    source = models.CharField(_("source"), max_length=20, choices=Source.choices, blank=True)
    # The Rule that set the outcome, while `source` is RULE.
    rule = models.ForeignKey(
        "Rule",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="transactions",
        verbose_name=_("rule"),
    )
    # A Categorizer's Suggestion, kept apart from the outcome. One is waited for while both are None;
    # confidence 0 with no Subcategory means the Categorizer had none.
    suggested_subcategory = models.ForeignKey(
        "Subcategory",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
        verbose_name=_("suggested subcategory"),
    )
    # The Categorizer's own probability of `suggested_subcategory`, from 0 to 1.
    confidence = models.FloatField(_("confidence"), null=True, blank=True)

    objects = TransactionQuerySet.as_manager()

    class Meta:
        ordering = ["date", "id"]
        constraints = [
            models.CheckConstraint(
                condition=~models.Q(subcategory__isnull=False, is_transfer=True)
                & ~models.Q(subcategory__isnull=False, is_split=True)
                & ~models.Q(is_transfer=True, is_split=True),
                name="one_outcome",
            ),
        ]
        verbose_name = _("transaction")
        verbose_name_plural = _("transactions")

    def __str__(self):
        return f"{self.date} {self.amount} {self.description}"

    @property
    def is_unresolved(self) -> bool:
        return self.subcategory_id is None and not self.is_transfer and not self.is_split

    @property
    def pending_suggestion_id(self) -> int | None:
        """The suggested Subcategory's id while the Transaction is unresolved, to preselect in the Review queue."""
        return self.suggested_subcategory_id if self.is_unresolved else None

    @property
    def outcome_label(self) -> str:
        """The outcome in words, as the Transaction row names it: "Category › Subcategory", "Transfer", "Split: Food ›
        Groceries 50,00 €, Home › Furniture & household 30,00 €" or "Awaiting review"."""
        if self.is_split:
            parts = ", ".join(
                f"{p.subcategory.category.name} › {p.subcategory.name} {figures.money(abs(p.amount))}"
                for p in self.parts.select_related("subcategory__category")
            )
            return _("Split: %(parts)s") % {"parts": parts}
        if self.subcategory_id:
            assert self.subcategory is not None
            return f"{self.subcategory.category.name} › {self.subcategory.name}"
        return str(_("Transfer") if self.is_transfer else _("Awaiting review"))

    @property
    def outcome_saved(self) -> str:
        """The outcome as the line saying it was saved names it: "a Split into 2 Parts", or else `outcome_label`."""
        if self.is_split:
            count = len(self.parts.all())
            return ngettext(
                "a Split into %(count)d Part", "a Split into %(count)d Parts", count
            ) % {"count": count}
        return self.outcome_label

    @property
    def shown_parts(self) -> list[tuple["Part", str]]:
        """A Split's Parts as its Part rows show them, each with "em" or "dim" when only some count where the rows are
        listed (`TransactionQuerySet.with_counted`), else ""."""
        parts = list(self.parts.all())
        counted = [getattr(p, "counted", True) for p in parts]
        if all(counted):
            return [(p, "") for p in parts]
        return [(p, "em" if c else "dim") for p, c in zip(parts, counted, strict=True)]

    @property
    def source_caption(self) -> str:
        """What set the outcome, as the row's muted caption ("by Rule"); "" while unresolved."""
        return str(SOURCE_CAPTIONS[Source(self.source)]) if self.source else ""

    @property
    def source_reason(self) -> str:
        """Why the outcome is what it is, specifically, as the source caption's hover title: "Matched the Rule
        “HOFER” → Food › Groceries"; "" while unresolved."""
        if self.source == Source.RULE:
            if self.rule is None:
                return str(_("A Rule matched it; the Rule has since been deleted."))
            return _("Matched the Rule “%(rule)s” → %(outcome)s") % {
                "rule": self.rule,
                "outcome": self.outcome_label,
            }
        if self.source == Source.CATEGORIZER:
            if self.confidence is None:
                return str(_("A Categorizer suggested it."))
            return _("A Categorizer suggested it, %(percent)s sure.") % {
                "percent": figures.share(self.confidence)
            }
        if self.source == Source.IBAN:
            return _("Its counterparty IBAN, %(iban)s, is one of the Household's.") % {
                "iban": self.counterparty_iban
            }
        if self.source == Source.PAIRING:
            if self.counterpart is None:
                return str(_("Paired with its other side in another of the Household's Accounts."))
            return _("Paired with the other side in %(account)s on %(day)s.") % {
                "account": self.counterpart.account.name,
                "day": figures.day(self.counterpart.date),
            }
        if self.source == Source.MANUAL:
            return str(_("A Member chose it."))
        if self.source == Source.PARSER:
            return str(_("The bank's Statement listed it as a bank fee."))
        return ""

    def pairing_candidates(self) -> list["Transaction"]:
        """For an ambiguous pairing, the Transactions equally close to being its other side."""
        from .transfers import closest_candidates

        return closest_candidates(self) if self.ambiguous_pairing else []

    def set_outcome(
        self, subcategory: "Subcategory | None", *, source: str, rule: "Rule | None" = None
    ) -> None:
        """Sets the outcome to `subcategory`, or to Transfer when it is None. Leaving Transfer unpairs both sides;
        a Split's Parts go.

        Any change settles an ambiguous pairing: the Transaction stays as it is now set.

        `rule` is the Rule that set it; any other change, such as a manual one, clears the link."""
        if self.is_split:
            self.parts.all().delete()
        self.subcategory = subcategory
        self.is_transfer = subcategory is None
        self.is_split = False
        self.source = source
        self.rule = rule
        self.ambiguous_pairing = False
        if not self.is_transfer and self.counterpart_id:
            Transaction.objects.filter(pk=self.counterpart_id).update(counterpart=None)
            self.counterpart = None
        self.save(
            update_fields=[
                "subcategory",
                "is_transfer",
                "is_split",
                "source",
                "rule",
                "counterpart",
                "ambiguous_pairing",
            ]
        )


class Category(models.Model):
    class Kind(models.TextChoices):
        SPENDING = "spending", _("Spending")
        INCOME = "income", _("Income")

    name = models.CharField(_("name"), max_length=100)
    kind = models.CharField(_("kind"), max_length=10, choices=Kind.choices)
    # Display order, lowest first.
    position = models.PositiveIntegerField(_("position"), default=0)

    class Meta:
        ordering = ["position", "id"]
        verbose_name = _("category")
        verbose_name_plural = _("categories")

    def __str__(self):
        return self.name


class Subcategory(models.Model):
    """A Transaction's Category, one level down. Every Category has exactly one catch-all."""

    category = models.ForeignKey(
        Category, on_delete=models.CASCADE, related_name="subcategories", verbose_name=_("category")
    )
    name = models.CharField(_("name"), max_length=100)
    # Takes the Transactions of a deleted sibling; can't be deleted itself.
    is_catch_all = models.BooleanField(_("catch-all"), default=False)
    # Bank fees split off their payment by the parsers are categorized here at import, whatever its name.
    is_bank_fees = models.BooleanField(_("bank fees"), default=False)
    position = models.PositiveIntegerField(_("position"), default=0)

    class Meta:
        # The catch-all is always listed last.
        ordering = ["is_catch_all", "position", "id"]
        constraints = [
            models.UniqueConstraint(
                fields=["category"],
                condition=models.Q(is_catch_all=True),
                name="one_catch_all_per_category",
            ),
            models.UniqueConstraint(
                fields=["is_bank_fees"],
                condition=models.Q(is_bank_fees=True),
                name="one_bank_fees_subcategory",
            ),
        ]
        verbose_name = _("subcategory")
        verbose_name_plural = _("subcategories")

    def __str__(self):
        return f"{self.category} → {self.name}"


class Part(models.Model):
    """One piece of a Split: an exact amount of its Transaction placed in one Subcategory. A Split's Parts are at
    least two, in different Subcategories of one kind, each in the Transaction's direction, and add up to its amount
    (`ledger.outcomes.split`)."""

    transaction = models.ForeignKey(
        Transaction, on_delete=models.CASCADE, related_name="parts", verbose_name=_("transaction")
    )
    subcategory = models.ForeignKey(
        Subcategory, on_delete=models.PROTECT, related_name="parts", verbose_name=_("subcategory")
    )
    # Signed like its Transaction's amount.
    amount = models.DecimalField(_("amount"), max_digits=12, decimal_places=2)

    class Meta:
        # The order the Member gave them in.
        ordering = ["id"]
        constraints = [
            models.UniqueConstraint(
                fields=["transaction", "subcategory"], name="one_part_per_subcategory"
            ),
            models.CheckConstraint(condition=~models.Q(amount=0), name="part_not_zero"),
        ]
        verbose_name = _("part")
        verbose_name_plural = _("parts")

    def __str__(self):
        return f"{self.subcategory} {self.amount}"


class Setting(models.Model):
    """An installation-wide value. There is no Household table: the installation is the Household."""

    # A Suggestion at least this confident sets the outcome by itself.
    AUTO_ACCEPT_THRESHOLD = "auto_accept_threshold"

    DEFAULTS = {
        AUTO_ACCEPT_THRESHOLD: "0.90",
    }

    key = models.CharField(_("key"), max_length=50, primary_key=True)
    value = models.CharField(_("value"), max_length=200, blank=True)

    class Meta:
        verbose_name = _("setting")
        verbose_name_plural = _("settings")

    def __str__(self):
        return f"{self.key} = {self.value}"

    @classmethod
    def get(cls, key: str) -> str:
        setting = cls.objects.filter(key=key).first()
        return setting.value if setting else cls.DEFAULTS[key]

    @classmethod
    def put(cls, key: str, value: str) -> None:
        cls.objects.update_or_create(key=key, defaults={"value": value})


class Rule(models.Model):
    """Categorizes matching Transactions at import. The first match in `position` order wins.

    Every condition that is set must hold; at least one is set."""

    class Direction(models.TextChoices):
        IN = "in", _("In")
        OUT = "out", _("Out")

    DESCRIPTION_LENGTH = 200

    # Case- and accent-insensitive.
    description_contains = models.CharField(
        _("description contains"), max_length=DESCRIPTION_LENGTH, blank=True
    )
    # Stored without spaces, in capitals, like the parsers' IBANs.
    counterparty_iban = models.CharField(_("counterparty IBAN"), max_length=34, blank=True)
    direction = models.CharField(
        _("direction"), max_length=3, choices=Direction.choices, blank=True
    )
    account = models.ForeignKey(
        Account,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="rules",
        verbose_name=_("account"),
    )
    # The outcome: a Subcategory, or Transfer when None.
    subcategory = models.ForeignKey(
        Subcategory,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="rules",
        verbose_name=_("subcategory"),
    )
    # Lowest first; the first matching Rule wins.
    position = models.IntegerField(_("position"), default=0)

    class Meta:
        ordering = ["position", "id"]
        verbose_name = _("rule")
        verbose_name_plural = _("rules")

    def __str__(self):
        return self.description_contains or self.counterparty_iban or str(self.pk)

    def condition(self) -> models.Q:
        """The Transactions this Rule matches."""
        q = models.Q()
        if self.description_contains:
            q &= models.Q(description__unaccent__icontains=self.description_contains)
        if self.counterparty_iban:
            q &= models.Q(counterparty_iban=self.counterparty_iban)
        if self.direction == self.Direction.IN:
            q &= models.Q(amount__gt=0)
        elif self.direction == self.Direction.OUT:
            q &= models.Q(amount__lt=0)
        if self.account_id:
            q &= models.Q(account_id=self.account_id)
        return q

    @property
    def outcome_label(self) -> str:
        """Its outcome in words, as the Transaction row names one: "Category › Subcategory" or "Transfer"."""
        if self.subcategory_id:
            assert self.subcategory is not None
            return f"{self.subcategory.category.name} › {self.subcategory.name}"
        return str(_("Transfer"))

    @property
    def iban_grouped(self) -> str:
        """Its counterparty IBAN in groups of four, as people read one."""
        from .parsers.iban import grouped_iban

        return grouped_iban(self.counterparty_iban)

    @property
    def name(self) -> str:
        """What the Rules page calls it: its description text in quotes, else its IBAN, else its other conditions."""
        if self.description_contains:
            return f"“{self.description_contains}”"
        if self.counterparty_iban:
            return self.iban_grouped
        on = self.account.name if self.account_id and self.account else ""
        if self.direction == self.Direction.IN:
            return _("Money in on %(account)s") % {"account": on} if on else str(_("Money in"))
        if self.direction == self.Direction.OUT:
            return _("Money out on %(account)s") % {"account": on} if on else str(_("Money out"))
        return _("Anything on %(account)s") % {"account": on}


class ApiToken(models.Model):
    """What one program outside Pursegraph, such as a Categorizer, authenticates with to its API (ledger/api.py).
    So far it can only fetch the Transactions waiting for a Suggestion and send Suggestions back; it can't log in.
    Only a hash of the secret is stored; the admin sees the secret once."""

    name = models.CharField(_("name"), max_length=100)
    # SHA-256 of the secret, in hex.
    digest = models.CharField(_("digest"), max_length=64, unique=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name="+",
        verbose_name=_("created by"),
    )
    created_at = models.DateTimeField(_("created at"), auto_now_add=True)
    # Any call made with it.
    last_used_at = models.DateTimeField(_("last used at"), null=True, blank=True)
    # The last Suggestion, or "no suggestion", it sent that was stored.
    last_suggestion_at = models.DateTimeField(_("last suggestion at"), null=True, blank=True)
    # Kept once revoked, so the Suggestions page can still name it as the sender of the last Suggestion.
    revoked_at = models.DateTimeField(_("revoked at"), null=True, blank=True)

    class Meta:
        ordering = ["name", "id"]
        verbose_name = _("API token")
        verbose_name_plural = _("API tokens")

    def __str__(self):
        return self.name


class Webhook(models.Model):
    """A URL Pursegraph POSTs to when an action leaves Transactions waiting for a Suggestion, so whatever listens there
    knows to fetch them (ledger/webhooks.py). The URL holds the receiver's secret, so pages show it masked."""

    class Outcome(models.TextChoices):
        DELIVERED = "delivered", _("delivered")
        HTTP_ERROR = "http_error", _("HTTP error")
        TIMED_OUT = "timed_out", _("timed out")
        UNREACHABLE = "unreachable", _("couldn't connect")

    name = models.CharField(_("name"), max_length=100)
    url = models.CharField(_("URL"), max_length=2000)
    created_at = models.DateTimeField(_("created at"), auto_now_add=True)
    # Only the latest attempt is kept: when, how it went, and the reply's status code for an HTTP error.
    last_attempt_at = models.DateTimeField(_("last attempt at"), null=True, blank=True)
    last_outcome = models.CharField(
        _("last outcome"), max_length=20, choices=Outcome.choices, blank=True
    )
    last_status = models.PositiveSmallIntegerField(_("last status"), null=True, blank=True)

    class Meta:
        ordering = ["name", "id"]
        verbose_name = _("Webhook")
        verbose_name_plural = _("Webhooks")

    def __str__(self):
        return self.name

    @property
    def delivered(self) -> bool:
        return self.last_outcome == self.Outcome.DELIVERED

    @property
    def failure(self) -> str:
        """Why its latest attempt failed, as the API & Webhooks page says it: "HTTP 500", "timed out" or "couldn't
        connect"; "" if it was delivered or never made."""
        if self.last_outcome == self.Outcome.HTTP_ERROR:
            return f"HTTP {self.last_status}"
        return "" if self.delivered else self.get_last_outcome_display()

    @property
    def masked_url(self) -> str:
        """Its URL with only the scheme, host and port shown, as the rest may hold the receiver's secret:
        "https://ha.example:8123/••••"."""
        parts = urlsplit(self.url)
        host = f"[{parts.hostname}]" if ":" in (parts.hostname or "") else parts.hostname
        origin = f"{parts.scheme}://{host}" + (f":{parts.port}" if parts.port else "")
        hidden = parts.path.strip("/") or parts.query or parts.fragment
        return origin + ("/••••" if hidden else "/")
