"""The date and money formats the Slovenian and German banks print."""

from datetime import date, datetime
from decimal import Decimal


def dotted_date(text: str) -> date:
    """ "31.08.2026" -> date(2026, 8, 31)."""
    return datetime.strptime(text, "%d.%m.%Y").date()


def comma_money(text: str) -> Decimal:
    """ "-1.234,56" -> Decimal("-1234.56")."""
    return Decimal(text.replace(".", "").replace(",", "."))
