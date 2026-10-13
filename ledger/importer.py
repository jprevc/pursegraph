"""The import pipeline: one Statement file in, committed Statement and Transactions out.

Steps, for one file: sha256 re-import check, parse, balance check, Account resolution, the
opening balance and Duplicate checks against the Account's Coverage, then commit (Statement,
Transactions and the original file). Any failure rejects that file and stores nothing of it.
"""

import hashlib
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from pathlib import PurePath

from django.core.files.base import ContentFile
from django.db import IntegrityError, transaction
from django.db.models import Sum
from django.utils.formats import date_format
from django.utils.translation import gettext as _

from .coverage import ONE_DAY, DateRange, coverage, gaps
from .models import Account, Bank, Statement, Transaction
from .parsers import ParsedRow, ParsedStatement, ParseError, parse


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


@dataclass(frozen=True)
class DayMismatch:
    """A day inside the Account's Coverage whose rows don't match the Transactions already imported."""

    day: date
    missing: list[Transaction] = field(default_factory=list)
    """Already imported for this day, but not on the new Statement."""
    unexpected: list[ParsedRow] = field(default_factory=list)
    """On the new Statement, but not among the Transactions already imported for this day."""


class ImportRejected(Exception):
    """The Statement was not imported.

    `keep_file` asks the Member to keep the file because a parser fix needs it; `diagnosis` is
    set when the balances didn't add up, `mismatch` when rows inside the Coverage didn't match.
    """

    def __init__(
        self, message: str, *, keep_file: bool = False, diagnosis: BalanceDiagnosis | None = None,
        mismatch: list[DayMismatch] | None = None,
    ):
        super().__init__(message)
        self.keep_file = keep_file or diagnosis is not None
        self.diagnosis = diagnosis
        self.mismatch = mismatch or []


@dataclass(frozen=True)
class ImportSummary:
    account: Account
    period_start: date
    period_end: date
    imported_count: int
    duplicate_count: int
    skipped_count: int
    gaps: list[DateRange] = field(default_factory=list)
    """The Coverage gaps right before and after the new Statement's stretch of Coverage."""


@dataclass(frozen=True)
class FileResult:
    """What became of one uploaded file: a summary if it was imported, the rejection if not."""

    filename: str
    summary: ImportSummary | None = None
    rejection: ImportRejected | None = None


@dataclass(frozen=True)
class _CheckedFile:
    """A file that parsed and whose balances add up, ready to be checked against its Account."""

    filename: str
    content: bytes
    sha256: str
    format: str
    parsed: ParsedStatement


def import_statements(*, files: list[tuple[str, bytes]], member, account: Account | NewAccount) -> list[FileResult]:
    """Import each of `files` (filename, content) into `account`, independently of the others.

    Files that can't be parsed are rejected first; the rest are imported in period order, so
    each one's Duplicate check sees the Coverage the earlier ones left. A NewAccount is created
    by the first file imported, and the later files go into it.
    """
    results: list[FileResult] = []
    checked: list[_CheckedFile] = []
    for filename, content in files:
        try:
            checked.append(_check_file(filename, content))
        except ImportRejected as rejection:
            results.append(FileResult(filename, rejection=rejection))
    for file in sorted(checked, key=lambda f: (f.parsed.period_start, f.parsed.period_end)):
        try:
            summary = _import_checked(file, member, account)
        except ImportRejected as rejection:
            results.append(FileResult(file.filename, rejection=rejection))
        else:
            results.append(FileResult(file.filename, summary=summary))
            account = summary.account
    return results


def _check_file(filename: str, content: bytes) -> _CheckedFile:
    """The checks that need nothing but the file: sha256 re-import, parse, balance check."""
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
    return _CheckedFile(filename, content, sha256, format, parsed)


def _import_checked(file: _CheckedFile, member, account: Account | NewAccount) -> ImportSummary:
    parsed = file.parsed
    if isinstance(account, Account) and account.bank != parsed.bank:
        raise ImportRejected(
            _("This is a %(statement_bank)s Statement, but %(account)s is a %(account_bank)s Account.")
            % {"statement_bank": Bank(parsed.bank).label, "account": account, "account_bank": account.get_bank_display()}
        )

    with transaction.atomic():
        if isinstance(account, NewAccount):
            account = Account.objects.create(name=account.name, bank=parsed.bank)
            account.owners.add(member)
        else:
            # Imports into one Account run one at a time, so each sees the Coverage the previous one left.
            account = Account.objects.select_for_update().get(pk=account.pk)
        _check_opening_balance(account, parsed)
        duplicates, new_rows = _match_coverage(account, parsed)
        statement = Statement(
            account=account, format=file.format, period_start=parsed.period_start, period_end=parsed.period_end,
            opening_balance=parsed.opening_balance, closing_balance=parsed.closing_balance,
            imported_by=member, sha256=file.sha256,
        )
        statement.file.save(PurePath(file.filename).name, ContentFile(file.content), save=False)
        try:
            statement.save()
            transactions = Transaction.objects.bulk_create(
                Transaction(
                    account=account, date=row.date, amount=row.amount, description=row.description,
                    counterparty_name=row.counterparty_name, counterparty_iban=row.counterparty_iban,
                    reference=row.reference, running_balance=row.running_balance, raw=row.raw,
                )
                for row in new_rows
            )
            statement.transactions.add(*transactions, *duplicates)
            adjacent_gaps = _adjacent_gaps(account, statement)
        except IntegrityError:
            # The same file was imported concurrently (or twice in one upload), after the sha256 check.
            statement.file.delete(save=False)
            raise ImportRejected(_("This Statement was already imported."))
        except BaseException:
            statement.file.delete(save=False)
            raise

    return ImportSummary(
        account, parsed.period_start, parsed.period_end, len(transactions), len(duplicates), parsed.skipped_count,
        adjacent_gaps,
    )


def _adjacent_gaps(account: Account, statement: Statement) -> list[DateRange]:
    ranges = coverage(account.statements.all())
    [own] = [r for r in ranges if statement.period_start in r]
    return [gap for gap in gaps(ranges) if gap.end + ONE_DAY == own.start or gap.start - ONE_DAY == own.end]


def _check_opening_balance(account: Account, parsed: ParsedStatement):
    """The new Statement must start from the Account's running balance where the Coverage already shows it.

    That is where it starts after an existing Statement's first day, up to the day after its last
    day. The existing Statement's own rows give the balance; rows other Statements added on its
    last day (which follow its own rows) count too. Extra rows on its first day precede its
    opening balance, so they don't.
    """
    start = parsed.period_start
    before = (
        account.statements.filter(period_start__lt=start, period_end__gte=start - ONE_DAY)
        .order_by("period_start", "id").first()
    )
    if before is None:
        return
    rows_before = before.transactions.filter(date__lt=start).aggregate(total=Sum("amount"))["total"] or 0
    added_on_last_day = (
        account.transactions.filter(date=before.period_end, date__lt=start).exclude(statements=before)
        .aggregate(total=Sum("amount"))["total"] or 0
    )
    expected = before.opening_balance + rows_before + added_on_last_day
    if parsed.opening_balance != expected:
        raise ImportRejected(
            _("The Statement opens at %(opening)s, but the Account's balance going into %(date)s was %(expected)s, "
              "so it was not imported.")
            % {"opening": parsed.opening_balance, "date": date_format(start), "expected": expected}
        )


def _match_coverage(account: Account, parsed: ParsedStatement) -> tuple[list[Transaction], list[ParsedRow]]:
    """Split a new Statement's rows against the Account's Coverage.

    Returns the already imported Transactions the rows inside the Coverage matched (the
    Duplicates) and the rows to insert. Inside the Coverage, each day's rows must match the
    Transactions already imported for that day as a multiset; only on the first and last day of
    a Coverage range may the new Statement add rows, as long as it matches every existing one.
    """
    rows = parsed.rows
    ranges = coverage(account.statements.all())
    if not ranges:
        return [], rows
    edge_days = {r.start for r in ranges} | {r.end for r in ranges}

    def covered(day):
        return any(day in r for r in ranges)

    new_by_day: dict[date, list[ParsedRow]] = {}
    for row in rows:
        new_by_day.setdefault(row.date, []).append(row)
    existing_by_day: dict[date, list[Transaction]] = {}
    for existing in account.transactions.filter(date__range=(parsed.period_start, parsed.period_end)):
        existing_by_day.setdefault(existing.date, []).append(existing)

    duplicates: list[Transaction] = []
    to_insert = [row for row in rows if not covered(row.date)]
    mismatch: list[DayMismatch] = []
    for day in sorted(set(new_by_day) | set(existing_by_day)):
        if not covered(day):
            continue
        matched, missing, unexpected = _match_day(existing_by_day.get(day, []), new_by_day.get(day, []))
        if missing or (unexpected and day not in edge_days):
            mismatch.append(DayMismatch(day, missing, unexpected))
        duplicates += matched
        to_insert += unexpected
    if mismatch:
        raise ImportRejected(
            _("Rows inside the Account's Coverage don't match the Transactions already imported, so it was not imported."),
            mismatch=mismatch,
        )
    return duplicates, to_insert


def _match_day(existing: list[Transaction], new: list[ParsedRow]):
    """Match one day's rows as a multiset on (amount, plus running balance where printed).

    Returns the matched existing Transactions, the unmatched existing ones and the unmatched new rows.
    """
    with_balance = all(item.running_balance is not None for item in [*existing, *new])

    def key(item):
        return item.amount, item.running_balance if with_balance else None

    unmatched = list(existing)
    matched, unexpected = [], []
    for row in new:
        match = next((t for t in unmatched if key(t) == key(row)), None)
        if match is None:
            unexpected.append(row)
        else:
            unmatched.remove(match)
            matched.append(match)
    return matched, unmatched, unexpected
