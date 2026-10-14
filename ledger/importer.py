"""The import pipeline: one Statement file in, committed Statement and Transactions out.

It runs in two calls, because the Account may have to be asked for after parsing:

- `check_statement`: sha256 re-import check, parse, balance check, printed totals check, then
  Account detection from the Statement's own IBAN;
- `commit_statement`: into the detected Account, or one the Member picked or creates (whom it
  then belongs to), checks the opening balance and Duplicates against the Account's Coverage,
  then stores the Statement, its Transactions (less the Duplicates) and the original file, and
  categorizes the new Transactions by the Rules.

Any failure raises ImportRejected and stores nothing of that Statement.
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

from .coverage import ONE_DAY, DateRange, gaps
from .models import Account, AccountIBAN, Bank, Source, Statement, Subcategory, Transaction
from .parsers import ParsedRow, ParsedStatement, ParseError, Totals, parse
from .rules import apply_rules


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


@dataclass(frozen=True)
class DayMismatch:
    """A day inside the Account's Coverage whose rows don't match the Transactions already imported."""

    day: date
    missing: list[Transaction]
    """Already imported for this day, but not on the new Statement."""
    unexpected: list[ParsedRow]
    """On the new Statement, but not among the Transactions already imported for this day."""


class ImportRejected(Exception):
    """The Statement was not imported.

    `keep_file` asks the Member to keep the file because a parser fix needs it; `diagnosis` is
    set when the numbers didn't add up, `mismatch` when rows inside the Coverage didn't match.
    """

    def __init__(
        self,
        message: str,
        *,
        keep_file: bool = False,
        diagnosis: Diagnosis | None = None,
        mismatch: list[DayMismatch] | None = None,
    ):
        super().__init__(message)
        self.keep_file = keep_file or diagnosis is not None
        self.diagnosis = diagnosis
        self.mismatch = mismatch or []


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
    duplicate_count: int
    skipped_count: int
    rule_count: int
    """The new Transactions the Rules categorized."""
    gaps: list[DateRange] = field(default_factory=list)
    """The Coverage gaps the new Statement left: new ones, or ones it only partly filled."""


@dataclass(frozen=True)
class FileResult:
    """What became of one uploaded file: a summary if it was imported, the rejection if not."""

    filename: str
    summary: ImportSummary | None = None
    rejection: ImportRejected | None = None


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
    totals_match = parsed.printed_totals is None or parsed.printed_totals.matches(parsed_totals)
    if not balances_add_up or not totals_match:
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

    # None once an admin deleted it; fees then wait in the Review queue.
    bank_fees = Subcategory.objects.filter(is_bank_fees=True).first()
    with transaction.atomic():
        if isinstance(account, NewAccount):
            account = Account.objects.create(name=account.name, bank=parsed.bank)
            account.owners.add(member)
        else:
            # Imports into one Account run one at a time, so each sees the Coverage the previous one left.
            account = Account.objects.select_for_update().get(pk=account.pk)
        duplicates, new_rows = _match_coverage(account, parsed)
        _check_running_balance(account, parsed, new_rows)
        gaps_before = set(gaps(account.coverage()))
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
                for row in new_rows
            )
            statement.transactions.add(*transactions, *duplicates)
            rule_count = apply_rules(
                Transaction.objects.filter(pk__in=[t.pk for t in transactions])
            )
            gaps_left = sorted(
                set(gaps(account.coverage())) - gaps_before, key=lambda gap: gap.start
            )
        except IntegrityError as err:
            # The same file (or another Statement of this IBAN) was imported concurrently, after the checks.
            statement.file.delete(save=False)
            raise ImportRejected(_("This Statement was already imported.")) from err
        except BaseException:
            statement.file.delete(save=False)
            raise

    return ImportSummary(
        account,
        parsed.period_start,
        parsed.period_end,
        len(transactions),
        len(duplicates),
        parsed.skipped_count,
        rule_count,
        gaps_left,
    )


def _totals(rows: list[ParsedRow]) -> Totals:
    """The parsed rows' money in/out and counts, to compare with the printed ones."""
    money_in = [row.amount for row in rows if row.amount > 0]
    money_out = [-row.amount for row in rows if row.amount < 0]
    return Totals(
        sum(money_in, Decimal(0)), sum(money_out, Decimal(0)), len(money_in), len(money_out)
    )


def _check_running_balance(account: Account, parsed: ParsedStatement, inserted: list[ParsedRow]):
    """The new Statement must follow the Account's running balance wherever it runs into the Coverage.

    That is where it starts after an existing Statement's first day (up to the day after its
    last day), and where it reaches the first day of a Coverage range. `inserted` are the
    Statement's rows that aren't Duplicates.

    An existing Statement's own rows give the balance after its first day; rows other Statements
    added on its last day follow its own rows, so they count too, while rows added on its first
    day precede its opening balance. Going into a Coverage range, the new Statement's rows added on
    the range's first day therefore come before the opening balance of the Statement starting there.
    """
    start = parsed.period_start
    before = (
        account.statements.filter(period_start__lt=start, period_end__gte=start - ONE_DAY)
        .order_by("period_start", "id")
        .first()
    )
    if before is not None:
        added_on_last_day = account.transactions.filter(
            date=before.period_end, date__lt=start
        ).exclude(statements=before)
        expected = (
            before.opening_balance
            + _total(before.transactions.filter(date__lt=start))
            + _total(added_on_last_day)
        )
        _require_balance(start, parsed.opening_balance, expected)

    for covered in account.coverage():
        if not start <= covered.start <= parsed.period_end + ONE_DAY:
            continue
        # Of the Statements starting that day, the latest imported has every row of the day.
        first = account.statements.filter(period_start=covered.start).latest("id")
        reached = (
            parsed.opening_balance
            + sum((row.amount for row in parsed.rows if row.date < covered.start), Decimal(0))
            + sum((row.amount for row in inserted if row.date == covered.start), Decimal(0))
        )
        _require_balance(covered.start, reached, first.opening_balance)


def _total(transactions) -> Decimal:
    return transactions.aggregate(total=Sum("amount"))["total"] or Decimal(0)


def _require_balance(day: date, balance: Decimal, expected: Decimal):
    if balance != expected:
        raise ImportRejected(
            _(
                "The Statement's balance going into %(date)s is %(balance)s, but the Account's was %(expected)s, "
                "so it was not imported."
            )
            % {"date": date_format(day), "balance": balance, "expected": expected}
        )


def _match_coverage(
    account: Account, parsed: ParsedStatement
) -> tuple[list[Transaction], list[ParsedRow]]:
    """Split a new Statement's rows against the Account's Coverage.

    Returns the already imported Transactions the rows inside the Coverage matched (the
    Duplicates) and the rows to insert. Inside the Coverage, each day's rows must match the
    Transactions already imported for that day as a multiset; only on the first and last day of
    a Coverage range may the new Statement add rows, as long as it matches every existing one.
    """
    rows = parsed.rows
    ranges = account.coverage()
    if not ranges:
        return [], rows
    edge_days = {r.start for r in ranges} | {r.end for r in ranges}

    def covered(day):
        return any(day in r for r in ranges)

    new_by_day: dict[date, list[ParsedRow]] = {}
    for row in rows:
        new_by_day.setdefault(row.date, []).append(row)
    existing_by_day: dict[date, list[Transaction]] = {}
    days = [parsed.period_start, parsed.period_end, *new_by_day]
    for existing in account.transactions.filter(date__range=(min(days), max(days))):
        existing_by_day.setdefault(existing.date, []).append(existing)

    duplicates: list[Transaction] = []
    to_insert = [row for row in rows if not covered(row.date)]
    mismatch: list[DayMismatch] = []
    for day in sorted(set(new_by_day) | set(existing_by_day)):
        if not covered(day):
            continue
        matched, missing, unexpected = _match_day(
            existing_by_day.get(day, []), new_by_day.get(day, [])
        )
        if missing or (unexpected and day not in edge_days):
            mismatch.append(DayMismatch(day, missing, unexpected))
        duplicates += matched
        to_insert += unexpected
    if mismatch:
        raise ImportRejected(
            _(
                "Rows inside the Account's Coverage don't match the Transactions already imported, so it was not imported."
            ),
            mismatch=mismatch,
        )
    return duplicates, to_insert


def _match_day(
    existing: list[Transaction], new: list[ParsedRow]
) -> tuple[list[Transaction], list[Transaction], list[ParsedRow]]:
    """Match one day's rows as a multiset on (amount, plus running balance where printed).

    Returns the matched existing Transactions, the unmatched existing ones and the unmatched new rows.
    """
    both: list[Transaction | ParsedRow] = [*existing, *new]
    with_balance = all(
        transaction_or_row.running_balance is not None for transaction_or_row in both
    )

    def key(transaction_or_row: Transaction | ParsedRow):
        return (
            transaction_or_row.amount,
            transaction_or_row.running_balance if with_balance else None,
        )

    unmatched = list(existing)
    matched: list[Transaction] = []
    unexpected: list[ParsedRow] = []
    for row in new:
        match = next((t for t in unmatched if key(t) == key(row)), None)
        if match is None:
            unexpected.append(row)
        else:
            unmatched.remove(match)
            matched.append(match)
    return matched, unmatched, unexpected
