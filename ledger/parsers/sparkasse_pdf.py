"""Banka Sparkasse (Slovenia) PDF Statements, as extracted text.

The summary table prints, per currency, the opening balance, money out and its row count, money
in and its row count, and the closing balance. Only the EUR block counts; the CHF/GBP/USD blocks
and the legal text after them are skipped.

In the EUR block, rows are listed under PRILIVI (money in) and ODLIVI (money out) with unsigned
amounts. Each row takes two dated lines:

    <booking date> <counterparty name> <amount> [<reference>]
    [<rest of the name>, on lines of its own]
    <value date> <counterparty IBAN> [<purpose>]
    [<the IBAN's last digits>, on a line of their own] [<rest of the purpose>]

The interest row has no counterparty: its first line has only the amount, and its description
("Pozitivne obresti") is on the value-date line instead of an IBAN.
"""

import re
from datetime import datetime, timedelta
from decimal import Decimal

from django.utils.translation import gettext as _

from .types import ParsedRow, ParsedStatement, ParseError, Totals

MONEY = r"\d{1,3}(?:\.\d{3})*,\d\d"
OWN_IBAN = re.compile(r"^IBAN (SI56(?: \d{4}){3} \d{3})$", re.M)
PERIOD = re.compile(r"^Datum predhodnega izpiska: (\S+) Datum izpiska: (\S+)$", re.M)
SUMMARY = re.compile(rf"^EUR ({MONEY}) ({MONEY}) (\d+) ({MONEY}) (\d+) ({MONEY})$", re.M)
EUR_BLOCK = re.compile(r"^Promet na TRR \d+ v EUR$")
EUR_BLOCK_END = re.compile(rf"^Končno stanje {MONEY} EUR$")
SECTION_SIGN = {"PRILIVI": 1, "ODLIVI": -1}
SECTION_END = re.compile(rf"^(?:Prilivi|Odlivi) skupaj št\. \d+ {MONEY}EUR$")
# Lines that carry no row: the opening balance, column headers and page footers.
NOISE = re.compile(rf"^(?:Začetno stanje {MONEY} EUR|Dat\.knj\. .*|Dat\.val\. .*|\d+ od \d+)$")
DATE = r"\d\d\.\d\d\.\d{4}"
FIRST_LINE = re.compile(rf"^({DATE})(?: (.*?))? ({MONEY})(?: (\S.*))?$")
SECOND_LINE = re.compile(rf"^({DATE})(?: (.*))?$")
DATED = re.compile(rf"^{DATE}( |$)")
IBAN = re.compile(r"^([A-Z]{2}\d{2}[A-Z0-9]{11,30})(?: (.*))?$")
IBAN_TAIL = re.compile(r"^[A-Z0-9]{1,4}$")
# Lines of the Statement's own layout, which never belong inside a row.
STATEMENT_TEXT = re.compile(
    r"^(?:BANKA SPARKASSE|IZPISEK|IBAN |Datum|Skupni promet|Valuta |Promet na TRR|Začetno stanje|Končno stanje)"
)
NAME_WITH_AMOUNT = re.compile(rf" {MONEY}$|^{MONEY}$")
# IBAN lengths of the SEPA countries, so that a wrapped IBAN's first part never passes as a whole one.
IBAN_LENGTHS = {
    "AD": 24,
    "AT": 20,
    "BE": 16,
    "BG": 22,
    "CH": 21,
    "CY": 28,
    "CZ": 24,
    "DE": 22,
    "DK": 18,
    "EE": 20,
    "ES": 24,
    "FI": 18,
    "FR": 27,
    "GB": 22,
    "GI": 23,
    "GR": 27,
    "HR": 21,
    "HU": 28,
    "IE": 22,
    "IS": 26,
    "IT": 27,
    "LI": 21,
    "LT": 20,
    "LU": 20,
    "LV": 21,
    "MC": 27,
    "MT": 31,
    "NL": 18,
    "NO": 15,
    "PL": 28,
    "PT": 25,
    "RO": 24,
    "SE": 24,
    "SI": 19,
    "SK": 24,
    "SM": 27,
    "VA": 22,
}


def parse(text: str) -> ParsedStatement:
    iban, period, summary = (pattern.search(text) for pattern in (OWN_IBAN, PERIOD, SUMMARY))
    if not (iban and period and summary):
        raise ParseError(_("The Sparkasse Statement has no IBAN, period or EUR totals."))
    opening, money_out, count_out, money_in, count_in, closing = summary.groups()
    return ParsedStatement(
        bank="sparkasse_si",
        iban=iban[1].replace(" ", ""),
        # The period runs from the day after the previous Statement.
        period_start=_date(period[1]) + timedelta(days=1),
        period_end=_date(period[2]),
        opening_balance=_money(opening),
        closing_balance=_money(closing),
        rows=_rows(text),
        skipped_count=0,
        printed_totals=Totals(
            money_in=_money(money_in),
            money_out=_money(money_out),
            count_in=int(count_in),
            count_out=int(count_out),
        ),
    )


def _rows(text: str) -> list[ParsedRow]:
    lines = iter(text.splitlines())
    # Consumes everything up to the EUR block's heading.
    if not any(EUR_BLOCK.match(line) for line in lines):
        raise ParseError(_("The Sparkasse Statement has no EUR block."))
    rows: list[ParsedRow] = []
    sign: int | None = None
    row: list[str] = []  # the lines of the row being read

    def finish_row():
        if row:
            assert sign is not None  # a row is only started inside a PRILIVI/ODLIVI section
            rows.append(_row(row.copy(), sign))
            row.clear()

    for line in lines:
        if EUR_BLOCK_END.match(line):
            break
        if NOISE.match(line):
            continue
        if line in SECTION_SIGN or SECTION_END.match(line):
            finish_row()
            sign = SECTION_SIGN.get(line)
        elif sign is None:
            raise ParseError.unsupported_row(line)
        elif DATED.match(line) and _has_second_line(row):
            finish_row()
            row.append(line)
        elif row or DATED.match(line):
            row.append(line)
        else:
            raise ParseError.unsupported_row(line)
    else:
        raise ParseError(_("The Sparkasse Statement's EUR block has no closing balance."))
    finish_row()
    return rows


def _has_second_line(row: list[str]) -> bool:
    return sum(1 for line in row if DATED.match(line)) == 2


def _row(lines: list[str], sign: int) -> ParsedRow:
    text = " / ".join(lines)
    dated = [i for i, line in enumerate(lines) if DATED.match(line)]
    first = FIRST_LINE.match(lines[0])
    if (
        len(dated) != 2
        or not first
        or any(STATEMENT_TEXT.match(line) for line in lines)
        or any(NAME_WITH_AMOUNT.search(line) for line in lines[1 : dated[1]])
    ):
        raise ParseError.unsupported_row(text)
    booking_date, name, amount, reference = first.groups()
    name = " ".join([name or "", *lines[1 : dated[1]]]).strip()
    second = SECOND_LINE.match(lines[dated[1]])
    if not second:
        raise ParseError.unsupported_row(text)
    value_date, rest = second.groups()
    rest, after = rest or "", lines[dated[1] + 1 :]

    iban = ""
    if match := IBAN.match(rest):
        iban, rest = match[1], match[2] or ""
        if (
            not _valid_iban(iban)
            and after
            and IBAN_TAIL.match(after[0])
            and _valid_iban(iban + after[0])
        ):
            iban, after = iban + after[0], after[1:]
        if not _valid_iban(iban):
            raise ParseError.unsupported_row(text)
    elif name or not rest:
        raise ParseError.unsupported_row(text)
    # The interest row has no name: its description sits where the IBAN would be.
    description = name or rest
    purpose = " ".join([rest, *after]).strip() if name else " ".join(after)

    return ParsedRow(
        date=_date(booking_date),
        amount=sign * _money(amount),
        description=description,
        counterparty_name=name,
        counterparty_iban=iban,
        reference=reference or "",
        raw={"value_date": _date(value_date).isoformat(), "purpose": purpose, "lines": lines},
    )


def _valid_iban(iban: str) -> bool:
    """The country's IBAN length, when known, and the ISO 13616 mod-97 check."""
    if len(iban) != IBAN_LENGTHS.get(iban[:2], len(iban)):
        return False
    digits = "".join(str(int(char, 36)) for char in iban[4:] + iban[:4])
    return int(digits) % 97 == 1


def _date(text: str):
    return datetime.strptime(text, "%d.%m.%Y").date()


def _money(text: str) -> Decimal:
    """ "1.234,56" -> Decimal("1234.56")."""
    return Decimal(text.replace(".", "").replace(",", "."))
