from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest

from ledger.parsers import ParseError, Totals, parse_pdf_text

FIXTURE = (Path(__file__).parent / "fixtures" / "sparkasse.txt").read_text()


def test_sparkasse_statement():
    statement = parse_pdf_text(FIXTURE)

    assert statement.bank == "sparkasse_si"
    assert statement.iban == "SI56340001234567864"
    assert statement.period_start == date(2026, 9, 1)
    assert statement.period_end == date(2026, 9, 30)
    assert statement.opening_balance == Decimal("4321.90")
    assert statement.closing_balance == Decimal("3729.07")
    assert statement.printed_totals == Totals(
        money_in=Decimal("1250.02"), money_out=Decimal("1842.85"), count_in=2, count_out=10,
    )
    assert statement.skipped_count == 0


FEE = ("Banka Sparkasse, d. d.", "SI56340005000500035")


def test_sparkasse_rows():
    rows = parse_pdf_text(FIXTURE).rows

    assert [(r.date, r.amount, r.description, r.counterparty_name, r.counterparty_iban, r.reference) for r in rows] == [
        (date(2026, 9, 15), Decimal("1250.00"), "ZAVOD ZA ZDRAVSTVENO ZAVAROVANJE SLOVENIJE",
         "ZAVOD ZA ZDRAVSTVENO ZAVAROVANJE SLOVENIJE", "SI56011006000012342", "SI00 15092026-10001"),
        (date(2026, 9, 30), Decimal("0.02"), "Pozitivne obresti", "", "", ""),
        (date(2026, 9, 2), Decimal("-85.00"), "MARKO K", "MARKO K", "SI56020100001234582", ""),
        (date(2026, 9, 8), Decimal("-180.00"), "ORDINACIJA ZA DRUŽINSKO MEDICINO, DR. JANA HORVAT",
         "ORDINACIJA ZA DRUŽINSKO MEDICINO, DR. JANA HORVAT", "SI56040010012345664", "SI12 2026001234500"),
        (date(2026, 9, 8), Decimal("-0.40"), *FEE[:1], *FEE, ""),
        (date(2026, 9, 10), Decimal("-1500.00"), "Ana Novak", "Ana Novak", "LT633250001234567890", "SI00 0000000"),
        (date(2026, 9, 10), Decimal("-0.40"), *FEE[:1], *FEE, ""),
        (date(2026, 9, 15), Decimal("-60.00"), "DARS d.d.", "DARS d.d.", "SI56101000098765492", "SI12 9002600100001"),
        (date(2026, 9, 15), Decimal("-0.40"), *FEE[:1], *FEE, ""),
        (date(2026, 9, 15), Decimal("-16.00"), "DARS d.d.", "DARS d.d.", "SI56051008000123473", "SI12 7112600100002"),
        (date(2026, 9, 15), Decimal("-0.40"), *FEE[:1], *FEE, ""),
        (date(2026, 9, 30), Decimal("-0.25"), *FEE[:1], *FEE, "1600 12345"),
    ]
    assert all(r.running_balance is None for r in rows)


def test_sparkasse_keeps_the_purpose_and_value_date_in_raw():
    rows = parse_pdf_text(FIXTURE).rows

    assert [r.raw["purpose"] for r in rows] == [
        "", "", "Flik plačilo", "Račun št. 2026-00123", "plačilo provizije", "Prenos sredstev",
        "plačilo provizije", "GLOBA ZA PREKRŠEK", "plačilo provizije", "Poravnava kupoprodajnih poslov",
        "plačilo provizije", "NetStik pogodba 51234567890",
    ]
    assert rows[0].raw["value_date"] == "2026-09-15"
    assert rows[0].raw["lines"] == [
        "15.09.2026 ZAVOD ZA ZDRAVSTVENO 1.250,00 SI00 15092026-10001",
        "ZAVAROVANJE SLOVENIJE",
        "15.09.2026 SI56011006000012342",
    ]


def replace(old, new):
    assert old in FIXTURE
    return FIXTURE.replace(old, new)


@pytest.mark.parametrize("old, new, row", [
    # Something other than an IBAN or a description on the value-date line of a named row.
    ("02.09.2026 SI56020100001234582 Flik plačilo", "02.09.2026 Flik plačilo",
     "02.09.2026 MARKO K 85,00 / 02.09.2026 Flik plačilo"),
    # An IBAN that fails its checksum.
    ("02.09.2026 SI56020100001234582", "02.09.2026 SI56020100001234583",
     "02.09.2026 MARKO K 85,00 / 02.09.2026 SI56020100001234583 Flik plačilo"),
    # A first line without an amount.
    ("02.09.2026 MARKO K 85,00", "02.09.2026 MARKO K", "02.09.2026 MARKO K / 02.09.2026 SI56020100001234582 Flik plačilo"),
    # A row with no value-date line.
    ("30.09.2026 Pozitivne obresti\n", "", "30.09.2026 0,02"),
    # Text outside a section.
    ("PRILIVI\n", "PRILIVI ALI ODLIVI\n", "PRILIVI ALI ODLIVI"),
])
def test_sparkasse_rejects_an_unrecognised_row(old, new, row):
    with pytest.raises(ParseError) as error:
        parse_pdf_text(replace(old, new))

    assert str(error.value) == f"unsupported row: {row}"


def test_a_pdf_of_another_bank_is_rejected():
    with pytest.raises(ParseError) as error:
        parse_pdf_text("Bank Statement Nr. 05/2026\n01.05.2026 until 31.05.2026\n")

    assert str(error.value) == "This PDF is not a Statement of a supported bank."


def test_sparkasse_joins_a_wrapped_iban_even_when_its_first_part_passes_the_checksum():
    # LT IBANs have 20 characters; both "LT40325000000000002" and "LT403250000000000028" pass mod-97.
    text = replace("10.09.2026 LT63325000123456789 Prenos sredstev\n0\n", "10.09.2026 LT40325000000000002 Prenos sredstev\n8\n")

    row = parse_pdf_text(text).rows[5]

    assert (row.counterparty_iban, row.raw["purpose"]) == ("LT403250000000000028", "Prenos sredstev")


@pytest.mark.parametrize("old, new, row", [
    # A page header between a row's lines.
    ("ZAVAROVANJE SLOVENIJE\n", "BANKA SPARKASSE, d. d.\nZAVAROVANJE SLOVENIJE\n",
     "15.09.2026 ZAVOD ZA ZDRAVSTVENO 1.250,00 SI00 15092026-10001 / BANKA SPARKASSE, d. d. / "
     "ZAVAROVANJE SLOVENIJE / 15.09.2026 SI56011006000012342"),
    ("kupoprodajnih poslov\n", "kupoprodajnih poslov\nPromet na TRR 340001234567864 v EUR\n",
     "15.09.2026 DARS d.d. 16,00 SI12 7112600100002 / 15.09.2026 SI56051008000123473 Poravnava / "
     "kupoprodajnih poslov / Promet na TRR 340001234567864 v EUR"),
    # An amount where only the rest of a name can be.
    ("ZAVAROVANJE SLOVENIJE\n", "ZAVAROVANJE SLOVENIJE 12,00\n",
     "15.09.2026 ZAVOD ZA ZDRAVSTVENO 1.250,00 SI00 15092026-10001 / ZAVAROVANJE SLOVENIJE 12,00 / "
     "15.09.2026 SI56011006000012342"),
])
def test_sparkasse_rejects_statement_text_inside_a_row(old, new, row):
    with pytest.raises(ParseError) as error:
        parse_pdf_text(replace(old, new))

    assert str(error.value) == f"unsupported row: {row}"
