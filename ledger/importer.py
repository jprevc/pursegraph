"""The import pipeline: one Statement file in, committed Statement and Transactions out.

It runs in two calls, because the Account may have to be asked for after parsing:

- `check_statement`: sha256 re-import check, parse, balance check, printed totals check, then
  Account detection from the Statement's own IBAN;
- `commit_statement`: into the detected Account, or one the Member picked or creates (whom it
  then belongs to), stores the Statement, its Transactions and the original file.

Any failure raises ImportRejected and stores nothing.
"""

import hashlib
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from pathlib import PurePath

from django.core.files.base import ContentFile
from django.db import IntegrityError, transaction
from django.utils.translation import gettext as _

from .models import Account, AccountIBAN, Bank, Source, Statement, Subcategory, Transaction
from .parsers import ParsedRow, ParsedStatement, ParseError, Totals, parse


@dataclass(frozen=True)
class NewAccount:
    """An Account to create during the import; the importing Member becomes its owner."""

    name: str


@dataclass(frozen=True)
class Diagnosis:
    """Why a Statement's numbers didn't add up: its balances and printed totals against its rows."""

    opening_balance: Decimal
    rows_total: Decimal
    closing_balance: Decimal
    rows: list[ParsedRow]
    printed_totals: Totals | None
    parsed_totals: Totals


class ImportRejected(Exception):
    """The Statement was not imported.

    `keep_file` asks the Member to keep the file because a parser fix needs it; `diagnosis` is
    set when the numbers didn't add up.
    """

    def __init__(
        self, message: str, *, keep_file: bool = False, diagnosis: Diagnosis | None = None
    ):
        super().__init__(message)
        self.keep_file = keep_file or diagnosis is not None
        self.diagnosis = diagnosis


@dataclass(frozen=True)
class CheckedStatement:
    """A parsed Statement that passed every check, waiting to be committed into an Account."""

    content: bytes
    filename: str
    sha256: str
    format: str
    parsed: ParsedStatement
    account: Account | None
    """The Account detected from the Statement's IBAN, if any."""


@dataclass(frozen=True)
class ImportSummary:
    account: Account
    period_start: date
    period_end: date
    imported_count: int
    skipped_count: int


def check_statement(*, content: bytes, filename: str) -> CheckedStatement:
    sha256 = hashlib.sha256(content).hexdigest()
    existing = Statement.objects.filter(sha256=sha256).select_related("account").first()
    if existing:
        raise ImportRejected(
            _("This Statement was already imported on %(date)s, into %(account)s.")
            % {"date": existing.imported_at.date(), "account": existing.account}
        )

    format = PurePath(filename).suffix.lower().removeprefix(".")
    if format not in Statement.Format.values:
        raise ImportRejected(_("Only PDF and CSV Statements can be imported."))
    try:
        parsed = parse(content, format)
    except ParseError as error:
        raise ImportRejected(str(error), keep_file=True) from error

    rows_total = sum((row.amount for row in parsed.rows), Decimal(0))
    parsed_totals = _totals(parsed.rows)
    balances_add_up = parsed.opening_balance + rows_total == parsed.closing_balance
    if not balances_add_up or parsed.printed_totals not in (None, parsed_totals):
        raise ImportRejected(
            _("The Statement's balances don't add up, so it was not imported.")
            if not balances_add_up
            else _("The Statement's rows don't match its printed totals, so it was not imported."),
            diagnosis=Diagnosis(
                parsed.opening_balance,
                rows_total,
                parsed.closing_balance,
                parsed.rows,
                parsed.printed_totals,
                parsed_totals,
            ),
        )

    known = (
        AccountIBAN.objects.filter(iban=parsed.iban).select_related("account").first()
        if parsed.iban
        else None
    )
    return CheckedStatement(
        content, filename, sha256, format, parsed, known.account if known else None
    )


def commit_statement(
    checked: CheckedStatement, *, member, account: Account | NewAccount
) -> ImportSummary:
    parsed = checked.parsed
    if isinstance(account, Account) and account.bank != parsed.bank:
        raise ImportRejected(
            _(
                "This is a %(statement_bank)s Statement, but %(account)s is a %(account_bank)s Account."
            )
            % {
                "statement_bank": Bank(parsed.bank).label,
                "account": account,
                "account_bank": account.get_bank_display(),
            }
        )
    if checked.account and account != checked.account:
        raise ImportRejected(
            _("This Statement's IBAN %(iban)s belongs to %(account)s.")
            % {"iban": parsed.iban, "account": checked.account}
        )

    # Found by name: if an admin renamed or deleted it, fees wait in the Review queue instead.
    bank_fees = Subcategory.objects.filter(category__name="Finance", name="Bank fees").first()
    with transaction.atomic():
        if isinstance(account, NewAccount):
            account = Account.objects.create(name=account.name, bank=parsed.bank)
            account.owners.add(member)
        statement = Statement(
            account=account,
            format=checked.format,
            period_start=parsed.period_start,
            period_end=parsed.period_end,
            opening_balance=parsed.opening_balance,
            closing_balance=parsed.closing_balance,
            imported_by=member,
            sha256=checked.sha256,
        )
        statement.file.save(
            PurePath(checked.filename).name, ContentFile(checked.content), save=False
        )
        try:
            if parsed.iban and not checked.account:
                # An unknown IBAN now identifies the Account it was imported into.
                AccountIBAN.objects.create(account=account, iban=parsed.iban)
            statement.save()
            transactions = Transaction.objects.bulk_create(
                Transaction(
                    account=account,
                    date=row.date,
                    amount=row.amount,
                    description=row.description,
                    counterparty_name=row.counterparty_name,
                    counterparty_iban=row.counterparty_iban,
                    reference=row.reference,
                    running_balance=row.running_balance,
                    raw=row.raw,
                    **(
                        {"subcategory": bank_fees, "source": Source.PARSER}
                        if row.is_fee and bank_fees
                        else {}
                    ),
                )
                for row in parsed.rows
            )
            statement.transactions.add(*transactions)
        except IntegrityError as err:
            # The same file (or another Statement of this IBAN) was imported concurrently, after the checks.
            statement.file.delete(save=False)
            raise ImportRejected(_("This Statement was already imported.")) from err
        except BaseException:
            statement.file.delete(save=False)
            raise

    return ImportSummary(
        account, parsed.period_start, parsed.period_end, len(transactions), parsed.skipped_count
    )


def _totals(rows: list[ParsedRow]) -> Totals:
    """The parsed rows' money in/out and counts, to compare with the printed ones."""
    money_in = [row.amount for row in rows if row.amount > 0]
    money_out = [-row.amount for row in rows if row.amount < 0]
    return Totals(
        sum(money_in, Decimal(0)), sum(money_out, Decimal(0)), len(money_in), len(money_out)
    )
