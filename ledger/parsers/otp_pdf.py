"""OTP banka (Slovenia) PDF Statements, as layout text.

The plain text runs the payee column and the wrapped description column together, so these are
parsed from pdfplumber's layout text, which keeps a gap of two or more spaces between them.

The summary prints the EUR opening balance, money out (Breme), money in (Dobro) and the closing
balance, but no row counts. The rows follow, page after page, with unsigned amounts whose column
(Breme or Dobro) doesn't survive as text: each is signed by which way it moves the running balance
printed beside it. Each row takes two dated lines and the payee's further lines:

    <value date> <transaction ID> [<payee>] <amount> <running balance> <description>
    <booking date> [<payee, continued>]  [<description, continued>]
    [<payee, continued>, on lines of their own]

The payee is one of:
- the Account holder's own account in its domestic form ("04001-..."): a card payment or a cash
  withdrawal, with the holder's name and address on the next lines. The description names the
  merchant, so it is the counterparty too;
- "Prejemnik: <name>", whichever way the money went, then a mobile number (a Flik payment) or the
  counterparty's IBAN in groups of four, possibly wrapped, then "Ref.: [<reference>]" and, for an
  IBAN, an optional purpose before it and "Koda namena: <purpose code>" after it;
- an IBAN alone, with the payee's name and address on the next lines: the bank's monthly fee;
- nothing: a fee for a cash withdrawal, or a card payment booked after the period.

A row is dated by its booking date, except one booked after the period ends: card payments of the
period's last day can be booked days later, yet the bank lists them and counts them in this
Statement's closing balance; the next Statement starts from that balance and doesn't list them
again. That row is dated by its value date and keeps its booking date in raw.
"""

import re
from datetime import date, datetime, timedelta
from decimal import Decimal

from django.utils.translation import gettext as _

from .iban import IBAN_LENGTHS, tidy_iban, valid_iban
from .types import ParsedRow, ParsedStatement, ParseError, Totals

MONEY = r"\d{1,3}(?:\.\d{3})*,\d\d"
DATE = r"\d\d\.\d\d\.\d{4}"
OWN_IBAN = re.compile(r"TRANSAKCIJSKEM RAČUNU ŠTEV\. (SI56(?: \d{4}){3} \d{3}) ZA OBDOBJE")
STATEMENT_DATE = re.compile(rf"Datum izpiska: ({DATE})$", re.M)
PREVIOUS_DATE = re.compile(rf"Datum pre\. izpiska: ({DATE})$", re.M)
SUMMARY = re.compile(rf"^\s*EUR\s+({MONEY})\s+({MONEY})\s+({MONEY})\s+({MONEY})$", re.M)
ROWS_START = "Izpis prometa na transakcijskem računu"
# The legal text after the last row.
ROWS_END = re.compile(
    r"^(?:\S+ stanje na transakcijskem računu |Storitev je oproščena plačila DDV)"
)
CURRENCY = re.compile(r"^VALUTA: (\S+)$")
# Lines that carry no row: column headers and page footers.
NOISE = re.compile(
    r"^(?:Datum val\. ID|Datum knj transakcije .*|\S+ \S+ +Stran \d+|OTP banka d\.d\.; .*"
    r"|EUR; identifikacijska številka za DDV: .*)$"
)
FIRST_LINE = re.compile(rf"^({DATE}) (\d+)(?: +(\S.*?))? +({MONEY}) +(-?{MONEY})(?: +(\S.*))?$")
SECOND_LINE = re.compile(rf"^({DATE})(?: +(\S.*))?$")
# The Account holder's own account, in its domestic form: a card payment or cash withdrawal.
OWN_ACCOUNT = re.compile(r"^\d{5}-\d{10}$")
IBAN = re.compile(r"^[A-Z]{2}\d{2}[A-Z0-9]{11,30}$")
IBAN_START = re.compile(r"^([A-Z]{2})\d{2}$")
IBAN_GROUP = re.compile(r"^[A-Z0-9]{1,4}$")
PHONE = re.compile(r"^00\d{8,13}$")
PAYEE = "Prejemnik:"
# The layout puts a gap of two or more spaces between the payee column and the description column.
COLUMN_GAP = re.compile(r" {2,}")
FEE = re.compile(r"^(?:PROVIZIJA|MESEČNI STROŠKI VODENJA)\b")


def is_statement(text: str) -> bool:
    """`text`, plain or layout, is an OTP banka Statement's."""
    return "ZBIRNI PODATKI NA TRANSAKCIJSKEM RAČUNU" in text and "OTP banka d.d.;" in text


def parse(text: str) -> ParsedStatement:
    # The layout text pads every line to the page's width.
    text = "\n".join(line.rstrip() for line in text.splitlines())
    iban, end, previous, summary = (
        pattern.search(text) for pattern in (OWN_IBAN, STATEMENT_DATE, PREVIOUS_DATE, SUMMARY)
    )
    if not (iban and end and previous and summary and valid_iban(tidy_iban(iban[1]))):
        raise ParseError(_("The OTP banka Statement has no IBAN, period or EUR totals."))
    opening, money_out, money_in, closing = (_money(amount) for amount in summary.groups())
    period_end = _date(end[1])
    return ParsedStatement(
        bank="otp_si",
        iban=tidy_iban(iban[1]),
        # The period runs from the day after the previous Statement.
        period_start=_date(previous[1]) + timedelta(days=1),
        period_end=period_end,
        opening_balance=opening,
        closing_balance=closing,
        rows=_rows(text, opening, period_end),
        skipped_count=0,
        printed_totals=Totals(money_in=money_in, money_out=money_out),
    )


def _rows(text: str, opening: Decimal, period_end: date) -> list[ParsedRow]:
    lines = iter(line.strip() for line in text.splitlines())
    # Consumes everything up to the rows' heading.
    if not any(line == ROWS_START for line in lines):
        raise ParseError(_("The OTP banka Statement has no rows' heading."))
    rows: list[ParsedRow] = []
    row: list[str] = []  # the lines of the row being read

    def finish_row():
        if row:
            balance = rows[-1].running_balance if rows else opening
            assert balance is not None  # every OTP row has its running balance
            rows.append(_row(row.copy(), balance, period_end))
            row.clear()

    for line in lines:
        if ROWS_END.match(line):
            break
        if not line or NOISE.match(line):
            continue
        if currency := CURRENCY.match(line):
            if currency[1] != "EUR":
                raise ParseError.unsupported_row(line)
        elif FIRST_LINE.match(line):
            finish_row()
            row.append(line)
        elif row:
            row.append(line)
        else:
            raise ParseError.unsupported_row(line)
    finish_row()
    return rows


def _row(lines: list[str], previous_balance: Decimal, period_end: date) -> ParsedRow:
    """A row's lines: <value date> <ID> [<payee>] <amount> <balance> <description>, then
    <booking date> [<payee, continued>] [<description, continued>], then the payee's other lines."""
    text = " / ".join(lines)
    first = FIRST_LINE.match(lines[0])
    second = SECOND_LINE.match(lines[1]) if len(lines) > 1 else None
    if not (first and second):
        raise ParseError.unsupported_row(text)
    value_date, transaction_id, body, amount, balance, description = first.groups()
    booking_date, rest = second.groups()
    # Each later line is <payee column>[  <description column>].
    payee_lines: list[str] = []
    more_description: list[str] = []
    for line in [rest or "", *lines[2:]]:
        payee, *description_part = COLUMN_GAP.split(line, maxsplit=1)
        payee_lines.append(payee)
        more_description += description_part
    description = " ".join([description or "", *more_description]).strip()
    if not description:
        raise ParseError.unsupported_row(text)

    raw: dict = {
        "value_date": _date(value_date).isoformat(),
        "transaction_id": transaction_id,
        "lines": lines,
    }
    name, iban, reference = description, "", ""
    if body is None:
        # A bank fee, or a card payment booked days after its value date (see the module docstring).
        if any(payee_lines):
            raise ParseError.unsupported_row(text)
    elif OWN_ACCOUNT.match(body) or IBAN.match(body):
        # A card payment or cash withdrawal names the Account holder; a payment with the payee's
        # IBAN alone (the bank's own fees) names the payee. Both lines go on with its address.
        if not payee_lines[0] or len(payee_lines) > 3:
            raise ParseError.unsupported_row(text)
        if IBAN.match(body):
            if not valid_iban(body):
                raise ParseError.unsupported_row(text)
            name, iban = payee_lines[0], body
    elif body.startswith(PAYEE + " "):
        payee = _payee([body.removeprefix(PAYEE + " "), *payee_lines])
        if payee is None:
            raise ParseError.unsupported_row(text)
        name, iban, reference, payee_raw = payee
        raw.update(payee_raw)
    else:
        raise ParseError.unsupported_row(text)

    signed = _signed(_money(amount), previous_balance, _money(balance))
    if signed is None:
        raise ParseError.unsupported_row(text)
    row_date = _date(booking_date)
    if row_date > period_end:
        # Booked after the period, yet in this Statement's closing balance.
        raw["booking_date"] = row_date.isoformat()
        row_date = _date(value_date)
    return ParsedRow(
        date=row_date,
        amount=signed,
        description=description,
        counterparty_name=name,
        counterparty_iban=iban,
        reference=reference,
        running_balance=_money(balance),
        raw=raw,
        is_fee=bool(FEE.match(description)),
    )


def _payee(lines: list[str]) -> tuple[str, str, str, dict] | None:
    """The payee column of a transfer: <name> <IBAN or mobile number> [<purpose>] Ref.: [<reference>]
    [Koda namena: <purpose code>], wrapped over several lines. None if it isn't laid out so."""
    name: list[str] = []
    purpose: list[str] = []
    iban, reference, code = "", "", ""
    raw: dict = {}
    state = "name"
    for word in " ".join(lines).split():
        if state == "name" and PHONE.match(word):
            raw["phone"], state = word, "purpose"
        elif state == "name" and (start := IBAN_START.match(word)) and start[1] in IBAN_LENGTHS:
            iban, state = word, "iban"
        elif state == "iban":
            if not (IBAN_GROUP.match(word) and len(iban + word) <= IBAN_LENGTHS[iban[:2]]):
                return None
            iban += word
            if len(iban) == IBAN_LENGTHS[iban[:2]]:
                state = "purpose"
        elif state in ("name", "purpose") and word == "Ref.:":
            state = "reference"
        elif state == "name":
            name.append(word)
        elif state == "purpose":
            purpose.append(word)
        elif state == "reference" and word == "Koda":
            state = "koda"
        elif state == "reference" and not reference:
            reference = word
        elif state == "koda" and word == "namena:":
            state = "code"
        elif state == "code" and not code:
            code = word
        else:
            return None
    if state not in ("reference", "code") or not name or (iban and not valid_iban(iban)):
        return None
    if purpose:
        raw["purpose"] = " ".join(purpose)
    if code:
        raw["purpose_code"] = code
    return " ".join(name), iban, reference, raw


def _signed(amount: Decimal, previous_balance: Decimal, balance: Decimal) -> Decimal | None:
    """The amount signed by which way it moved the running balance: the columns don't survive
    as text."""
    if previous_balance - amount == balance:
        return -amount
    if previous_balance + amount == balance:
        return amount
    return None


def _date(text: str) -> date:
    return datetime.strptime(text, "%d.%m.%Y").date()


def _money(text: str) -> Decimal:
    """ "1.234,56" -> Decimal("1234.56")."""
    return Decimal(text.replace(".", "").replace(",", "."))
