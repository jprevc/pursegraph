"""Revolut's CSV account-statement export.

Revolut double-encodes non-ASCII text (`Å¡` for `š`) and doesn't zero-pad hours. Rows are
dated by their Completed Date and listed in balance order. Only COMPLETED rows are
Transactions; rows in any other state are skipped. `Amount` is fee-free and `Balance` is after both the amount and the fee, so a
non-zero `Fee` becomes a fee Transaction of its own right after its payment.
"""

import csv
import io
from datetime import datetime
from decimal import Decimal, InvalidOperation

from django.utils.translation import gettext as _

from .types import ParsedRow, ParsedStatement, ParseError

HEADER = [
    "Type",
    "Product",
    "Started Date",
    "Completed Date",
    "Description",
    "Amount",
    "Fee",
    "Currency",
    "State",
    "Balance",
]
CENT = Decimal("0.01")


def parse(content: bytes) -> ParsedStatement:
    try:
        lines = list(csv.reader(io.StringIO(content.decode("utf-8-sig"))))
    except (UnicodeDecodeError, csv.Error) as err:
        raise ParseError(_("The file is not a Revolut CSV Statement.")) from err
    if not lines or lines[0] != HEADER:
        raise ParseError.unsupported_row(",".join(lines[0]) if lines else "")

    rows: list[ParsedRow] = []
    skipped = 0
    opening = closing = None
    for fields in lines[1:]:
        if not fields:
            continue
        text = ",".join(fields)
        if len(fields) != len(HEADER):
            raise ParseError.unsupported_row(text)
        line = {name: _repair(value) for name, value in zip(HEADER, fields, strict=True)}
        if line["State"] != "COMPLETED":
            skipped += 1
            continue
        if line["Product"] != "Current" or line["Currency"] != "EUR":
            raise ParseError.unsupported_row(text)
        try:
            day = datetime.strptime(line["Completed Date"], "%Y-%m-%d %H:%M:%S").date()
            amount, fee, balance = (_money(line[name]) for name in ("Amount", "Fee", "Balance"))
        except (ValueError, InvalidOperation) as err:
            raise ParseError.unsupported_row(text) from err

        if opening is None:
            opening = balance - amount + fee
        closing = balance
        description = line["Description"]
        counterparty = (
            description.removeprefix("Payment from ")
            if description.startswith("Payment from ")
            else ""
        )
        rows.append(
            ParsedRow(
                date=day,
                amount=amount,
                description=description,
                counterparty_name=counterparty,
                running_balance=balance + fee,
                raw=line,
            )
        )
        if fee:
            rows.append(
                ParsedRow(
                    # Stored data, so not translated.
                    date=day,
                    amount=-fee,
                    description=f"Fee: {description}",
                    running_balance=balance,
                    raw=line,
                    is_fee=True,
                )
            )

    if opening is None or closing is None:  # set by the first completed row
        raise ParseError(_("The Statement has no completed rows."))
    return ParsedStatement(
        bank="revolut",
        iban=None,
        period_start=min(row.date for row in rows),
        period_end=max(row.date for row in rows),
        opening_balance=opening,
        closing_balance=closing,
        rows=rows,
        skipped_count=skipped,
    )


def _repair(text: str) -> str:
    """Undo Revolut's double encoding (UTF-8 bytes read as Latin-1); leave other text alone."""
    try:
        return text.encode("latin-1").decode("utf-8")
    except (UnicodeEncodeError, UnicodeDecodeError):
        return text


def _money(text: str) -> Decimal:
    value = Decimal(text)
    if value != value.quantize(CENT):
        raise ValueError(text)
    return value.quantize(CENT)
