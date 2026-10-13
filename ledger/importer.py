"""The import pipeline: one Statement file in, committed Statement and Transactions out.

Steps, for one file: sha256 re-import check, parse, balance check, Account resolution,
then commit (Statement, Transactions and the original file). Any failure raises
ImportRejected and stores nothing.
"""

import hashlib
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from pathlib import PurePath

from django.core.files.base import ContentFile
from django.db import IntegrityError, transaction
from django.utils.translation import gettext as _

from .models import Account, Bank, Statement, Transaction
from .parsers import ParsedRow, ParseError, parse


@dataclass(frozen=True)
class NewAccount:
    """An Account to create during the import; the importing Member becomes its owner."""

    name: str


@dataclass(frozen=True)
class BalanceDiagnosis:
    opening_balance: Decimal
    rows_total: Decimal
    closing_balance: Decimal
    rows: list[ParsedRow]


class ImportRejected(Exception):
    """The Statement was not imported.

    `keep_file` asks the Member to keep the file because a parser fix needs it; `diagnosis` is
    set when the balances didn't add up.
    """

    def __init__(self, message: str, *, keep_file: bool = False, diagnosis: BalanceDiagnosis | None = None):
        super().__init__(message)
        self.keep_file = keep_file or diagnosis is not None
        self.diagnosis = diagnosis


@dataclass(frozen=True)
class ImportSummary:
    account: Account
    period_start: date
    period_end: date
    imported_count: int
    skipped_count: int


def import_statement(*, content: bytes, filename: str, member, account: Account | NewAccount) -> ImportSummary:
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
        raise ImportRejected(str(error), keep_file=True)

    rows_total = sum((row.amount for row in parsed.rows), Decimal(0))
    if parsed.opening_balance + rows_total != parsed.closing_balance:
        raise ImportRejected(
            _("The Statement's balances don't add up, so it was not imported."),
            diagnosis=BalanceDiagnosis(parsed.opening_balance, rows_total, parsed.closing_balance, parsed.rows),
        )

    if isinstance(account, Account) and account.bank != parsed.bank:
        raise ImportRejected(
            _("This is a %(statement_bank)s Statement, but %(account)s is a %(account_bank)s Account.")
            % {"statement_bank": Bank(parsed.bank).label, "account": account, "account_bank": account.get_bank_display()}
        )

    with transaction.atomic():
        if isinstance(account, NewAccount):
            account = Account.objects.create(name=account.name, bank=parsed.bank)
            account.owners.add(member)
        statement = Statement(
            account=account, format=format, period_start=parsed.period_start, period_end=parsed.period_end,
            opening_balance=parsed.opening_balance, closing_balance=parsed.closing_balance,
            imported_by=member, sha256=sha256,
        )
        statement.file.save(PurePath(filename).name, ContentFile(content), save=False)
        try:
            statement.save()
            transactions = Transaction.objects.bulk_create(
                Transaction(
                    account=account, date=row.date, amount=row.amount, description=row.description,
                    counterparty_name=row.counterparty_name, counterparty_iban=row.counterparty_iban,
                    reference=row.reference, running_balance=row.running_balance, raw=row.raw,
                )
                for row in parsed.rows
            )
            statement.transactions.add(*transactions)
        except IntegrityError:
            # The same file was imported concurrently, between the sha256 check and here.
            statement.file.delete(save=False)
            raise ImportRejected(_("This Statement was already imported."))
        except BaseException:
            statement.file.delete(save=False)
            raise

    return ImportSummary(account, parsed.period_start, parsed.period_end, len(transactions), parsed.skipped_count)
