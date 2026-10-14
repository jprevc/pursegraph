from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest

from ledger.parsers import ParseError, Totals, parse_pdf_text

FIXTURE = (Path(__file__).parent / "fixtures" / "n26.txt").read_text()


def test_n26_statement():
    statement = parse_pdf_text(FIXTURE)

    assert statement.bank == "n26"
    assert statement.iban == "DE89370400440532013000"
    assert statement.period_start == date(2026, 9, 1)
    assert statement.period_end == date(2026, 9, 30)
    assert statement.opening_balance == Decimal("572.94")
    assert statement.closing_balance == Decimal("745.21")
    # N26 prints no row counts.
    assert statement.printed_totals == Totals(
        money_in=Decimal("1250.00"), money_out=Decimal("1077.73")
    )
    assert statement.skipped_count == 0


def test_n26_rows():
    rows = parse_pdf_text(FIXTURE).rows

    assert [
        (r.date, r.amount, r.description, r.counterparty_name, r.counterparty_iban) for r in rows
    ] == [
        (date(2026, 9, 2), Decimal("-12.40"), "ZABEC MARKET", "ZABEC MARKET", ""),
        (date(2026, 9, 5), Decimal("1250.00"), "Ana Novak", "Ana Novak", "SI56020100001234582"),
        (date(2026, 9, 8), Decimal("-45.90"), "PETROL LJUBLJANA", "PETROL LJUBLJANA", ""),
        (
            date(2026, 9, 10),
            Decimal("-1000.00"),
            "Ana Novak",
            "Ana Novak",
            "DE02120300000000202051",
        ),
        (date(2026, 9, 20), Decimal("-8.99"), "BOOKSHOP DIGITAL", "BOOKSHOP DIGITAL", ""),
        (date(2026, 9, 22), Decimal("-10.00"), "N26", "N26", ""),
        (date(2026, 9, 23), Decimal("-0.44"), "EasyPark SI", "EasyPark SI", ""),
    ]
    assert all(r.running_balance is None and r.reference == "" for r in rows)


def test_n26_keeps_its_category_line_purpose_and_value_date_in_raw():
    rows = parse_pdf_text(FIXTURE).rows

    assert [(r.raw["n26_category"], r.raw["purpose"], r.raw["value_date"]) for r in rows] == [
        ("Mastercard • Groceries", "", "2026-09-01"),
        ("Incoming Transfers", "Placa september", "2026-09-05"),
        ("Mastercard • Car", "", "2026-09-07"),
        ("Outgoing Transfers", "Sent from N26", "2026-09-10"),
        ("Mastercard", "", "2026-09-20"),
        ("Card Reorder Fee", "", "2026-09-22"),
        ("Mastercard • Car", "", "2026-09-22"),
    ]
    assert rows[1].raw["lines"] == [
        "Ana Novak 05.09.2026 +1.250,00€",
        "Incoming Transfers",
        "IBAN: SI56020100001234582 • BIC: LJBASI2XXXX",
        "Placa september",
        "Value Date 05.09.2026",
    ]


def test_n26_statement_with_no_rows():
    text = FIXTURE.split("ZABEC MARKET")[0] + FIXTURE[FIXTURE.index("Overview") :]
    text = text.replace("-1.077,73€", "0,00€").replace("+1.250,00€", "0,00€")
    text = text.replace("+745,21€", "+572,94€")

    statement = parse_pdf_text(text)

    assert statement.rows == []
    assert statement.printed_totals == Totals(money_in=Decimal(0), money_out=Decimal(0))


def replace(old, new):
    assert old in FIXTURE
    return FIXTURE.replace(old, new)


@pytest.mark.parametrize(
    "old, new, row",
    [
        # A line outside any row.
        (
            "Value Date 01.09.2026\n",
            "Value Date 01.09.2026\nSomething else\n",
            "Something else",
        ),
        # A first line without an amount.
        (
            "ZABEC MARKET 02.09.2026 -12,40€",
            "ZABEC MARKET 02.09.2026",
            "ZABEC MARKET 02.09.2026",
        ),
        # An unsigned amount.
        (
            "ZABEC MARKET 02.09.2026 -12,40€",
            "ZABEC MARKET 02.09.2026 12,40€",
            "ZABEC MARKET 02.09.2026 12,40€",
        ),
        # A row with no value-date line.
        (
            "Mastercard • Groceries\nValue Date 01.09.2026\n",
            "Mastercard • Groceries\n",
            "ZABEC MARKET 02.09.2026 -12,40€ / Mastercard • Groceries",
        ),
        # A row with no category line.
        (
            "Mastercard • Groceries\nValue Date 01.09.2026\n",
            "Value Date 01.09.2026\n",
            "ZABEC MARKET 02.09.2026 -12,40€ / Value Date 01.09.2026",
        ),
        # Two IBAN lines in one row.
        (
            "IBAN: DE02120300000000202051 • BIC: BYLADEM1001\n",
            "IBAN: DE02120300000000202051 • BIC: BYLADEM1001\n"
            "IBAN: DE02120300000000202051 • BIC: BYLADEM1001\n",
            "Ana Novak 10.09.2026 -1.000,00€ / Outgoing Transfers / "
            "IBAN: DE02120300000000202051 • BIC: BYLADEM1001 / "
            "IBAN: DE02120300000000202051 • BIC: BYLADEM1001 / Sent from N26 / Value Date 10.09.2026",
        ),
    ],
)
def test_n26_rejects_an_unrecognised_row(old, new, row):
    with pytest.raises(ParseError) as error:
        parse_pdf_text(replace(old, new))

    assert str(error.value) == f"unsupported row: {row}"


def test_n26_money_out_printed_as_positive_doesnt_match_the_rows():
    statement = parse_pdf_text(replace("-1.077,73€", "+1.077,73€"))

    assert statement.printed_totals is not None
    assert statement.printed_totals.money_out == Decimal("-1077.73")


def test_n26_statement_without_an_overview_is_rejected():
    with pytest.raises(ParseError) as error:
        parse_pdf_text(replace("Previous balance +572,94€\n", ""))

    assert "overview" in str(error.value)
