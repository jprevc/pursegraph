"""What Revolut's CSV and PDF Statements share, so that both give the same Transactions."""

from datetime import date
from decimal import Decimal

from .types import ParsedRow


def counterparty_name(description: str) -> str:
    """The payer of a "Payment from <name>"; Revolut names no other counterparty."""
    return (
        description.removeprefix("Payment from ") if description.startswith("Payment from ") else ""
    )


def fee_row(day: date, fee: Decimal, description: str, balance: Decimal, raw: dict) -> ParsedRow:
    """The fee Transaction split off its payment, carrying the balance after both."""
    return ParsedRow(
        # Stored data, so not translated.
        date=day,
        amount=-fee,
        description=f"Fee: {description}",
        running_balance=balance,
        raw=raw,
        is_fee=True,
    )
