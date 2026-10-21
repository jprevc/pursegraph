"""How figures read: amounts as sl-SI euros (DESIGN.md, the Locale Figure Rule) and dates in three forms.

`static/figures.js` is the browser's twin of the amount formatters; `tests/test_figures.py` keeps them in step.
"""

from datetime import date, datetime
from decimal import ROUND_HALF_UP, Decimal

from django.utils import formats, numberformat, timezone

NBSP = " "
MINUS = "−"


def _decimal(value) -> Decimal:
    # A float goes through its shortest repr, so 3287.7 stays 3287.7 rather than its binary neighbour.
    return value if isinstance(value, Decimal) else Decimal(str(value))


def _euros(value, places: int, sign: bool = False) -> str:
    """sl-SI EUR as `Intl.NumberFormat('sl-SI', {style: 'currency', currency: 'EUR', useGrouping: 'always'})` writes
    it: "1.234,56 €", rounding halves away from zero and never showing a sign on zero."""
    if value is None or value == "":
        return ""
    amount = _decimal(value).quantize(Decimal(1).scaleb(-places), rounding=ROUND_HALF_UP)
    digits = numberformat.format(
        abs(amount),
        decimal_sep=",",
        decimal_pos=places,
        grouping=3,
        thousand_sep=".",
        force_grouping=True,
    )
    prefix = MINUS if amount < 0 else "+" if sign and amount > 0 else ""
    return f"{prefix}{digits}{NBSP}€"


def money(value) -> str:
    """An amount with its cents: "1.234,56 €"."""
    return _euros(value, 2)


def money_whole(value) -> str:
    """An amount in whole euros, as on a chart's axis: "1.200 €"."""
    return _euros(value, 0)


def money_signed(value) -> str:
    """Net, with its sign always shown: "+3.287,70 €", "−12,00 €"."""
    return _euros(value, 2, sign=True)


def share(value) -> str:
    """A fraction as whole percent with a space: 0.256 is "26 %"."""
    if value is None or value == "":
        return ""
    percent = (_decimal(value) * 100).quantize(Decimal(1), rounding=ROUND_HALF_UP)
    return f"{MINUS if percent < 0 else ''}{abs(percent)}{NBSP}%"


# Dates go through Django's localisation (pursegraph/formats/), so another language brings its own patterns.


def day(value: date) -> str:
    """A day: "1 Feb 2026". A moment is the day it is here."""
    if isinstance(value, datetime) and timezone.is_aware(value):
        value = timezone.localtime(value)
    return formats.date_format(value, "DATE_FORMAT")


def date_range(start: date, end: date) -> str:
    """From `start` to `end`, dropping what repeats: "1–30 Sep 2026", "28 Sep – 3 Oct 2026",
    "29 Dec 2025 – 4 Jan 2026". The dash is spaced once either side holds a space."""
    if start == end:
        return day(start)
    if (start.year, start.month) == (end.year, end.month):
        return f"{formats.date_format(start, 'j')}–{day(end)}"
    if start.year == end.year:
        return f"{formats.date_format(start, 'MONTH_DAY_FORMAT')} – {day(end)}"
    return f"{day(start)} – {day(end)}"


def month(value: date) -> str:
    """A month: "September 2026"."""
    return formats.date_format(value, "YEAR_MONTH_FORMAT")
