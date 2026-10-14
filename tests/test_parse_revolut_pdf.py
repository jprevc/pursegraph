from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest

from ledger.parsers import ParseError, Totals, parse, parse_pdf_text

FIXTURES = Path(__file__).parent / "fixtures"
FIXTURE = (FIXTURES / "revolut.txt").read_text()


def test_revolut_pdf_statement():
    statement = parse_pdf_text(FIXTURE)

    assert statement.bank == "revolut"
    assert statement.iban == "LT121000011101001000"
    assert statement.period_start == date(2026, 6, 1)
    assert statement.period_end == date(2026, 6, 11)
    assert statement.opening_balance == Decimal("500.00")
    assert statement.closing_balance == Decimal("2152.64")
    # Revolut prints money in and out, but not how many rows of each.
    assert statement.printed_totals == Totals(
        money_in=Decimal("2025.00"), money_out=Decimal("372.36")
    )
    assert statement.skipped_count == 0


def test_revolut_pdf_rows():
    rows = parse_pdf_text(FIXTURE).rows

    assert [
        (r.date, r.amount, r.description, r.counterparty_iban, r.reference, r.running_balance)
        for r in rows
    ] == [
        (date(2026, 6, 1), Decimal("-4.50"), "Hiša kave", "", "", Decimal("495.50")),
        (
            date(2026, 6, 3),
            Decimal("2000.00"),
            "Payment from Ana Novak",
            "SI56020100001234582",
            "SI00 12345",
            Decimal("2495.50"),
        ),
        (date(2026, 6, 6), Decimal("-50.02"), "Corner Shop", "", "", Decimal("2445.48")),
        (date(2026, 6, 6), Decimal("-0.50"), "Fee: Corner Shop", "", "", Decimal("2444.98")),
        (
            date(2026, 6, 8),
            Decimal("-300.00"),
            "To Janez Kranjc",
            "DE89370400440532013000",
            "rent June",
            Decimal("2144.98"),
        ),
        (date(2026, 6, 8), Decimal("-5.00"), "Fee: To Janez Kranjc", "", "", Decimal("2139.98")),
        (date(2026, 6, 10), Decimal("25.00"), "Čevljar", "", "", Decimal("2164.98")),
        (date(2026, 6, 11), Decimal("-12.34"), "Mercator Žalec", "", "", Decimal("2152.64")),
    ]
    assert [r.is_fee for r in rows] == [False, False, False, True, False, True, False, False]


def test_revolut_pdf_keeps_the_merchant_line_in_raw():
    first = parse_pdf_text(FIXTURE).rows[0]

    assert first.raw["to"] == "Hisa Kave, Ljubljana"
    assert first.raw["card"] == "123456******7890"
    assert first.raw["lines"] == [
        "Jun 1, 2026 Hiša kave €4.50 €495.50",
        "To: Hisa Kave, Ljubljana",
        "Card: 123456******7890",
    ]


def test_revolut_pdf_keeps_the_fx_rate_and_original_amount_in_the_payments_raw():
    rows = parse_pdf_text(FIXTURE).rows
    card, swift = rows[2], rows[4]

    assert card.raw["rate"] == "Revolut Rate €1.00 = £0.85 (ECB rate* €1.00 = £0.86)"
    assert card.raw["original_amount"] == "£42.52"
    assert "rate" not in swift.raw
    assert swift.raw["original_amount"] == "$345.00"
    assert swift.raw["to"] == "Janez Kranjc, DE89370400440532013000"


def test_revolut_pdf_gives_the_rows_the_revolut_csv_gives_for_the_same_period():
    csv_rows = parse((FIXTURES / "revolut.csv").read_bytes(), "csv").rows

    def fields(r):
        return (r.date, r.amount, r.description, r.counterparty_name, r.running_balance, r.is_fee)

    assert [fields(r) for r in parse_pdf_text(FIXTURE).rows] == [fields(r) for r in csv_rows]


def replace(old, new):
    assert old in FIXTURE
    return FIXTURE.replace(old, new)


@pytest.mark.parametrize(
    "old, new, row",
    [
        # A balance that moved by something other than the amount.
        (
            "Jun 1, 2026 Hiša kave €4.50 €495.50",
            "Jun 1, 2026 Hiša kave €4.50 €496.50",
            "Jun 1, 2026 Hiša kave €4.50 €496.50 / To: Hisa Kave, Ljubljana / Card: 123456******7890",
        ),
        # A fee and net amount that don't add up to the amount.
        (
            "Fee: €5.00 €300.00",
            "Fee: €5.00 €299.00",
            "Jun 8, 2026 To Janez Kranjc €305.00 €2,139.98 / Reference: rent June / "
            "Fee: €5.00 €299.00 / $345.00 / To: Janez Kranjc, DE89370400440532013000",
        ),
        # An unknown line of detail.
        (
            "Card: 123456******7890\nJun 11",
            "Card: 123456******7890\nCashback: €0.10\nJun 11",
            "Jun 10, 2026 Čevljar €25.00 €2,164.98 / Card: 123456******7890 / Cashback: €0.10",
        ),
        # The same detail twice.
        (
            "To: Mercator Zalec, Zalec\n",
            "To: Mercator Zalec, Zalec\nTo: Mercator Zalec, Zalec\n",
            "Jun 11, 2026 Mercator Žalec €12.34 €2,152.64 / To: Mercator Zalec, Zalec / "
            "To: Mercator Zalec, Zalec / Card: 123456******7890",
        ),
        # An IBAN that fails its checksum.
        (
            "SI56020100001234582",
            "SI56020100001234583",
            "Jun 3, 2026 Payment from Ana Novak €2,000.00 €2,495.50 / Reference: SI00 12345 / "
            "From: Ana Novak, SI56020100001234583",
        ),
        # Text before the first row.
        (
            "Balance\nJun 1, 2026",
            "Balance\nPending transactions\nJun 1, 2026",
            "Pending transactions",
        ),
    ],
)
def test_revolut_pdf_rejects_an_unrecognised_row(old, new, row):
    with pytest.raises(ParseError) as error:
        parse_pdf_text(replace(old, new))

    assert str(error.value) == f"unsupported row: {row}"


def test_revolut_pdf_joins_a_row_split_by_a_page_break():
    text = replace("Card: 123456******7890\nReport lost", "Report lost").replace(
        "Balance\nJun 8", "Balance\nCard: 123456******7890\nJun 8"
    )

    corner_shop = parse_pdf_text(text).rows[2]

    assert corner_shop.raw["card"] == "123456******7890"


def test_a_revolut_statement_in_another_currency_is_rejected():
    with pytest.raises(ParseError) as error:
        parse_pdf_text(FIXTURE.replace("EUR Statement", "USD Statement"))

    assert str(error.value) == "Only Revolut's EUR Statements are supported."
