from datetime import date

import pytest

from ledger.models import Category

from .conftest import drill_rows, view_chart, view_table

pytestmark = pytest.mark.django_db

TODAY = date(2026, 10, 15)


@pytest.fixture(autouse=True)
def today(monkeypatch):
    monkeypatch.setattr("dashboard.periods.today", lambda: TODAY)


def category_key(name):
    return str(Category.objects.get(name=name).pk)


def test_category_trends_default_to_the_last_12_months(logged_in_client, household):
    page = logged_in_client.get("/trends/").content.decode()

    assert "Category trends" in page
    assert "Nov 2025 – Oct 2026" in page
    assert "so far, to 15 Oct 2026" in page
    table = view_table(page)
    assert [row[0] for row in table] == ["Food", "Shopping", "Awaiting review"]
    zeros = ["0.00"] * 9
    assert table[0] == ["Food", *zeros, "999.00", "180.00", "777.00", "1956.00"]
    assert table[1] == ["Shopping", *zeros, "0.00", "70.00", "0.00", "70.00"]
    assert table[2] == ["Awaiting review", *zeros, "0.00", "12.30", "0.00", "12.30"]


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
    page = logged_in_client.get("/trends/", {"period": "2026-09"}).content.decode()

    assert view_table(page)[0] == ["Food", "180.00", "180.00"]


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
