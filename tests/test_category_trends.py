import html
import re
from datetime import date

import pytest

from ledger.models import Category

from .conftest import EUR, drill_rows, view_chart, view_table

pytestmark = pytest.mark.django_db

TODAY = date(2026, 10, 15)


@pytest.fixture(autouse=True)
def today(monkeypatch):
    monkeypatch.setattr("dashboard.periods.today", lambda: TODAY)


def category_key(name):
    return str(Category.objects.get(name=name).pk)


def test_category_trends_default_to_the_12_months_ending_with_the_last_full_month(
    logged_in_client, household
):
    page = logged_in_client.get("/trends/").content.decode()

    assert "Category trends" in page
    assert "1 Oct 2025 – 30 Sep 2026" in page
    assert "so far, to" not in page
    table = view_table(page)
    assert [row[0] for row in table] == ["Food", "Shopping", "Awaiting review"]
    zeros = [f"0,00{EUR}"] * 10
    assert table[0] == ["Food", *zeros, f"999,00{EUR}", f"180,00{EUR}", f"1.179,00{EUR}"]
    assert table[1] == ["Shopping", *zeros, f"0,00{EUR}", f"70,00{EUR}", f"70,00{EUR}"]
    assert table[2] == ["Awaiting review", *zeros, f"0,00{EUR}", f"12,30{EUR}", f"12,30{EUR}"]


def test_the_chart_draws_one_line_per_category(logged_in_client, household):
    page = logged_in_client.get("/trends/", {"period": "2026-Q3"}).content.decode()

    chart = view_chart(page, "trends")
    assert chart["months"] == ["Jul 2026", "Aug 2026", "Sep 2026"]
    assert [(line["name"], line["data"]) for line in chart["lines"]] == [
        ("Food", [0, 999, 180]),
        ("Shopping", [0, 0, 70]),
        ("Awaiting review", [0, 0, 12.3]),
    ]
    assert chart["lines"][0]["keys"] == [
        f"{category_key('Food')}:2026-07",
        f"{category_key('Food')}:2026-08",
        f"{category_key('Food')}:2026-09",
    ]
    assert chart["drill"] == "/trends/transactions/?period=2026-Q3&key="


def test_an_explicit_period_overrides_the_default(logged_in_client, household):
    page = logged_in_client.get("/trends/", {"period": "2026-Q3"}).content.decode()

    assert view_table(page)[0] == [
        "Food",
        f"0,00{EUR}",
        f"999,00{EUR}",
        f"180,00{EUR}",
        f"1.179,00{EUR}",
    ]


def test_a_month_shows_the_12_months_ending_with_it(logged_in_client, household):
    page = logged_in_client.get("/trends/", {"period": "2026-09"}).content.decode()

    assert "1 Oct 2025 – 30 Sep 2026" in page
    assert len(view_chart(page, "trends")["months"]) == 12
    assert [label for _, selected, label in period_options(page) if selected] == ["Last 12 months"]


def table_head(page):
    return [
        html.unescape(c)
        for c in re.findall(r"<th[^>]*>([^<]*)</th>", page.split("<thead>")[1].split("</thead>")[0])
    ]


def test_the_tables_month_columns_drop_the_year(logged_in_client, household):
    page = logged_in_client.get("/trends/").content.decode()

    assert table_head(page) == [
        "Category",
        *["Oct", "Nov", "Dec", "Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep"],
        "Total",
    ]


def test_a_period_longer_than_a_year_keeps_the_year_in_its_columns(logged_in_client, household):
    page = logged_in_client.get(
        "/trends/", {"from": "2025-09-01", "to": "2026-10-31"}
    ).content.decode()

    assert table_head(page)[1:3] == ["Sep 2025", "Oct 2025"]


def test_drill_down_into_a_point_or_a_whole_line(logged_in_client, household):
    url = "/trends/transactions/"
    params = {"period": "2026-Q3"}
    food = category_key("Food")

    assert drill_rows(logged_in_client, url, {**params, "key": f"{food}:2026-09"}) == [
        "Mercator", "Gostilna", "Spar",
    ]  # fmt: skip
    assert drill_rows(logged_in_client, url, {**params, "key": food}) == [
        "August groceries", "Mercator", "Gostilna", "Spar",
    ]  # fmt: skip
    assert drill_rows(logged_in_client, url, {**params, "key": "awaiting:2026-09"}) == [
        "Unknown shop"
    ]


def period_options(page):
    select = re.search(r'<select name="period"[^>]*>(.*?)</select>', page, re.S)
    assert select, "no period selector"
    return re.findall(r'<option value="([^"]*)"( selected)?>([^<]*)</option>', select[1])


@pytest.mark.parametrize("url", ["/spending/", "/cashflow/", "/per-member/", "/money-flow/"])
def test_the_other_views_still_offer_a_month(logged_in_client, household, url):
    page = logged_in_client.get(url).content.decode()

    assert "Month" in [label for _, _, label in period_options(page)]


def test_the_period_selector_offers_no_month(logged_in_client, household):
    page = logged_in_client.get("/trends/").content.decode()

    assert [(value, label) for value, _, label in period_options(page)] == [
        ("2026-Q3", "Quarter"),
        ("2026", "Year"),
        ("last12-2026-09", "Last 12 months"),
        ("2025-10-01..2026-09-30", "Custom range"),
    ]


def test_a_months_drill_down_reaches_beyond_the_month(logged_in_client, household):
    food = category_key("Food")
    rows = drill_rows(logged_in_client, "/trends/transactions/", {"period": "2026-09", "key": food})

    assert rows == ["August groceries", "Mercator", "Gostilna", "Spar"]
