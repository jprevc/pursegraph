from django.conf import settings
from django.db import models, transaction
from django.utils.translation import gettext_lazy as _

from .coverage import DateRange, Segment, coverage, timeline


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

    def coverage_timeline(self) -> list[Segment]:
        """The Coverage as covered stretches with the gaps between them, for the Import page."""
        return timeline(self.coverage())


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
    LLM = "llm", _("LLM")
    MANUAL = "manual", _("Manual")
    IBAN = "iban", _("IBAN")
    PAIRING = "pairing", _("Pairing")
    # Set by the parser itself, such as a bank fee row.
    PARSER = "parser", _("Parser")


SOURCE_CAPTIONS = {
    Source.RULE: _("by Rule"),
    Source.LLM: _("by LLM"),
    Source.MANUAL: _("by hand"),
    Source.IBAN: _("by IBAN"),
    Source.PAIRING: _("paired"),
    Source.PARSER: _("by import"),
}


class TransactionQuerySet(models.QuerySet):
    def unresolved(self):
        """Neither a Subcategory nor a Transfer."""
        return self.filter(subcategory__isnull=True, is_transfer=False)

    def in_review_queue(self):
        """The Review queue: the unresolved ones, and the Transfer sides with several possible counterparts."""
        return self.unresolved() | self.filter(ambiguous_pairing=True)


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

    # The outcome: a Subcategory or a Transfer, never both; neither means unresolved.
    subcategory = models.ForeignKey(
        "Subcategory",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="transactions",
        verbose_name=_("subcategory"),
    )
    is_transfer = models.BooleanField(_("transfer"), default=False)
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
    source = models.CharField(_("source"), max_length=10, choices=Source.choices, blank=True)
    # The Rule that set the outcome, while `source` is RULE.
    rule = models.ForeignKey(
        "Rule",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="transactions",
        verbose_name=_("rule"),
    )
    # The local LLM's suggestion, kept apart from the outcome. The worker asks for one while both are None;
    # confidence 0 with no Subcategory means the LLM's answer was unusable.
    suggested_subcategory = models.ForeignKey(
        "Subcategory",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
        verbose_name=_("suggested subcategory"),
    )
    # The LLM's own probability of `suggested_subcategory`, from 0 to 1.
    confidence = models.FloatField(_("confidence"), null=True, blank=True)

    objects = TransactionQuerySet.as_manager()

    class Meta:
        ordering = ["date", "id"]
        constraints = [
            models.CheckConstraint(
                condition=~models.Q(subcategory__isnull=False, is_transfer=True),
                name="subcategory_or_transfer",
            ),
        ]
        verbose_name = _("transaction")
        verbose_name_plural = _("transactions")

    def __str__(self):
        return f"{self.date} {self.amount} {self.description}"

    @property
    def is_unresolved(self) -> bool:
        return self.subcategory_id is None and not self.is_transfer

    @property
    def pending_suggestion_id(self) -> int | None:
        """The suggested Subcategory's id while the Transaction is unresolved, to preselect in the Review queue."""
        return self.suggested_subcategory_id if self.is_unresolved else None

    @property
    def outcome_label(self) -> str:
        """The outcome in words, as the Transaction row names it: "Category › Subcategory", "Transfer" or
        "Awaiting review"."""
        if self.subcategory_id:
            assert self.subcategory is not None
            return f"{self.subcategory.category.name} › {self.subcategory.name}"
        return str(_("Transfer") if self.is_transfer else _("Awaiting review"))

    @property
    def source_caption(self) -> str:
        """What set the outcome, as the row's muted caption ("by Rule"); "" while unresolved."""
        return str(SOURCE_CAPTIONS[Source(self.source)]) if self.source else ""

    def pairing_candidates(self) -> list["Transaction"]:
        """For an ambiguous pairing, the Transactions equally close to being its other side."""
        from .transfers import closest_candidates

        return closest_candidates(self) if self.ambiguous_pairing else []

    def set_outcome(
        self, subcategory: "Subcategory | None", *, source: str, rule: "Rule | None" = None
    ) -> None:
        """Sets the outcome to `subcategory`, or to Transfer when it is None. Leaving Transfer unpairs both sides.

        Any change settles an ambiguous pairing: the Transaction stays as it is now set.

        `rule` is the Rule that set it; any other change, such as a manual one, clears the link."""
        self.subcategory = subcategory
        self.is_transfer = subcategory is None
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


class Setting(models.Model):
    """An installation-wide value. There is no Household table: the installation is the Household."""

    # An LLM suggestion at least this confident sets the outcome by itself.
    AUTO_ACCEPT_THRESHOLD = "auto_accept_threshold"
    # "1" while the last call to the LLM failed.
    SUGGESTIONS_UNAVAILABLE = "suggestions_unavailable"

    DEFAULTS = {AUTO_ACCEPT_THRESHOLD: "0.90", SUGGESTIONS_UNAVAILABLE: ""}

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
