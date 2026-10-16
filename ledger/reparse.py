"""Re-parsing stored Statement files, to see what a parser fix would change, and to apply it.

`reparse()` parses a Statement's stored original file again and compares the result with what
is stored: the Statement's own fields and the Transactions on it. It only reads; nothing is changed.
`apply_changes()` then takes the changed Transactions' fields on in place.
"""

from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import date
from typing import Any

from django.db import transaction
from django.db.models import Q

from .importer import ImportRejected, check_balances_and_totals, run_automatic_steps
from .models import Source, Statement, Transaction
from .parsers import ParsedRow, ParsedStatement, ParseError, parse
from .transfers import WINDOW

# The Transaction fields a parser sets, apart from the date the rows are matched by.
# `raw` is left out: it is everything the parser saw, so any parser change shows there.
ROW_FIELDS = (
    "amount",
    "description",
    "counterparty_name",
    "counterparty_iban",
    "reference",
    "running_balance",
    "is_fee",
)
# The fields the automatic steps read: a change to one gives the Transaction its outcome again.
RERUN_FIELDS = (
    "amount",
    "description",
    "counterparty_name",
    "counterparty_iban",
    "reference",
    "is_fee",
)
# What a Duplicate was matched by: the rest of it comes from the Statement that first had it.
DUPLICATE_FIELDS = ("amount", "running_balance")
STATEMENT_FIELDS = ("period_start", "period_end", "opening_balance", "closing_balance")


@dataclass(frozen=True)
class FieldChange:
    name: str
    stored: Any
    parsed: Any


@dataclass(frozen=True)
class ChangedRow:
    """A stored Transaction the re-parsed Statement still has, with some of its fields different."""

    transaction: Transaction
    row: ParsedRow
    changes: list[FieldChange]


@dataclass(frozen=True)
class OutcomeChange:
    """A Transaction whose outcome applying a re-parse changed, each described for the Member."""

    transaction: Transaction
    before: str
    after: str


@dataclass
class ReparseResult:
    """A Statement re-parsed: its differences against what is stored, or why it couldn't be."""

    statement: Statement
    error: str = ""
    """Why the file couldn't be re-parsed, or why the re-parsed Statement would be rejected."""
    statement_changes: list[FieldChange] = field(default_factory=list)
    changed: list[ChangedRow] = field(default_factory=list)
    added: list[ParsedRow] = field(default_factory=list)
    """Rows the re-parsed Statement has that no stored Transaction matches."""
    removed: list[Transaction] = field(default_factory=list)
    """Transactions on the Statement that no re-parsed row matches."""

    @property
    def has_differences(self) -> bool:
        return bool(self.statement_changes or self.changed or self.added or self.removed)


def reparse(statement: Statement) -> ReparseResult:
    result = ReparseResult(statement)
    name = statement.file.name
    if not name or not statement.file.storage.exists(name):
        result.error = "the stored file is missing"
        return result
    try:
        with statement.file.open("rb") as file:
            content = file.read()
        parsed = parse(content, statement.format)
    except ParseError as error:
        result.error = str(error)
        return result
    except Exception as error:
        # A parser bug, say, fails this Statement only.
        result.error = f"{type(error).__name__}: {error}"
        return result

    result.statement_changes = _statement_changes(statement, parsed)
    _diff_rows(result, list(statement.transactions.all()), _duplicate_ids(statement), parsed.rows)
    try:
        check_balances_and_totals(parsed)
    except ImportRejected as rejection:
        diagnosis = rejection.diagnosis
        assert diagnosis is not None
        if not diagnosis.balances_add_up:
            result.error = (
                f"the balances don't add up: opening {diagnosis.opening_balance}"
                f" + rows {diagnosis.rows_total} ≠ closing {diagnosis.closing_balance}"
            )
        else:
            result.error = (
                f"the rows don't match the printed totals: printed {diagnosis.printed_totals},"
                f" parsed {diagnosis.parsed_totals}"
            )
    return result


def _duplicate_ids(statement: Statement) -> set[int]:
    """The Transactions that were Duplicates on the Statement: an earlier imported Statement has them too."""
    return set(
        Transaction.statements.through.objects.filter(
            transaction__statements=statement, statement__id__lt=statement.pk
        ).values_list("transaction_id", flat=True)
    )


def _statement_changes(statement: Statement, parsed: ParsedStatement) -> list[FieldChange]:
    changes = _field_changes(statement, parsed, STATEMENT_FIELDS)
    if parsed.bank != statement.account.bank:
        changes.append(FieldChange("bank", statement.account.bank, parsed.bank))
    if parsed.iban and not statement.account.ibans.filter(iban=parsed.iban).exists():
        changes.append(FieldChange("iban", None, parsed.iban))
    return changes


def _compared_fields(
    transaction: Transaction, row: ParsedRow, duplicate_ids: set[int]
) -> tuple[str, ...]:
    if transaction.pk not in duplicate_ids:
        return ROW_FIELDS
    # Like the Duplicate check, the running balance counts only where both have one.
    if transaction.running_balance is None or row.running_balance is None:
        return ("amount",)
    return DUPLICATE_FIELDS


def _field_changes(stored, parsed, names: tuple[str, ...]) -> list[FieldChange]:
    return [
        FieldChange(name, getattr(stored, name), getattr(parsed, name))
        for name in names
        if getattr(stored, name) != getattr(parsed, name)
    ]


def _diff_rows(
    result: ReparseResult,
    stored: list[Transaction],
    duplicate_ids: set[int],
    rows: list[ParsedRow],
) -> None:
    """Match the rows to the stored Transactions day by day, the closest matches first.

    First every compared field equal, then the same amount and running balance (a changed
    description, say), then the same description (a changed amount). What is left over is added
    or removed.
    """
    passes: list[Callable[[Transaction, ParsedRow], bool]] = [
        lambda t, row: not _field_changes(t, row, _compared_fields(t, row, duplicate_ids)),
        lambda t, row: (t.amount, t.running_balance) == (row.amount, row.running_balance),
        lambda t, row: t.description == row.description,
    ]
    stored_by_day = _by_day(stored)
    rows_by_day = _by_day(rows)
    for day in sorted(stored_by_day.keys() | rows_by_day.keys()):
        unmatched_stored = stored_by_day.get(day, [])
        unmatched_rows = rows_by_day.get(day, [])
        for matches in passes:
            still_unmatched = []
            for row in unmatched_rows:
                match = next((t for t in unmatched_stored if matches(t, row)), None)
                if match is None:
                    still_unmatched.append(row)
                    continue
                unmatched_stored.remove(match)
                compared = _compared_fields(match, row, duplicate_ids)
                if changes := _field_changes(match, row, compared):
                    result.changed.append(ChangedRow(match, row, changes))
            unmatched_rows = still_unmatched
        result.added += unmatched_rows
        result.removed += unmatched_stored


def _by_day[T: (Transaction, ParsedRow)](items: list[T]) -> dict[date, list[T]]:
    by_day: dict[date, list[T]] = {}
    for item in items:
        by_day.setdefault(item.date, []).append(item)
    return by_day


def refusal(result: ReparseResult) -> str:
    """Why `apply_changes()` won't take the differences on, if it won't; those need delete and re-import."""
    if result.statement_changes:
        return "the Statement's own fields changed"
    if result.added or result.removed:
        return "rows were added or removed"
    statement = result.statement
    duplicate_ids = _duplicate_ids(statement)
    through = Transaction.statements.through.objects
    for changed in result.changed:
        t = changed.transaction
        others = sorted(
            through.filter(transaction=t)
            .exclude(statement=statement)
            .values_list("statement_id", flat=True)
        )
        if t.pk in duplicate_ids:
            return (
                f"{describe_row(t)} is a Duplicate here; re-parse Statement {others[0]}, which first"
                " had it, instead"
            )
        if others and any(change.name in DUPLICATE_FIELDS for change in changed.changes):
            return (
                f"the amount or running balance of {describe_row(t)} changed, but Statement"
                f"{'' if len(others) == 1 else 's'} {', '.join(map(str, others))}"
                f" {'has' if len(others) == 1 else 'have'} it too"
            )
    return ""


def describe_row(transaction_or_row) -> str:
    """A Transaction or re-parsed row on one line: its date, amount and description."""
    return f"{transaction_or_row.date} {transaction_or_row.amount:.2f} {transaction_or_row.description}"


def apply_changes(result: ReparseResult) -> list[OutcomeChange]:
    """Takes the changed Transactions' parser-set fields and `raw` on from the re-parsed rows, unless
    there is a `refusal()`.

    Those whose change could alter their automatic outcome get it again, as at import; a manual
    outcome is kept. Returns the outcomes that changed, of these Transactions and of those they
    were or are now paired with."""
    rerun = [
        changed.transaction
        for changed in result.changed
        if changed.transaction.source != Source.MANUAL
        and any(change.name in RERUN_FIELDS for change in changed.changes)
    ]
    reach = Q(pk__in=[])
    for t in rerun:
        reach |= Q(date__range=(t.date - WINDOW, t.date + WINDOW))
    affected = Transaction.objects.filter(reach).select_related(
        "subcategory__category", "counterpart"
    )
    with transaction.atomic():
        before = {t.pk: (_outcome(t), describe_outcome(t)) for t in affected}
        for changed in result.changed:
            t = changed.transaction
            for name in (*ROW_FIELDS, "raw"):
                setattr(t, name, getattr(changed.row, name))
            t.save(update_fields=[*ROW_FIELDS, "raw"])
        if not rerun:
            return []

        pks = [t.pk for t in rerun]
        # Like leaving Transfer in set_outcome(): the counterpart stays a one-sided Transfer.
        Transaction.objects.filter(counterpart__in=pks).update(counterpart=None)
        Transaction.objects.filter(pk__in=pks).update(
            subcategory=None,
            is_transfer=False,
            source="",
            rule=None,
            counterpart=None,
            ambiguous_pairing=False,
            suggested_subcategory=None,
            confidence=None,
        )
        run_automatic_steps(Transaction.objects.filter(pk__in=pks))
        return [
            OutcomeChange(t, before[t.pk][1], describe_outcome(t))
            for t in affected.filter(pk__in=before.keys())
            if _outcome(t) != before[t.pk][0]
        ]


def _outcome(t: Transaction) -> tuple:
    return (t.subcategory_id, t.is_transfer, t.counterpart_id, t.ambiguous_pairing, t.source)


def describe_outcome(t: Transaction) -> str:
    """The Transaction's outcome as the Member would read it, with what set it."""
    if t.is_transfer:
        if t.counterpart:
            pairing = f"paired with {t.counterpart}"
        else:
            pairing = "ambiguous pairing" if t.ambiguous_pairing else "one-sided"
        return f"Transfer, {pairing} ({Source(t.source).label})"
    if t.subcategory:
        subcategory = t.subcategory
        return f"{subcategory.category} / {subcategory.name} ({Source(t.source).label})"
    return "awaiting review"
