"""The Dashboard's frame around every view: its title, the view tabs, the filter bar and the stat tiles, and the
Spending view's Category list and drill-down."""

import html
import json
import re
from datetime import date

import pytest

from ledger.models import Account, Category

from .conftest import EUR

pytestmark = pytest.mark.django_db

TODAY = date(2026, 10, 15)
SWAP = {"HX-Request": "true"}


@pytest.fixture(autouse=True)
def today(monkeypatch):
    monkeypatch.setattr("dashboard.periods.today", lambda: TODAY)


def text(fragment):
    return html.unescape(re.sub(r"<[^>]+>", "", fragment)).strip()


@pytest.mark.parametrize("url", ["/", "/cashflow/", "/trends/", "/per-member/", "/money-flow/"])
@pytest.mark.parametrize("headers", [{}, SWAP], ids=["page", "swap"])
def test_every_view_is_titled_dashboard(logged_in_client, household, url, headers):
    page = logged_in_client.get(url, headers=headers).content.decode()

    assert [text(h) for h in re.findall(r"<h1[^>]*>(.*?)</h1>", page, re.S)] == ["Dashboard"]


def tiles(page):
    """The stat tiles, as (label, figure, comparison) in the order shown."""
    return [
        tuple(text(part) for part in parts)
        for parts in re.findall(
            r'<div class="panel tile">\s*<p class="tile-label">(.*?)</p>\s*<p class="tile-figure fig">(.*?)</p>'
            r"\s*<p class=\"compare\">(.*?)</p>",
            page,
            re.S,
        )
    ]


def test_the_tiles_set_the_periods_figures_against_the_one_before(logged_in_client, household):
    page = logged_in_client.get("/spending/", {"period": "2026-09"}).content.decode()

    assert tiles(page) == [
        ("Spent", f"262,30{EUR}", f"736,70{EUR} less than August"),
        ("Money in", f"3.550,00{EUR}", f"2.050,00{EUR} more than August"),
        ("Net", f"+3.287,70{EUR}", f"2.786,70{EUR} more than August"),
    ]


@pytest.mark.parametrize("url", ["/cashflow/", "/trends/", "/money-flow/"])
def test_every_view_has_the_tiles_for_its_period_and_filters(logged_in_client, household, url):
    page = logged_in_client.get(url, {"period": "2026-09", "member": "joint"}).content.decode()

    assert [(label, figure) for label, figure, _compare in tiles(page)] == [
        ("Spent", f"60,00{EUR}"),
        ("Money in", f"0,00{EUR}"),
        ("Net", f"\u221260,00{EUR}"),
    ]


def test_per_member_tiles_ignore_the_member_filter_as_its_chart_does(logged_in_client, household):
    page = logged_in_client.get(
        "/per-member/", {"period": "2026-09", "member": "joint"}
    ).content.decode()

    assert tiles(page)[0][:2] == ("Spent", f"262,30{EUR}")


def test_a_comparison_names_the_year_when_it_differs_and_says_when_nothing_changed(
    logged_in_client, household
):
    january = logged_in_client.get("/spending/", {"period": "2026-01"}).content.decode()
    quarter = logged_in_client.get("/spending/", {"period": "2026-Q3"}).content.decode()

    assert tiles(january)[0] == ("Spent", f"0,00{EUR}", "Same as December 2025")
    assert tiles(quarter)[1][2] == f"5.050,00{EUR} more than Q2 2026"


def drill_down(client, url, params):
    return client.get(url, params, headers=SWAP)


def test_the_drill_down_is_a_card_titled_by_its_category_and_period(logged_in_client, household):
    food = Category.objects.get(name="Food")
    response = drill_down(
        logged_in_client, "/spending/transactions/", {"period": "2026-09", "category": food.pk}
    )
    page = response.content.decode()

    card = re.search(r'<section class="panel drill-card" ([^>]*)>', page)
    assert card and f'data-mark="{food.pk}"' in card[1]
    assert f'style="--hue: var(--cat-{(food.pk - 1) % 10})"' in card[1]
    assert [text(h) for h in re.findall(r"<h2[^>]*>(.*?)</h2>", page, re.S)] == [
        "Food · September 2026"
    ]
    assert re.search(
        r'<button type="button" class="ghost icon-button" data-close aria-label="Close">', page
    )
    assert "Changing an outcome moves the amount between Categories at once." in page
    assert json.loads(response["HX-Trigger"]) == {
        "announce": "Food, September 2026, 3 Transactions"
    }


def test_a_drill_down_into_another_views_mark_is_titled_by_its_label(logged_in_client, household):
    page = drill_down(
        logged_in_client, "/cashflow/transactions/", {"period": "2026-Q3", "key": "2026-09"}
    ).content.decode()

    assert [text(h) for h in re.findall(r"<h2[^>]*>(.*?)</h2>", page, re.S)] == [
        "Sep 2026 · Q3 2026"
    ]
    card = re.search(r"<section[^>]*>", page)
    assert card and "--hue" not in card[0]


def test_an_empty_drill_down_says_so_and_announces_none(logged_in_client, household):
    response = drill_down(
        logged_in_client, "/spending/transactions/", {"period": "2026-09", "category": "999"}
    )

    assert "No Transactions here." in response.content.decode()
    assert json.loads(response["HX-Trigger"])["announce"].endswith(", 0 Transactions")


def announced(response):
    return json.loads(response.get("HX-Trigger", "{}")).get("announce")


def test_a_view_swapped_in_announces_the_view_and_its_period(logged_in_client, household):
    swapped = logged_in_client.get("/cashflow/", {"period": "2026-09"}, headers=SWAP)
    whole = logged_in_client.get("/cashflow/", {"period": "2026-09"})

    assert announced(swapped) == "Cash flow, September 2026"
    # A page change announces nothing: its focused <h1> is read anyway.
    assert announced(whole) is None


def test_a_filtered_view_announces_whose_accounts_it_shows(logged_in_client, household, member):
    anas = Account.objects.get(name="Ana's Sparkasse")
    joint = Account.objects.get(name="Joint Revolut")

    def announcement(params):
        return announced(
            logged_in_client.get("/spending/", {"period": "2026-09", **params}, headers=SWAP)
        )

    assert announcement({"member": member.pk}) == "Spending, September 2026, ana's Accounts"
    assert announcement({"member": "joint"}) == "Spending, September 2026, Joint Accounts"
    assert announcement({"account": anas.pk}) == "Spending, September 2026, Ana's Sparkasse"
    assert announcement({"account": [anas.pk, joint.pk]}) == "Spending, September 2026, 2 Accounts"


@pytest.mark.parametrize("url", ["/cashflow/", "/trends/", "/per-member/", "/money-flow/"])
def test_a_tables_marks_open_their_drill_down_with_real_buttons(logged_in_client, household, url):
    page = logged_in_client.get(url, {"period": "2026-09"}).content.decode()

    assert 'tabindex="0"' not in page
    assert re.search(
        r'<button type="button" class="mark-open" aria-controls="drill" hx-get="[^"]+" hx-target="#drill">',
        page,
    )


def test_the_numbers_refetched_after_an_outcome_changed_announce_nothing(
    logged_in_client, household
):
    response = logged_in_client.get(
        "/spending/", {"period": "2026-09"}, headers={**SWAP, "HX-Target": "numbers"}
    )

    assert announced(response) is None
