"""N26 PDF Statements, as extracted text.

The rows come first, on pages headed "Bank Statement Nr. MM/YYYY", with signed amounts. Each row
takes several lines:

    <description> <booking date> <signed amount>€
    <N26's category line, such as "Mastercard • Groceries" or "Outgoing Transfers">
    [IBAN: <counterparty IBAN> • BIC: <BIC>]
    [<purpose>, on lines of its own]
    Value Date <value date>

The overview page after them prints the opening and closing balances and the money in and out
totals, but no row counts. Every page ends in a footer with the Account holder's name and address and the
Statement's own IBAN.
"""

import re
from datetime import datetime
from decimal import Decimal

from django.utils.translation import gettext as _

from .types import ParsedRow, ParsedStatement, ParseError, Totals

UNSIGNED = r"\d{1,3}(?:\.\d{3})*,\d\d"
MONEY = rf"[+-]?{UNSIGNED}"
DATE = r"\d\d\.\d\d\.\d{4}"
OWN_IBAN = re.compile(r"^IBAN: ([A-Z]{2}\d{2}[A-Z0-9]+) • BIC: \S+ Nr\. \d\d/\d{4}$", re.M)
PERIOD = re.compile(rf"^({DATE}) until ({DATE})$", re.M)
OPENING = re.compile(rf"^Previous balance ({MONEY})€$", re.M)
MONEY_OUT = re.compile(rf"^Outgoing transactions ({MONEY})€$", re.M)
MONEY_IN = re.compile(rf"^Incoming transactions ({MONEY})€$", re.M)
CLOSING = re.compile(rf"^Your new balance ({MONEY})€$", re.M)
OVERVIEW = re.compile(r"^Overview Nr\. \d\d/\d{4}$")
# The page footer's first line; the next one is the Account holder's address and the issue date.
FOOTER = re.compile(r"^.* Issued on$")
# Lines that carry no row: page headers and the rest of the page footer.
NOISE = re.compile(
    rf"^(?:Bank Statement Nr\. \d\d/\d{{4}}|{DATE} until {DATE}|Description Booking Date Amount"
    rf"|{OWN_IBAN.pattern[1:-1]}|\d+ / \d+)$"
)
# A row's amount always carries its sign.
FIRST_LINE = re.compile(rf"^(.+) ({DATE}) ([+-]{UNSIGNED})€$")
VALUE_DATE = re.compile(rf"^Value Date ({DATE})$")
IBAN = re.compile(r"^IBAN: ([A-Z]{2}\d{2}[A-Z0-9]+) • BIC: \S+$")


def parse(text: str) -> ParsedStatement:
    iban, period, opening, money_out, money_in, closing = (
        pattern.search(text)
        for pattern in (OWN_IBAN, PERIOD, OPENING, MONEY_OUT, MONEY_IN, CLOSING)
    )
    if not (iban and period and opening and money_out and money_in and closing):
        raise ParseError(_("The N26 Statement has no IBAN, period or overview balances."))
    return ParsedStatement(
        bank="n26",
        iban=iban[1],
        period_start=_date(period[1]),
        period_end=_date(period[2]),
        opening_balance=_money(opening[1]),
        closing_balance=_money(closing[1]),
        rows=_rows(text),
        skipped_count=0,
        # The overview prints money out as negative, or unsigned when it's zero.
        printed_totals=Totals(money_in=_money(money_in[1]), money_out=-_money(money_out[1])),
    )


def _rows(text: str) -> list[ParsedRow]:
    rows: list[ParsedRow] = []
    row: list[str] = []  # the lines of the row being read
    lines = iter(text.splitlines())
    for line in lines:
        if OVERVIEW.match(line):
            break
        if FOOTER.match(line):
            next(lines, None)  # the address
        elif NOISE.match(line):
            continue
        elif FIRST_LINE.match(line):
            if row:  # the previous row never reached its value date
                raise ParseError.unsupported_row(" / ".join(row))
            row.append(line)
        elif not row:
            raise ParseError.unsupported_row(line)
        else:
            row.append(line)
            if VALUE_DATE.match(line):
                rows.append(_row(row.copy()))
                row.clear()
    else:
        raise ParseError(_("The N26 Statement has no overview page."))
    if row:
        raise ParseError.unsupported_row(" / ".join(row))
    return rows


def _row(lines: list[str]) -> ParsedRow:
    text = " / ".join(lines)
    first, value_date = FIRST_LINE.match(lines[0]), VALUE_DATE.match(lines[-1])
    details = lines[1:-1]
    ibans = [match[1] for line in details if (match := IBAN.match(line))]
    if not (first and value_date and details) or IBAN.match(details[0]) or len(ibans) > 1:
        raise ParseError.unsupported_row(text)
    description, booking_date, amount = first.groups()
    category, *rest = details
    return ParsedRow(
        date=_date(booking_date),
        amount=_money(amount),
        description=description,
        counterparty_name=description,
        counterparty_iban=ibans[0] if ibans else "",
        raw={
            "n26_category": category,
            "purpose": " ".join(line for line in rest if not IBAN.match(line)),
            "value_date": _date(value_date[1]).isoformat(),
            "lines": lines,
        },
    )


def _date(text: str):
    return datetime.strptime(text, "%d.%m.%Y").date()


def _money(text: str) -> Decimal:
    """ "-1.234,56" -> Decimal("-1234.56")."""
    return Decimal(text.replace(".", "").replace(",", "."))
