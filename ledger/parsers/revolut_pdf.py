"""Revolut PDF account Statements (the EUR Statement), as extracted text.

The balance summary prints the Current Account's opening balance, money out, money in and
closing balance, but no row counts. The rows follow "Account transactions from <date> to <date>",
each starting with a dated line and followed by lines of detail:

    <Mon D, YYYY> <description> €<amount> €<balance after it>
    [Reference: <reference>]
    [Fee: €<fee> €<amount less the fee>]
    [Revolut Rate <rate> <original amount>] or [<original amount>]
    [To: <merchant or payee>[, <IBAN>]] or [From: <payer>[, <IBAN>]]
    [Card: <masked card number>]

The amount is unsigned and the text doesn't say which column it's in, so its sign comes from the
change in balance. A fee-bearing row's amount and balance include the fee, which becomes a fee
Transaction of its own after its payment, as the Revolut CSV gives it. Each page ends with a
footer and the next one starts with a header; both are skipped, even inside a row.
"""

import re
from datetime import datetime
from decimal import Decimal

from django.utils.translation import gettext as _

from .iban import valid_iban
from .types import ParsedRow, ParsedStatement, ParseError, Totals

MONEY = r"€(\d{1,3}(?:,\d{3})*\.\d\d)"
OWN_IBAN = re.compile(r" IBAN ([A-Z]{2}\d{2}[A-Z0-9]{11,30})$", re.M)
SUMMARY = re.compile(rf"^Account \(Current Account\) {MONEY} {MONEY} {MONEY} {MONEY}$", re.M)
PERIOD = re.compile(r"^Account transactions from (.+) to (.+)$")
PAGE_HEADER = re.compile(
    r"^(?:EUR Statement|Generated on .*|Revolut Bank UAB|Date Description Money out Money in Balance)$"
)
FOOTER_START = re.compile(r"^Report lost or stolen card ")
FOOTER_END = re.compile(r"^© \d{4} Revolut Bank UAB Page \d+ of \d+$")
FIRST_LINE = re.compile(rf"^([A-Z][a-z]{{2}} \d{{1,2}}, \d{{4}}) (.+) {MONEY} {MONEY}$")
DATED = re.compile(r"^[A-Z][a-z]{2} \d{1,2}, \d{4} ")
# The detail lines, by the key each is kept under in `raw`.
DETAILS = {
    "reference": re.compile(r"^Reference: (.+)$"),
    "fee": re.compile(rf"^Fee: {MONEY} {MONEY}$"),
    "rate": re.compile(r"^(Revolut Rate .*\)) (.+)$"),
    "original_amount": re.compile(r"^([^\s\d€]{1,3}[\d,]+\.\d\d|[\d,]+\.\d\d [A-Z]{3})$"),
    "to": re.compile(r"^To: (.+)$"),
    "from": re.compile(r"^From: (.+)$"),
    "card": re.compile(r"^Card: (.+)$"),
}
IBAN_AT_END = re.compile(r", ([A-Z]{2}\d{2}[A-Z0-9]{11,30})$")


def parse(text: str) -> ParsedStatement:
    if not text.startswith("EUR Statement\n"):
        raise ParseError(_("Only Revolut's EUR Statements are supported."))
    iban, summary = OWN_IBAN.search(text), SUMMARY.search(text)
    if not (iban and summary and valid_iban(iban[1])):
        raise ParseError(_("The Revolut Statement has no IBAN or balance summary."))
    opening, money_out, money_in, closing = (_money(amount) for amount in summary.groups())
    period, rows = _rows(text, opening)
    return ParsedStatement(
        bank="revolut",
        iban=iban[1],
        period_start=period[0],
        period_end=period[1],
        opening_balance=opening,
        closing_balance=closing,
        rows=rows,
        skipped_count=0,
        printed_totals=Totals(money_in=money_in, money_out=money_out),
    )


def _rows(text: str, opening: Decimal):
    lines = iter(text.splitlines())
    # Consumes everything up to the transactions' heading.
    period = next((match for line in lines if (match := PERIOD.match(line))), None)
    if period is None:
        raise ParseError(_("The Revolut Statement has no transactions heading."))
    rows: list[ParsedRow] = []
    balance = opening
    row: list[str] = []  # the lines of the row being read

    def finish_row():
        nonlocal balance
        if row:
            new_rows = _row(row.copy(), balance)
            balance += sum(new_row.amount for new_row in new_rows)
            rows.extend(new_rows)
            row.clear()

    for line in lines:
        if FOOTER_START.match(line):
            if not any(FOOTER_END.match(footer) for footer in lines):
                raise ParseError.unsupported_row(line)
        elif PAGE_HEADER.match(line):
            continue
        elif DATED.match(line):
            finish_row()
            row.append(line)
        elif row:
            row.append(line)
        else:
            raise ParseError.unsupported_row(line)
    finish_row()
    return (_date(period[1], "%B %d, %Y"), _date(period[2], "%B %d, %Y")), rows


def _row(lines: list[str], balance_before: Decimal) -> list[ParsedRow]:
    """The row's Transaction, and its fee Transaction after it if it has a fee."""
    text = " / ".join(lines)
    first = FIRST_LINE.match(lines[0])
    if not first:
        raise ParseError.unsupported_row(text)
    day, description, amount, balance = first[1], first[2], _money(first[3]), _money(first[4])
    details: dict[str, re.Match] = {}
    for line in lines[1:]:
        key, match = next(
            ((key, match) for key, pattern in DETAILS.items() if (match := pattern.match(line))),
            (None, None),
        )
        if key is None or match is None or key in details:
            raise ParseError.unsupported_row(text)
        details[key] = match

    if balance - balance_before == amount:
        sign = 1
    elif balance_before - balance == amount:
        sign = -1
    else:
        raise ParseError.unsupported_row(text)
    fee = Decimal(0)
    if match := details.get("fee"):
        fee, net = _money(match[1]), _money(match[2])
        if sign != -1 or fee + net != amount:
            raise ParseError.unsupported_row(text)
        amount = net

    raw: dict = {"lines": lines}
    for key, match in details.items():
        if key == "rate":
            raw["rate"], raw["original_amount"] = match[1], match[2]
        elif key != "fee":
            raw[key] = match[1]
    party = details.get("to") or details.get("from")
    party_iban = IBAN_AT_END.search(party[1]) if party else None
    iban = party_iban[1] if party_iban else ""
    if iban and not valid_iban(iban):
        raise ParseError.unsupported_row(text)

    date = _date(day, "%b %d, %Y")
    payment = ParsedRow(
        date=date,
        amount=sign * amount,
        description=description,
        # As the Revolut CSV gives it, which has only the description.
        counterparty_name=description.removeprefix("Payment from ")
        if description.startswith("Payment from ")
        else "",
        counterparty_iban=iban,
        reference=raw.get("reference", ""),
        running_balance=balance + fee,
        raw=raw,
    )
    if not fee:
        return [payment]
    return [
        payment,
        ParsedRow(
            # Stored data, so not translated.
            date=date,
            amount=-fee,
            description=f"Fee: {description}",
            running_balance=balance,
            raw=raw,
            is_fee=True,
        ),
    ]


def _date(text: str, format: str):
    try:
        return datetime.strptime(text, format).date()
    except ValueError as err:
        raise ParseError.unsupported_row(text) from err


def _money(text: str) -> Decimal:
    """ "1,234.56" -> Decimal("1234.56")."""
    return Decimal(text.replace(",", ""))
