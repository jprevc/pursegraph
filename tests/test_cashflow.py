from datetime import date

import pytest

from ledger.models import Subcategory, Transaction

from .conftest import EUR, drill_rows, view_chart, view_table

pytestmark = pytest.mark.django_db

TODAY = date(2026, 10, 15)


@pytest.fixture(autouse=True)
def today(monkeypatch):
    monkeypatch.setattr("dashboard.periods.today", lambda: TODAY)


def test_cashflow_sets_money_in_against_money_out_leaving_transfers_out(
    logged_in_client, household
):
    page = logged_in_client.get("/cashflow/", {"period": "2026-09"}).content.decode()

    assert "Cashflow" in page
    assert view_table(page) == [["Sep 2026", f"3.550,00{EUR}", f"262,30{EUR}", f"+3.287,70{EUR}"]]


def test_a_longer_period_shows_every_month_so_far(logged_in_client, household):
    page = logged_in_client.get("/cashflow/", {"period": "2026"}).content.decode()

    table = view_table(page)
    assert [row[0] for row in table] == [
        "Jan 2026", "Feb 2026", "Mar 2026", "Apr 2026", "May 2026", "Jun 2026",
        "Jul 2026", "Aug 2026", "Sep 2026", "Oct 2026",
    ]  # fmt: skip
    assert table[6] == ["Jul 2026", f"0,00{EUR}", f"0,00{EUR}", f"0,00{EUR}"]
    assert table[7] == ["Aug 2026", f"1.500,00{EUR}", f"999,00{EUR}", f"+501,00{EUR}"]
    assert table[9] == ["Oct 2026", f"0,00{EUR}", f"777,00{EUR}", f"−777,00{EUR}"]
    assert f"5.050,00{EUR}" in page  # money in over the year


def test_the_chart_shows_the_same_numbers_as_the_table(logged_in_client, household):
    page = logged_in_client.get("/cashflow/", {"period": "2026-Q3"}).content.decode()

    chart = view_chart(page, "cashflow")
    assert chart["months"] == ["Jul 2026", "Aug 2026", "Sep 2026"]
    assert chart["in"] == [0, 1500, 3550]
    assert chart["out"] == [0, 999, 262.3]
    assert chart["net"] == [0, 501, 3287.7]
    assert chart["keys"] == ["2026-07", "2026-08", "2026-09"]
    assert chart["drill"] == "/cashflow/transactions/?period=2026-Q3&key="


def test_drill_down_into_a_months_money_in_money_out_or_both(logged_in_client, household):
    url = "/cashflow/transactions/"
    params = {"period": "2026-Q3"}

    assert drill_rows(logged_in_client, url, {**params, "key": "2026-09:in"}) == [
        "Ana's salary", "Marko's salary", "Unknown payment in", "Interest",
    ]  # fmt: skip
    assert drill_rows(logged_in_client, url, {**params, "key": "2026-09:out"}) == [
        "Mercator", "Shoe shop", "Shoe shop refund", "Gostilna", "Spar", "Unknown shop",
    ]  # fmt: skip
    assert drill_rows(logged_in_client, url, {**params, "key": "2026-08"}) == [
        "Marko's August salary", "August groceries",
    ]  # fmt: skip
    assert drill_rows(logged_in_client, url, {**params, "key": "2026-10"}) == []


def test_a_transaction_dated_ahead_of_today_still_counts(logged_in_client, household):
    groceries = Subcategory.objects.get(category__name="Food", name="Groceries")
    account = Transaction.objects.get(description="Mercator").account
    Transaction.objects.create(
        account=account, date=date(2026, 11, 2), amount="-10.00", description="Pre-booked",
        subcategory=groceries, source="manual",
    )  # fmt: skip

    page = logged_in_client.get("/cashflow/", {"period": "2026-Q4"}).content.decode()

    assert view_table(page) == [
        ["Oct 2026", f"0,00{EUR}", f"777,00{EUR}", f"−777,00{EUR}"],
        ["Nov 2026", f"0,00{EUR}", f"10,00{EUR}", f"−10,00{EUR}"],
    ]
