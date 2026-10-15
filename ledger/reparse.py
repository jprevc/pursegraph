"""Re-parsing stored Statement files, to see what a parser fix would change.

`reparse()` parses a Statement's stored original file again and compares the result with what
is stored: the Statement's own fields and the Transactions on it. It only reads; nothing is changed.
"""

from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import date
from typing import Any

from .importer import ImportRejected, check_numbers
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
class Reparse:
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


def reparse(statement: Statement) -> Reparse:
    result = Reparse(statement)
    name = statement.file.name
    if not name or not statement.file.storage.exists(name):
        result.error = "the stored file is missing"
        return result
    with statement.file.open("rb") as file:
        content = file.read()
    try:
        parsed = parse(content, statement.format)
    except ParseError as error:
        result.error = str(error)
        return result

    result.statement_changes = _statement_changes(statement, parsed)
    _diff_rows(result, list(statement.transactions.all()), parsed.rows)
    try:
        check_numbers(parsed)
    except ImportRejected as rejection:
        diagnosis = rejection.diagnosis
        assert diagnosis is not None
        if diagnosis.opening_balance + diagnosis.rows_total != diagnosis.closing_balance:
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


def _statement_changes(statement: Statement, parsed: ParsedStatement) -> list[FieldChange]:
    changes = [
        FieldChange(name, getattr(statement, name), getattr(parsed, name))
        for name in STATEMENT_FIELDS
        if getattr(statement, name) != getattr(parsed, name)
    ]
    if parsed.bank != statement.account.bank:
        changes.append(FieldChange("bank", statement.account.bank, parsed.bank))
    if parsed.iban and not statement.account.ibans.filter(iban=parsed.iban).exists():
        changes.append(FieldChange("iban", None, parsed.iban))
    return changes


def _row_changes(transaction: Transaction, row: ParsedRow) -> list[FieldChange]:
    return [
        FieldChange(name, getattr(transaction, name), getattr(row, name))
        for name in ROW_FIELDS
        if getattr(transaction, name) != getattr(row, name)
    ]


def _diff_rows(result: Reparse, stored: list[Transaction], rows: list[ParsedRow]) -> None:
    """Match the rows to the stored Transactions day by day, the closest matches first.

    First every field equal, then the same amount and running balance (a changed description,
    say), then the same description (a changed amount). What is left over is added or removed.
    """
    stored_by_day: dict[date, list[Transaction]] = {}
    for transaction in stored:
        stored_by_day.setdefault(transaction.date, []).append(transaction)
    rows_by_day: dict[date, list[ParsedRow]] = {}
    for row in rows:
        rows_by_day.setdefault(row.date, []).append(row)

    passes: list[Callable[[Transaction | ParsedRow], Any]] = [
        lambda t: tuple(getattr(t, name) for name in ROW_FIELDS),
        lambda t: (t.amount, t.running_balance),
        lambda t: t.description,
    ]
    for day in sorted(set(stored_by_day) | set(rows_by_day)):
        unmatched = stored_by_day.get(day, [])
        left = rows_by_day.get(day, [])
        for key in passes:
            still_left = []
            for row in left:
                match = next((t for t in unmatched if key(t) == key(row)), None)
                if match is None:
                    still_left.append(row)
                    continue
                unmatched.remove(match)
                if changes := _row_changes(match, row):
                    result.changed.append(ChangedRow(match, changes))
            left = still_left
        result.added += left
        result.removed += unmatched
