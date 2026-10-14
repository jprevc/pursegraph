from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal

from django.utils.translation import gettext as _


class ParseError(Exception):
    """The Statement can't be parsed. The message is shown to the Member."""

    @classmethod
    def unsupported_row(cls, text: str) -> "ParseError":
        return cls(_("unsupported row: %(row)s") % {"row": text})


@dataclass(frozen=True)
class ParsedRow:
    """One Transaction as the Statement lists it. `amount` is signed (negative = out) and fee-free."""

    date: date
    amount: Decimal
    description: str
    counterparty_name: str = ""
    counterparty_iban: str = ""
    reference: str = ""
    running_balance: Decimal | None = None
    raw: dict = field(default_factory=dict)
    # A bank fee split off its payment; categorized Finance → Bank fees at import.
    is_fee: bool = False


@dataclass(frozen=True)
class Totals:
    """Money in and out, and how many rows of each: as a Statement prints them, or as its rows add up.

    A Statement that prints no row counts (N26, Revolut) leaves them None.
    """

    money_in: Decimal
    money_out: Decimal
    count_in: int | None = None
    count_out: int | None = None

    def matches(self, parsed: "Totals") -> bool:
        """These printed totals agree with the `parsed` rows' totals, comparing counts only where printed."""
        return (
            self.money_in == parsed.money_in
            and self.money_out == parsed.money_out
            and self.count_in in (None, parsed.count_in)
            and self.count_out in (None, parsed.count_out)
        )


@dataclass(frozen=True)
class ParsedStatement:
    bank: str
    iban: str | None
    period_start: date
    period_end: date
    opening_balance: Decimal
    closing_balance: Decimal
    rows: list[ParsedRow]
    skipped_count: int
    """Rows left out because they aren't completed (pending, reverted, declined)."""
    printed_totals: Totals | None = None
