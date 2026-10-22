import json
import shutil
import subprocess
from datetime import date
from decimal import Decimal

import pytest
from django.conf import settings
from django.template import Context, Template

from pursegraph import figures

NBSP = " "
MINUS = "−"


def render(expression, **context):
    return Template("{% load figures icons %}" + expression).render(Context(context))


@pytest.mark.parametrize(
    ("amount", "shown"),
    [
        (Decimal("1234.56"), f"1.234,56{NBSP}€"),
        (Decimal("-1234.56"), f"{MINUS}1.234,56{NBSP}€"),
        (Decimal("12.3"), f"12,30{NBSP}€"),
        (Decimal("1234567.891"), f"1.234.567,89{NBSP}€"),
        (Decimal("0.005"), f"0,01{NBSP}€"),
        (Decimal("-0.004"), f"0,00{NBSP}€"),
        (3287.7, f"3.287,70{NBSP}€"),
        (0, f"0,00{NBSP}€"),
    ],
)
def test_an_amount_shows_as_sl_si_euros_with_grouping_always_on(amount, shown):
    assert render("{{ amount|money }}", amount=amount) == shown


@pytest.mark.parametrize(
    ("amount", "shown"),
    [
        (Decimal("1200.40"), f"1.200{NBSP}€"),
        (Decimal("1200.50"), f"1.201{NBSP}€"),
        (Decimal("-950"), f"{MINUS}950{NBSP}€"),
        (0, f"0{NBSP}€"),
    ],
)
def test_an_axis_amount_shows_in_whole_euros(amount, shown):
    assert render("{{ amount|money_whole }}", amount=amount) == shown


@pytest.mark.parametrize(
    ("amount", "shown"),
    [
        (Decimal("3287.7"), f"+3.287,70{NBSP}€"),
        (Decimal("-12"), f"{MINUS}12,00{NBSP}€"),
        (Decimal("0"), f"0,00{NBSP}€"),
    ],
)
def test_net_carries_an_explicit_sign(amount, shown):
    assert render("{{ amount|money_signed }}", amount=amount) == shown


@pytest.mark.parametrize(
    ("fraction", "shown"),
    [(0.256, f"26{NBSP}%"), (Decimal("0.785"), f"79{NBSP}%"), (1, f"100{NBSP}%"), (0, f"0{NBSP}%")],
)
def test_a_share_shows_as_whole_percent_with_a_space(fraction, shown):
    assert render("{{ fraction|share }}", fraction=fraction) == shown


def test_nothing_shows_for_a_missing_amount():
    assert render("{{ amount|money }}|{{ amount|share }}", amount=None) == "|"


def test_a_day_is_day_first_without_leading_zeros():
    assert render("{{ d|day }}", d=date(2026, 2, 1)) == "1 Feb 2026"


@pytest.mark.parametrize(
    ("start", "end", "shown"),
    [
        (date(2026, 9, 1), date(2026, 9, 30), "1–30 Sep 2026"),
        (date(2026, 9, 28), date(2026, 10, 3), "28 Sep – 3 Oct 2026"),
        (date(2025, 12, 29), date(2026, 1, 4), "29 Dec 2025 – 4 Jan 2026"),
        (date(2026, 9, 5), date(2026, 9, 5), "5 Sep 2026"),
    ],
)
def test_a_range_drops_the_repeated_month_and_year(start, end, shown):
    assert render("{{ start|date_range:end }}", start=start, end=end) == shown


def test_a_month_is_spelled_out():
    assert render("{{ d|month }}", d=date(2026, 9, 1)) == "September 2026"


def test_a_short_month_is_abbreviated_and_drops_its_year_in_a_table_column():
    assert figures.month_short(date(2026, 9, 1)) == "Sep 2026"
    assert figures.month_short(date(2026, 9, 1), year=False) == "Sep"


AMOUNTS = [1234.56, -1234.56, 12.3, 1234567.891, 0.005, -0.004, 1200.5, -950, 0, 3287.7]
SHARES = [0.256, 0.785, 1, 0, 0.004, 0.995, -0.25, -0.004]


@pytest.mark.skipif(not shutil.which("node"), reason="needs node to run static/figures.js")
def test_the_browser_formats_amounts_exactly_as_the_server_does():
    script = f"""
        globalThis.window = globalThis;
        require({json.dumps(str(settings.BASE_DIR / "static" / "figures.js"))});
        const amounts = {json.dumps(AMOUNTS)}, shares = {json.dumps(SHARES)};
        console.log(JSON.stringify({{
            money: amounts.map(Figures.money),
            moneyWhole: amounts.map(Figures.moneyWhole),
            moneySigned: amounts.map(Figures.moneySigned),
            share: shares.map(Figures.share),
        }}));
    """
    shown = json.loads(
        subprocess.run(["node", "-e", script], capture_output=True, check=True, text=True).stdout
    )

    assert shown == {
        "money": [figures.money(v) for v in AMOUNTS],
        "moneyWhole": [figures.money_whole(v) for v in AMOUNTS],
        "moneySigned": [figures.money_signed(v) for v in AMOUNTS],
        "share": [figures.share(v) for v in SHARES],
    }


def test_an_icon_draws_its_sprite_symbol_hidden_from_assistive_technology():
    assert render('{% icon "left" %}') == (
        '<svg class="icon" aria-hidden="true" focusable="false"><use href="#i-left"></use></svg>'
    )
