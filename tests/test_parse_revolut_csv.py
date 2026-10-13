from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest

from ledger.parsers import ParseError, parse

FIXTURE = (Path(__file__).parent / "fixtures" / "revolut.csv").read_bytes()


def test_revolut_csv_statement():
    statement = parse(FIXTURE, "csv")

    assert statement.bank == "revolut"
    assert statement.iban is None
    assert statement.period_start == date(2026, 6, 1)
    assert statement.period_end == date(2026, 6, 11)
    assert statement.opening_balance == Decimal("500.00")
    assert statement.closing_balance == Decimal("2152.64")
    assert statement.printed_totals is None
    assert statement.skipped_count == 1


def test_revolut_csv_rows():
    rows = parse(FIXTURE, "csv").rows

    assert [(r.date, r.amount, r.description, r.counterparty_name, r.running_balance, r.is_fee) for r in rows] == [
        (date(2026, 6, 1), Decimal("-4.50"), "Hiša kave", "", Decimal("495.50"), False),
        (date(2026, 6, 3), Decimal("2000.00"), "Payment from Ana Novak", "Ana Novak", Decimal("2495.50"), False),
        (date(2026, 6, 6), Decimal("-50.02"), "Corner Shop", "", Decimal("2445.48"), False),
        (date(2026, 6, 6), Decimal("-0.50"), "Fee: Corner Shop", "", Decimal("2444.98"), True),
        (date(2026, 6, 8), Decimal("-300.00"), "To Janez Kranjc", "", Decimal("2144.98"), False),
        (date(2026, 6, 8), Decimal("-5.00"), "Fee: To Janez Kranjc", "", Decimal("2139.98"), True),
        (date(2026, 6, 10), Decimal("25.00"), "Čevljar", "", Decimal("2164.98"), False),
        (date(2026, 6, 11), Decimal("-12.34"), "Mercator Žalec", "", Decimal("2152.64"), False),
    ]
    assert all(r.counterparty_iban == "" and r.reference == "" for r in rows)


def test_revolut_csv_keeps_the_whole_line_in_raw():
    first = parse(FIXTURE, "csv").rows[0]

    assert first.raw["Started Date"] == "2026-05-31 21:10:09"
    assert first.raw["Type"] == "Card Payment"
    assert first.raw["Description"] == "Hiša kave"


def test_revolut_csv_leaves_correctly_encoded_text_alone():
    content = FIXTURE.decode().replace("HiÅ¡a kave", "Hiša kave").encode()

    assert parse(content, "csv").rows[0].description == "Hiša kave"


def test_revolut_csv_skips_every_row_that_is_not_completed():
    line = b"Card Payment,Current,2026-06-12 9:00:00,,Bakery,-3.2,0,EUR,REVERTED,\n"

    statement = parse(FIXTURE + line, "csv")

    assert statement.skipped_count == 2
    assert statement.period_end == date(2026, 6, 11)


@pytest.mark.parametrize("line", [
    "Card Payment,Savings,2026-06-12 9:00:00,2026-06-12 9:00:01,Bakery,-3.2,0,EUR,COMPLETED,2149.44",
    "Card Payment,Current,2026-06-12 9:00:00,2026-06-12 9:00:01,Bakery,-3.2,0,USD,COMPLETED,2149.44",
    "Card Payment,Current,2026-06-12 9:00:00,yesterday,Bakery,-3.2,0,EUR,COMPLETED,2149.44",
    "Card Payment,Current,2026-06-12 9:00:00,2026-06-12 9:00:01,Bakery,-3.2,0,EUR,COMPLETED",
])
def test_revolut_csv_rejects_an_unrecognised_row(line):
    with pytest.raises(ParseError) as error:
        parse(FIXTURE + line.encode() + b"\n", "csv")

    assert str(error.value) == f"unsupported row: {line}"


def test_a_csv_that_is_not_a_revolut_export_is_rejected():
    with pytest.raises(ParseError) as error:
        parse(b"Date,Amount\n2026-06-01,10\n", "csv")

    assert str(error.value) == "unsupported row: Date,Amount"
