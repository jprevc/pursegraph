"""A Split Transaction counts each Part's amount in that Part's Subcategory (ADR 0003): on the Dashboard, in its
drill-downs, and in the Transactions page's outcome filter and facet counts."""

from datetime import date
from decimal import Decimal

import pytest
from django.http import QueryDict

from dashboard import queries
from dashboard.periods import Period
from dashboard.queries import Filters
from ledger import facets, outcomes
from ledger.models import Category, Source, Subcategory, Transaction

from .conftest import make_account

pytestmark = pytest.mark.django_db

SEPTEMBER = Period.month(2026, 9)


def sub(category, name):
    return Subcategory.objects.get(category__name=category, name=name)


def category(name):
    return Category.objects.get(name=name)


def add(account, day, amount, description, **outcome):
    return Transaction.objects.create(
        account=account, date=day, amount=Decimal(amount), description=description, **outcome
    )


@pytest.fixture
def ana(member):
    return member


@pytest.fixture
def hypermarket(ana):
    """Ana's €80.00 purchase, split 50.00 Groceries / 30.00 Household goods."""
    t = add(make_account("Ana's N26", "n26", ana), date(2026, 9, 5), "-80.00", "INTERSPAR")
    outcomes.split(
        t,
        [
            (sub("Food", "Groceries"), Decimal("-50.00")),
            (sub("Home", "Furniture & household"), Decimal("-30.00")),
        ],
    )
    t.refresh_from_db()
    return t


@pytest.fixture
def payslip(ana):
    """Ana's €300.00 payment in, split 200.00 Salary / 100.00 Interest."""
    t = add(make_account("Ana's Revolut", "revolut", ana), date(2026, 9, 15), "300.00", "Payslip")
    outcomes.split(
        t,
        [
            (sub("Income", "Salary"), Decimal("200.00")),
            (sub("Income", "Interest"), Decimal("100.00")),
        ],
    )
    t.refresh_from_db()
    return t


def table(view):
    """A view's rows as {label: (amount, {child label: amount})}."""
    return {
        r.label: (r.amount, {c.label: c.amount for c in r.children})
        for r in queries.view_data(view, SEPTEMBER, Filters()).rows
    }


# The Dashboard


def test_spending_counts_each_part_in_its_own_category_and_nothing_awaiting_review(hypermarket):
    assert table("spending") == {
        "Food": (Decimal("50.00"), {"Groceries": Decimal("50.00")}),
        "Home": (Decimal("30.00"), {"Furniture & household": Decimal("30.00")}),
    }
    assert queries.view_data("spending", SEPTEMBER, Filters()).total == Decimal("80.00")
    assert queries.awaiting_review(SEPTEMBER, Filters()) == (Decimal(0), Decimal(0))


def test_cash_flow_counts_a_split_purchase_as_money_out(hypermarket):
    data = queries.view_data("cashflow", SEPTEMBER, Filters())

    assert (data.total.money_in, data.total.money_out) == (Decimal(0), Decimal("80.00"))
    assert [t.amount for t in queries.tiles("cashflow", SEPTEMBER, Filters())] == [
        Decimal("80.00"),
        Decimal(0),
        Decimal("-80.00"),
    ]


def test_per_member_counts_each_part_in_its_category_in_its_transactions_bucket(hypermarket, ana):
    assert table("per_member") == {
        "ana": (Decimal("80.00"), {"Food": Decimal("50.00"), "Home": Decimal("30.00")}),
    }


def test_category_trends_count_each_part_in_its_category(hypermarket):
    trends = queries.view_data("trends", SEPTEMBER, Filters()).rows

    assert {t.label: t.total for t in trends} == {
        "Food": Decimal("50.00"),
        "Home": Decimal("30.00"),
    }


def test_income_counts_each_part_in_its_own_subcategory(payslip):
    data = queries.view_data("money_flow", SEPTEMBER, Filters())
    money_in = data.rows[0]

    assert {s.label: s.amount for s in money_in.children} == {
        "Salary": Decimal("200.00"),
        "Interest": Decimal("100.00"),
    }
    cashflow = queries.view_data("cashflow", SEPTEMBER, Filters()).total
    assert (cashflow.money_in, cashflow.money_out) == (Decimal("300.00"), Decimal(0))


def counted(view, key):
    """What a drill-down lists: each Transaction's description, its counted amount and its counted Parts."""
    return [
        (
            t.description,
            t.counted,  # type: ignore[attr-defined]
            [p.subcategory.name for p in t.parts.all() if p.counted],  # type: ignore[attr-defined]
        )
        for t in queries.drill_down(view, SEPTEMBER, Filters(), key)
    ]


def test_the_drill_down_into_a_category_counts_just_its_parts(hypermarket):
    food, home = str(category("Food").pk), str(category("Home").pk)

    assert counted("spending", food) == [("INTERSPAR", Decimal("-50.00"), ["Groceries"])]
    assert counted("spending", home) == [
        ("INTERSPAR", Decimal("-30.00"), ["Furniture & household"])
    ]
    assert counted("spending", queries.AWAITING_REVIEW) == []
    assert counted("trends", f"{food}:2026-09") == [("INTERSPAR", Decimal("-50.00"), ["Groceries"])]


def test_the_drill_down_into_all_money_out_counts_every_part(hypermarket, ana):
    every = [("INTERSPAR", Decimal("-80.00"), ["Groceries", "Furniture & household"])]

    assert counted("cashflow", "2026-09:out") == every
    assert counted("per_member", str(ana.pk)) == every
    assert counted("per_member", f"{ana.pk}:{category('Home').pk}") == [
        ("INTERSPAR", Decimal("-30.00"), ["Furniture & household"])
    ]


def test_the_drill_down_into_an_income_subcategory_counts_its_part(payslip):
    salary = sub("Income", "Salary").pk

    assert counted("money_flow", f"in:{salary}") == [("Payslip", Decimal("200.00"), ["Salary"])]
    assert counted("money_flow", "in:awaiting") == []


def test_the_drill_down_total_sums_only_the_counted_parts(logged_in_client, hypermarket):
    response = logged_in_client.get(
        "/spending/transactions/", {"period": "2026-09", "category": category("Food").pk}
    )

    assert response.context["total"] == Decimal("-50.00")


def test_an_unsplit_transaction_counts_whole_in_a_drill_down(ana):
    groceries = sub("Food", "Groceries")
    add(
        make_account("Ana's N26", "n26", ana),
        date(2026, 9, 1),
        "-12.00",
        "Hofer",
        subcategory=groceries,
    )

    assert counted("spending", str(groceries.category_id)) == [("Hofer", Decimal("-12.00"), [])]


# The Transactions page


def choice(**params):
    query = QueryDict(mutable=True)
    for key, value in params.items():
        query[key] = str(value)
    return facets.Choice.from_query(query)


def shown(c):
    return [t.description for t in facets.rows(c)]


def test_filtering_by_a_category_or_subcategory_includes_a_split_with_a_part_there(hypermarket):
    groceries = sub("Food", "Groceries")

    assert shown(choice(outcome=f"subcategory-{groceries.pk}")) == ["INTERSPAR"]
    assert shown(choice(outcome=f"category-{groceries.category_id}")) == ["INTERSPAR"]
    assert shown(choice(outcome=f"category-{category('Home').pk}")) == ["INTERSPAR"]
    assert shown(choice(outcome=f"subcategory-{sub('Food', 'Restaurants & cafés').pk}")) == []
    assert shown(choice(outcome="unresolved")) == []


def test_a_category_filter_identifies_the_matching_parts(hypermarket):
    [t] = facets.rows(choice(outcome=f"category-{category('Home').pk}"))

    assert t.counted == Decimal("-30.00")  # type: ignore[attr-defined]
    assert [(p.subcategory.name, p.counted) for p in t.parts.all()] == [  # type: ignore[attr-defined]
        ("Groceries", False),
        ("Furniture & household", True),
    ]


def test_a_split_with_two_parts_in_one_category_shows_once_under_it(ana):
    t = add(make_account("Ana's N26", "n26", ana), date(2026, 9, 5), "-80.00", "Market")
    outcomes.split(
        t,
        [
            (sub("Food", "Groceries"), Decimal("-50.00")),
            (sub("Food", "Restaurants & cafés"), Decimal("-30.00")),
        ],
    )
    food = category("Food").pk

    assert shown(choice(outcome=f"category-{food}")) == ["Market"]
    assert facets.counts(choice())["outcome"][f"category-{food}"] == 1


def test_the_outcome_facet_counts_a_split_once_per_category_and_subcategory_it_touches(
    hypermarket,
):
    by_outcome = facets.counts(choice())["outcome"]

    assert by_outcome == {
        "": 1,
        f"category-{category('Food').pk}": 1,
        f"category-{category('Home').pk}": 1,
        f"subcategory-{sub('Food', 'Groceries').pk}": 1,
        f"subcategory-{sub('Home', 'Furniture & household').pk}": 1,
    }


def test_amount_direction_and_source_use_the_whole_split_transaction(hypermarket):
    assert shown(choice(min="60", max="100")) == ["INTERSPAR"]
    assert shown(choice(min="40", max="55")) == []
    assert shown(choice(dir="out")) == ["INTERSPAR"]
    assert facets.counts(choice())["source"] == {"": 1, Source.MANUAL: 1}


def test_the_drill_down_into_a_category_lists_a_split_with_two_parts_there_once(ana):
    t = add(make_account("Ana's N26", "n26", ana), date(2026, 9, 5), "-80.00", "Market")
    outcomes.split(
        t,
        [
            (sub("Food", "Groceries"), Decimal("-50.00")),
            (sub("Food", "Restaurants & cafés"), Decimal("-30.00")),
        ],
    )

    assert counted("spending", str(category("Food").pk)) == [
        ("Market", Decimal("-80.00"), ["Groceries", "Restaurants & cafés"])
    ]


def test_the_summary_counts_only_the_parts_in_the_chosen_category_or_subcategory(
    hypermarket, payslip
):
    groceries = sub("Food", "Groceries")

    assert facets.totals(choice(outcome=f"category-{groceries.category_id}")) == (
        1,
        Decimal("50.00"),
        Decimal(0),
    )
    assert facets.totals(choice(outcome=f"subcategory-{sub('Income', 'Interest').pk}")) == (
        1,
        Decimal(0),
        Decimal("100.00"),
    )
    assert facets.totals(choice()) == (2, Decimal("80.00"), Decimal("300.00"))
