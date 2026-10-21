import json
import re
from datetime import date

import pytest

from ledger.models import Account, Subcategory, Transaction

from .conftest import EUR

pytestmark = pytest.mark.django_db

TODAY = date(2026, 10, 15)


@pytest.fixture(autouse=True)
def today(monkeypatch):
    monkeypatch.setattr("dashboard.periods.today", lambda: TODAY)
    return TODAY


def subcategory(category, name):
    return Subcategory.objects.get(category__name=category, name=name)


@pytest.fixture
def household(member):
    """September 2026 for a Household with two Accounts, plus a Transaction either side of the month."""
    current = Account.objects.create(name="Ana's Sparkasse", bank="sparkasse_si")
    current.owners.add(member)
    savings = Account.objects.create(name="Joint N26", bank="n26")
    groceries = subcategory("Food", "Groceries")
    restaurants = subcategory("Food", "Restaurants & cafés")
    shopping = subcategory("Shopping", "Other")
    salary = subcategory("Income", "Salary")
    rows = [
        (current, date(2026, 9, 1), "-80.00", "Mercator", groceries, False),
        (current, date(2026, 9, 5), "-40.50", "Gostilna", restaurants, False),
        (current, date(2026, 9, 9), "-100.00", "Shoe shop", shopping, False),
        (current, date(2026, 9, 12), "30.00", "Shoe shop refund", shopping, False),
        (current, date(2026, 9, 15), "2000.00", "Salary", salary, False),
        (current, date(2026, 9, 20), "-500.00", "To Joint N26", None, True),
        (savings, date(2026, 9, 20), "500.00", "From Ana's Sparkasse", None, True),
        (current, date(2026, 9, 25), "-12.30", "Unknown shop", None, False),
        (current, date(2026, 9, 26), "45.00", "Unknown payment in", None, False),
        (current, date(2026, 8, 31), "-999.00", "August groceries", groceries, False),
        (current, date(2026, 10, 1), "-777.00", "October groceries", groceries, False),
    ]
    for account, day, amount, description, outcome, is_transfer in rows:
        Transaction.objects.create(
            account=account,
            date=day,
            amount=amount,
            description=description,
            subcategory=outcome,
            is_transfer=is_transfer,
            source="manual" if outcome or is_transfer else "",
        )


def spending_table(page):
    """The table beside the chart, as {Category: amount}, in the order shown."""
    return dict(
        re.findall(
            r'<tr class="category"[^>]*>\s*<td>([^<]*)</td>\s*<td class="num">([^<]*)</td>', page
        )
    )


def chart_data(page):
    data = re.search(r'<script id="spending-data" type="application/json">(.*?)</script>', page)
    assert data, "no chart data"
    return json.loads(data[1])


def drill_rows(client, params):
    page = client.get("/spending/transactions/", params).content.decode()
    return re.findall(
        r'<tr id="transaction-\d+">\s*<td>[^<]*</td><td>[^<]*</td><td>([^<]*)</td>', page
    )


def test_dashboard_lands_on_spending_by_category_for_the_last_complete_month(
    logged_in_client, household
):
    page = logged_in_client.get("/").content.decode()

    assert "Spending by Category" in page
    assert "September 2026" in page
    assert "so far" not in page
    assert list(spending_table(page)) == ["Food", "Shopping", "Awaiting review"]


def test_spending_nets_refunds_and_leaves_out_transfers_and_income(logged_in_client, household):
    page = logged_in_client.get("/spending/", {"period": "2026-09"}).content.decode()

    table = spending_table(page)
    assert list(table) == ["Food", "Shopping", "Awaiting review"]
    assert table == {
        "Food": f"120,50{EUR}",
        "Shopping": f"70,00{EUR}",
        "Awaiting review": f"12,30{EUR}",
    }
    assert "Income" not in table
    assert "Total" in page and f"202,80{EUR}" in page


def test_the_chart_shows_the_same_numbers_as_the_table(logged_in_client, household):
    page = logged_in_client.get("/spending/", {"period": "2026-09"}).content.decode()

    data = chart_data(page)
    assert [(bar["name"], bar["value"]) for bar in data["bars"]] == [
        ("Food", 120.5),
        ("Shopping", 70.0),
        ("Awaiting review", 12.3),
    ]


def test_subcategories_are_listed_under_their_category(logged_in_client, household):
    page = logged_in_client.get("/spending/", {"period": "2026-09"}).content.decode()

    subcategories = re.findall(
        r'<tr class="subcategory"[^>]*>\s*<td>([^<]*)</td>\s*<td class="num">([^<]*)</td>', page
    )
    assert subcategories == [
        ("Groceries", f"80,00{EUR}"),
        ("Restaurants &amp; cafés", f"40,50{EUR}"),
        ("Other", f"70,00{EUR}"),
    ]


@pytest.mark.parametrize(
    ("period", "label", "previous", "following"),
    [
        ("2026-09", "September 2026", "2026-08", "2026-10"),
        ("2026-Q3", "Q3 2026", "2026-Q2", "2026-Q4"),
        ("2025", "2025", "2024", "2026"),
        ("last12-2026-09", "1 Oct 2025 – 30 Sep 2026", "last12-2026-08", "last12-2026-10"),
        (
            "2026-09-10..2026-09-19",
            "10–19 Sep 2026",
            "2026-08-31..2026-09-09",
            "2026-09-20..2026-09-29",
        ),
    ],
)
def test_period_units_and_their_arrows(
    logged_in_client, household, period, label, previous, following
):
    page = logged_in_client.get("/spending/", {"period": period}).content.decode()

    assert label in page
    assert f"period={previous}" in page
    assert f"period={following}" in page


def test_the_period_selector_offers_every_unit(logged_in_client, household):
    page = logged_in_client.get("/spending/", {"period": "2026-08"}).content.decode()

    select = re.search(r'<select name="period"[^>]*>(.*?)</select>', page, re.S)
    assert select, "no period selector"
    options = re.findall(r'<option value="([^"]*)"( selected)?>([^<]*)</option>', select[1])
    assert [(value, label) for value, _, label in options] == [
        ("2026-08", "Month"),
        ("2026-Q3", "Quarter"),
        ("2026", "Year"),
        ("last12-2026-08", "Last 12 months"),
        ("2026-08-01..2026-08-31", "Custom range"),
    ]
    assert [label for _, selected, label in options if selected] == ["Month"]


def test_a_custom_range_comes_from_two_dates(logged_in_client, household):
    page = logged_in_client.get(
        "/spending/", {"from": "2026-09-01", "to": "2026-09-10"}
    ).content.decode()

    assert "1–10 Sep 2026" in page
    assert spending_table(page) == {"Food": f"120,50{EUR}", "Shopping": f"100,00{EUR}"}


def test_the_period_covers_its_whole_range(logged_in_client, household):
    page = logged_in_client.get("/spending/", {"period": "2026-Q3"}).content.decode()

    assert spending_table(page)["Food"] == f"1.119,50{EUR}"


def test_the_current_month_is_labelled_so_far(logged_in_client, household):
    page = logged_in_client.get("/spending/", {"period": "2026-10"}).content.decode()

    assert "October 2026" in page
    assert "so far, to 15 Oct 2026" in page
    assert spending_table(page) == {"Food": f"777,00{EUR}"}
    assert "period=2026-11" not in page  # nothing to step forward to


def test_a_period_that_cannot_be_read_falls_back_to_the_last_complete_month(
    logged_in_client, household
):
    page = logged_in_client.get("/spending/", {"period": "2026-13"}).content.decode()

    assert "September 2026" in page


def test_a_period_with_no_spending_says_so(logged_in_client, household):
    page = logged_in_client.get("/spending/", {"period": "2024-01"}).content.decode()

    assert "No spending in this period." in page
    assert "Import your first Statement" not in page


def test_an_htmx_request_gets_the_view_alone(logged_in_client, household):
    full = logged_in_client.get("/spending/", {"period": "2026-09"}).content.decode()
    swapped = logged_in_client.get(
        "/spending/", {"period": "2026-09"}, headers={"HX-Request": "true"}
    ).content.decode()

    assert '<div class="shell">' in full and 'id="view"' in full
    assert '<div class="shell">' not in swapped
    assert spending_table(swapped) == spending_table(full)


def test_the_view_controls_swap_the_view_via_htmx(logged_in_client, household):
    page = logged_in_client.get("/spending/", {"period": "2026-09"}).content.decode()

    assert 'hx-get="/spending/?period=2026-08"' in page
    assert 'hx-target="#view"' in page
    assert 'hx-push-url="true"' in page


def test_drill_down_lists_a_categorys_transactions_in_the_period(logged_in_client, household):
    food = subcategory("Food", "Groceries").category
    shopping = subcategory("Shopping", "Other").category

    assert drill_rows(logged_in_client, {"period": "2026-09", "category": food.pk}) == [
        "Mercator",
        "Gostilna",
    ]
    assert drill_rows(logged_in_client, {"period": "2026-09", "category": shopping.pk}) == [
        "Shoe shop",
        "Shoe shop refund",
    ]


def test_drill_down_into_awaiting_review(logged_in_client, household):
    assert drill_rows(logged_in_client, {"period": "2026-09", "category": "awaiting"}) == [
        "Unknown shop"
    ]


def test_the_chart_marks_carry_their_drill_down_address(logged_in_client, household):
    food = subcategory("Food", "Groceries").category
    page = logged_in_client.get("/spending/", {"period": "2026-09"}).content.decode()

    data = chart_data(page)
    assert data["drill"] == "/spending/transactions/?period=2026-09&category="
    assert [bar["key"] for bar in data["bars"]] == [
        str(food.pk),
        str(subcategory("Shopping", "Other").category.pk),
        "awaiting",
    ]


def test_drill_down_rows_edit_the_outcome_inline(logged_in_client, household):
    page = logged_in_client.get(
        "/spending/transactions/", {"period": "2026-09", "category": "awaiting"}
    ).content.decode()
    unknown = Transaction.objects.get(description="Unknown shop")

    assert f'hx-post="/transactions/{unknown.pk}/outcome/"' in page
    assert ">Awaiting review</option>" in page

    groceries = subcategory("Food", "Groceries")
    logged_in_client.post(
        f"/transactions/{unknown.pk}/outcome/",
        {"outcome": groceries.pk},
        headers={"HX-Request": "true"},
    )
    after = logged_in_client.get("/spending/", {"period": "2026-09"}).content.decode()
    assert spending_table(after) == {"Food": f"132,80{EUR}", "Shopping": f"70,00{EUR}"}


def test_restoring_history_gets_the_whole_page(logged_in_client, household):
    response = logged_in_client.get(
        "/spending/",
        {"period": "2026-09"},
        headers={"HX-Request": "true", "HX-History-Restore-Request": "true"},
    )

    assert '<div class="shell">' in response.content.decode()
    assert "HX-Request" in response["Vary"]


def test_the_last_day_of_a_running_period_is_still_so_far(logged_in_client, household, monkeypatch):
    monkeypatch.setattr("dashboard.periods.today", lambda: date(2026, 9, 30))

    page = logged_in_client.get("/spending/", {"period": "2026-09"}).content.decode()

    assert "so far, to 30 Sep 2026" in page


@pytest.mark.parametrize(
    "period", ["9999", "0001", "0001-01-01..9999-12-31", "last12-0001-01", "1899-12"]
)
def test_periods_at_the_edge_of_the_calendar_fall_back_to_the_default(
    logged_in_client, household, period
):
    response = logged_in_client.get("/spending/", {"period": period})

    assert response.status_code == 200
    assert "September 2026" in response.content.decode()


def test_an_empty_installation_asks_for_the_first_statement_on_every_view(logged_in_client):
    page = logged_in_client.get("/spending/").content.decode()

    assert "Import your first Statement" in page


def test_drill_down_rows_go_back_to_the_view_without_htmx(logged_in_client, household):
    page = logged_in_client.get(
        "/spending/transactions/", {"period": "2026-09", "category": "awaiting"}
    ).content.decode()

    assert '<input type="hidden" name="next" value="/spending/?period=2026-09">' in page
