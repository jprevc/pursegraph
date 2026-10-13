from django.conf import settings
from django.db import models
from django.utils.translation import gettext_lazy as _


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
    owners = models.ManyToManyField(settings.AUTH_USER_MODEL, related_name="accounts", verbose_name=_("owners"))

    class Meta:
        ordering = ["name", "id"]
        verbose_name = _("account")
        verbose_name_plural = _("accounts")

    def __str__(self):
        return self.name


class AccountIBAN(models.Model):
    """An IBAN of an Account; several when the bank re-issued it. Each identifies exactly one Account."""

    account = models.ForeignKey(Account, on_delete=models.CASCADE, related_name="ibans", verbose_name=_("account"))
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

    account = models.ForeignKey(Account, on_delete=models.PROTECT, related_name="statements", verbose_name=_("account"))
    format = models.CharField(_("format"), max_length=3, choices=Format.choices)
    period_start = models.DateField(_("period start"))
    period_end = models.DateField(_("period end"))
    opening_balance = models.DecimalField(_("opening balance"), max_digits=12, decimal_places=2)
    closing_balance = models.DecimalField(_("closing balance"), max_digits=12, decimal_places=2)
    imported_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="+", verbose_name=_("imported by")
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


class Transaction(models.Model):
    account = models.ForeignKey(Account, on_delete=models.PROTECT, related_name="transactions", verbose_name=_("account"))
    # The booking date: the day the bank applied it to the balance.
    date = models.DateField(_("date"))
    # Negative = out. Fee-free: a bank fee is a Transaction of its own.
    amount = models.DecimalField(_("amount"), max_digits=12, decimal_places=2)
    description = models.TextField(_("description"))
    counterparty_name = models.CharField(_("counterparty"), max_length=200, blank=True)
    counterparty_iban = models.CharField(_("counterparty IBAN"), max_length=34, blank=True)
    reference = models.CharField(_("reference"), max_length=200, blank=True)
    running_balance = models.DecimalField(_("running balance"), max_digits=12, decimal_places=2, null=True, blank=True)
    # Everything the parser saw for this row.
    raw = models.JSONField(_("raw"), default=dict)
    statements = models.ManyToManyField(Statement, related_name="transactions", verbose_name=_("statements"))

    class Meta:
        ordering = ["date", "id"]
        verbose_name = _("transaction")
        verbose_name_plural = _("transactions")

    def __str__(self):
        return f"{self.date} {self.amount} {self.description}"
