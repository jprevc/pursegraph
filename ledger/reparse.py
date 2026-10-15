"""Re-parsing stored Statement files, to see what a parser fix would change.

`reparse()` parses a Statement's stored original file again and compares the result with what
is stored: the Statement's own fields and the Transactions on it. It only reads; nothing is changed.
"""

from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import date
from typing import Any

from .importer import ImportRejected, check_balances_and_totals
from .models import Statement, Transaction
from .parsers import ParsedRow, ParsedStatement, ParseError, parse

# The Transaction fields a parser sets, apart from the date the rows are matched by.
# `raw` is left out: it is everything the parser saw, so any parser change shows there.
ROW_FIELDS = (
    "amount",
    "description",
    "counterparty_name",
    "counterparty_iban",
    "reference",
    "running_balance",
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
    changes: list[FieldChange]


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
                    result.changed.append(ChangedRow(match, changes))
            unmatched_rows = still_unmatched
        result.added += unmatched_rows
        result.removed += unmatched_stored


def _by_day[T: (Transaction, ParsedRow)](items: list[T]) -> dict[date, list[T]]:
    by_day: dict[date, list[T]] = {}
    for item in items:
        by_day.setdefault(item.date, []).append(item)
    return by_day
