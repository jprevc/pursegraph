from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest

from ledger.parsers import ParseError, Totals, parse_pdf_text

FIXTURE = (Path(__file__).parent / "fixtures" / "otp.txt").read_text()


def test_otp_statement():
    statement = parse_pdf_text(FIXTURE)

    assert statement.bank == "otp_si"
    assert statement.iban == "SI56040010012345664"
    assert statement.period_start == date(2026, 8, 1)
    assert statement.period_end == date(2026, 8, 31)
    assert statement.opening_balance == Decimal("2500.00")
    assert statement.closing_balance == Decimal("707.22")
    assert statement.printed_totals == Totals(
        money_in=Decimal("2453.09"), money_out=Decimal("4245.87")
    )
    assert statement.skipped_count == 0


def test_otp_rows():
    rows = parse_pdf_text(FIXTURE).rows

    assert [
        (
            r.date,
            r.amount,
            r.description,
            r.counterparty_name,
            r.counterparty_iban,
            r.reference,
            r.is_fee,
        )
        for r in rows
    ] == [
        (date(2026, 8, 3), Decimal("-17.91"), *["INTERSPAR KRANJ"] * 2, "", "", False),
        (date(2026, 8, 2), Decimal("-11.49"), "knjiga za šolo", "MARKO K.", "", "", False),
        (date(2026, 8, 5), Decimal("-20.00"), *["1616000011/GLAVNA ULICA"] * 2, "", "", False),
        (date(2026, 8, 5), Decimal("-0.75"), *["PROVIZIJA ZA DVIG GOTOVINE"] * 2, "", "", True),
        (date(2026, 8, 5), Decimal("108.00"), "AMAZON - PLOŠČA", "PETRA S.", "", "", False),
        (
            date(2026, 8, 13),
            Decimal("61.23"),
            "OTROŠKI DODATEK",
            "ZAVOD ZA - OTROSKI DODATEK 2",
            "SI56011006000012342",
            "SI0011692433-63888",
            False,
        ),
        (
            date(2026, 8, 14),
            Decimal("2263.36"),
            "PLAČA",
            "ACME-NEPOSREDNA PLACILA IZ NASL.-SN",
            "SI56011006000045613",
            "SI0014082026-20801",
            False,
        ),
        (date(2026, 8, 23), Decimal("-100.00"), ":/", "Luka P.", "", "", False),
        (
            date(2026, 8, 27),
            Decimal("-4000.00"),
            "BROKER EUROPE IRELAND LIMITED;PLAČILO",
            "BROKER EUROPE IRELAND LIMITED",
            "DE30501108001234567890",
            "",
            False,
        ),
        (
            date(2026, 8, 28),
            Decimal("-12.00"),
            "ZAVOD KNJIGARNA CELJE;KNJIGA PLAČILO",
            "ZAVOD KNJIGARNA CELJE",
            "SI56610000012345634",
            "SI00282026",
            False,
        ),
        (
            date(2026, 8, 29),
            Decimal("17.00"),
            "Nakazilo",
            "KOVAČ MAJA",
            "SI56610000098765456",
            "",
            False,
        ),
        (
            date(2026, 8, 29),
            Decimal("-5.00"),
            "Plačilo na račun člana društva.",
            "Društvo Primer, d.d.",
            "SI56040010011111145",
            "",
            False,
        ),
        (date(2026, 8, 29), Decimal("3.50"), "vračilo - sladoled", "TINA R.", "", "", False),
        (
            date(2026, 8, 30),
            Decimal("-3.50"),
            "ZAVOD ZA KAKOVOST;RAČUN ZA JULIJ 2026",
            "ZAVOD ZA KAKOVOST",
            "SI56029220022222210",
            "",
            False,
        ),
        (date(2026, 8, 31), Decimal("-41.24"), *["HOFER hvala"] * 2, "", "", False),
        (date(2026, 8, 31), Decimal("-27.98"), *["C & A Kranj Jug 803"] * 2, "", "", False),
        (
            date(2026, 8, 31),
            Decimal("-6.00"),
            "MESEČNI STROŠKI VODENJA OSEBNEGA RAČUNA",
            "OTP BANKA D.D.",
            "SI56040007000012313",
            "",
            True,
        ),
    ]
    assert [r.running_balance for r in rows[:2]] == [Decimal("2482.09"), Decimal("2470.60")]


def test_otp_raw_keeps_the_value_date_phone_number_and_purpose():
    rows = parse_pdf_text(FIXTURE).rows

    assert rows[0].raw["value_date"] == "2026-07-28"
    assert rows[0].raw["transaction_id"] == "2600000001"
    assert rows[1].raw["phone"] == "0038641000001"
    assert rows[7].raw["phone"] == "0038641000003"
    assert rows[5].raw["purpose_code"] == "BECH"
    assert rows[8].raw["purpose"] == "PLAČILO"
    assert rows[8].raw["purpose_code"] == "GDSV"
    assert rows[9].raw["purpose"] == "KNJIGA PLAČILO"
    assert rows[10].raw["purpose_code"] == "OTHR"
    assert rows[12].raw["phone"] == "0038641000004"


def test_a_row_booked_after_the_period_is_dated_by_its_value_date():
    row = parse_pdf_text(FIXTURE).rows[15]

    assert row.date == date(2026, 8, 31)
    assert row.raw["booking_date"] == "2026-09-02"


def test_the_layout_texts_trailing_spaces_are_ignored():
    text = "\n".join(line + "   " for line in FIXTURE.splitlines())

    assert parse_pdf_text(text) == parse_pdf_text(FIXTURE)


@pytest.mark.parametrize(
    "old, new",
    [
        # A payer label the parser doesn't know.
        ("Prejemnik: MARKO K.", "Plačnik: MARKO K."),
        # An amount that doesn't move the running balance by itself.
        ("17,91       2.482,09", "17,92       2.482,09"),
        # A payee's IBAN that fails its check.
        ("0600 0045 613", "0600 0045 614"),
        # A card payment with more lines than the holder's address.
        (
            "                     1000 LJUBLJANA\n       02.08",
            "     X\n     1000 LJUBLJANA\n       02.08",
        ),
        # Text before the first row.
        (
            "       Datum knj transakcije Plačnik/Prejemnik Breme Dobro Stanje Opis\n       28.07",
            "  Prenos\n       28.07",
        ),
        # A stray line after a Flik payment's empty reference.
        (
            "0038641000002\n                      Ref.:\n",
            "0038641000002\n                      Ref.:\n   X1\n",
        ),
        # A description going on past the booking-date line.
        ("                     342\n", "                     342              DODATEK\n"),
        # A card payment with a shorter address than the holder's.
        (
            "                     GLAVNA ULICA 1\n                     1000 LJUBLJANA\n       02.08",
            "                     1000 LJUBLJANA\n       02.08",
        ),
        # An amount where a card payment's address goes.
        (
            "                     1000 LJUBLJANA\n       02.08",
            "                     1000 LJUBLJANA 3,00\n       02.08",
        ),
        # A booking-date line missing.
        ("       05.08.2026\n       05.08.2026 2600000005", "       05.08.2026 2600000005"),
    ],
)
def test_a_row_the_parser_doesnt_recognise_is_rejected(old, new):
    assert FIXTURE.count(old) == 1

    with pytest.raises(ParseError, match="^unsupported row: "):
        parse_pdf_text(FIXTURE.replace(old, new))


def test_a_block_in_another_currency_is_rejected():
    text = FIXTURE.replace("      VALUTA: EUR", "      VALUTA: USD", 1)

    with pytest.raises(ParseError, match="^unsupported row: VALUTA: USD$"):
        parse_pdf_text(text)


def test_the_period_is_the_one_the_statement_prints():
    text = FIXTURE.replace("Datum pre. izpiska: 31.07.2026", "Datum pre. izpiska: 30.06.2026")

    statement = parse_pdf_text(text)

    assert (statement.period_start, statement.period_end) == (date(2026, 8, 1), date(2026, 8, 31))


def test_a_period_across_new_year_starts_in_the_year_before():
    text = FIXTURE.replace("ZA OBDOBJE OD 01.08-31.08.2026", "ZA OBDOBJE OD 15.12-14.01.2027")

    statement = parse_pdf_text(
        text.replace("Datum izpiska: 31.08.2026", "Datum izpiska: 14.01.2027")
    )

    assert (statement.period_start, statement.period_end) == (date(2026, 12, 15), date(2027, 1, 14))
