import re
from datetime import date
from decimal import Decimal

import pytest
from django.http import QueryDict
from django.utils.http import urlencode

from dashboard import queries
from dashboard.periods import Period
from dashboard.queries import Filters
from ledger import facets
from ledger.models import Account, Category, Source, Subcategory, Transaction

pytestmark = pytest.mark.django_db


@pytest.fixture
def homes(django_user_model):
    """Ana's and Luka's own Accounts and a Joint one."""
    ana = django_user_model.objects.create_user(username="ana", first_name="Ana")
    luka = django_user_model.objects.create_user(username="luka", first_name="Luka")
    accounts = {
        "ana": Account.objects.create(name="Ana · N26", bank="n26"),
        "luka": Account.objects.create(name="Luka · Revolut", bank="revolut"),
        "joint": Account.objects.create(name="Joint · Sparkasse", bank="sparkasse"),
    }
    accounts["ana"].owners.set([ana])
    accounts["luka"].owners.set([luka])
    accounts["joint"].owners.set([ana, luka])
    return {"ana": ana, "luka": luka, **{f"{k}_account": v for k, v in accounts.items()}}


def add(account, day, amount, description, **outcome):
    return Transaction.objects.create(
        account=account, date=day, amount=Decimal(amount), description=description, **outcome
    )


def choice(**params):
    query = QueryDict(mutable=True)
    for key, value in params.items():
        query[key] = str(value)
    return facets.Choice.from_query(query)


def shown(c):
    return [t.description for t in facets.rows(c)]


def test_the_period_and_the_member_narrow_the_rows(homes):
    add(homes["ana_account"], date(2026, 9, 3), "-10", "Ana in September")
    add(homes["ana_account"], date(2026, 8, 3), "-10", "Ana in August")
    add(homes["luka_account"], date(2026, 9, 5), "-10", "Luka in September")

    assert shown(choice(period="2026-09")) == ["Luka in September", "Ana in September"]
    assert shown(choice(period="2026-09", member=homes["ana"].pk)) == ["Ana in September"]


@pytest.fixture
def groceries():
    return Subcategory.objects.get(category__name="Food", name="Groceries")


def test_the_outcome_narrows_to_awaiting_review_a_transfer_a_category_or_a_subcategory(
    homes, groceries
):
    account = homes["ana_account"]
    add(account, date(2026, 9, 1), "-10", "Unresolved")
    add(account, date(2026, 9, 2), "-20", "Moved", is_transfer=True, source=Source.IBAN)
    add(account, date(2026, 9, 3), "-30", "Groceries", subcategory=groceries, source=Source.RULE)
    other_food = groceries.category.subcategories.exclude(pk=groceries.pk).first()
    add(
        account, date(2026, 9, 4), "-40", "Other food", subcategory=other_food, source=Source.MANUAL
    )
    food = groceries.category

    assert shown(choice(outcome="unresolved")) == ["Unresolved"]
    assert shown(choice(outcome="transfer")) == ["Moved"]
    assert shown(choice(outcome=f"category-{food.pk}")) == ["Other food", "Groceries"]
    assert shown(choice(outcome=f"subcategory-{groceries.pk}")) == ["Groceries"]


def test_decided_narrows_to_what_set_the_outcome(homes, groceries):
    account = homes["ana_account"]
    add(account, date(2026, 9, 2), "-20", "By IBAN", is_transfer=True, source=Source.IBAN)
    add(account, date(2026, 9, 3), "-30", "By Rule", subcategory=groceries, source=Source.RULE)

    assert shown(choice(source="rule")) == ["By Rule"]
    assert shown(choice(source="iban")) == ["By IBAN"]


def test_the_amount_narrows_by_direction_and_by_size_either_way(homes):
    account = homes["ana_account"]
    add(account, date(2026, 9, 1), "-5.00", "Small out")
    add(account, date(2026, 9, 2), "-50.00", "Big out")
    add(account, date(2026, 9, 3), "50.00", "Big in")

    assert shown(choice(dir="out")) == ["Big out", "Small out"]
    assert shown(choice(dir="in")) == ["Big in"]
    assert shown(choice(min="10")) == ["Big in", "Big out"]
    assert shown(choice(max="10,5")) == ["Small out"]
    assert shown(choice(dir="out", min="50", max="50")) == ["Big out"]


def test_search_and_the_review_queues_decided_just_now(homes):
    account = homes["ana_account"]
    shop = add(account, date(2026, 9, 1), "-5", "Corner Shop")
    add(account, date(2026, 9, 2), "-5", "Čevljar")
    other = add(account, date(2026, 9, 3), "-5", "Hiša kave")

    assert shown(choice(q="cevljar")) == ["Čevljar"]
    assert shown(choice(decided=f"{shop.pk},{other.pk}")) == ["Hiša kave", "Corner Shop"]


def test_unreadable_values_are_ignored(homes):
    add(homes["ana_account"], date(2026, 9, 1), "-5", "Corner Shop")

    assert shown(choice(outcome="nonsense", source="x", dir="up", min="ten", decided="1,a")) == [
        "Corner Shop"
    ]


def test_each_option_counts_what_it_would_give_with_the_other_facets_held(
    homes, groceries, django_assert_max_num_queries
):
    ana, luka, joint = (homes[f"{k}_account"] for k in ("ana", "luka", "joint"))
    food = groceries.category
    add(ana, date(2026, 9, 1), "-10", "a", subcategory=groceries, source=Source.RULE)
    add(ana, date(2026, 9, 2), "-10", "b")
    add(ana, date(2026, 8, 2), "-10", "c", is_transfer=True, source=Source.IBAN)
    add(luka, date(2026, 9, 3), "-10", "d", subcategory=groceries, source=Source.MANUAL)
    add(joint, date(2026, 7, 3), "-10", "e")
    ana_key, luka_key = str(homes["ana"].pk), str(homes["luka"].pk)

    with django_assert_max_num_queries(8):
        counts = facets.counts(choice(period="2026-09", member=ana_key))

    # Every Member's count holds September, and every month's holds Ana. An option that gives none isn't listed.
    assert counts["member"] == {"": 3, ana_key: 2, luka_key: 1}
    assert counts["period"] == {"": 3, "2026-09": 2, "2026-08": 1}
    assert counts["account"] == {"": 2, str(ana.pk): 2}
    assert counts["outcome"] == {
        "": 2,
        "unresolved": 1,
        f"category-{food.pk}": 1,
        f"subcategory-{groceries.pk}": 1,
    }
    assert counts["source"] == {"": 2, "rule": 1}


def test_the_counts_hold_the_search_the_amount_and_decided_just_now(homes):
    account = homes["ana_account"]
    shop = add(account, date(2026, 9, 1), "-5", "Corner Shop")
    add(account, date(2026, 9, 2), "-50", "Corner Shop")
    add(account, date(2026, 9, 3), "-5", "Hiša kave")

    assert facets.counts(choice(q="corner", max="10"))["period"] == {"": 1, "2026-09": 1}
    assert facets.counts(choice(decided=str(shop.pk)))["outcome"][""] == 1


def test_a_choice_writes_back_the_query_it_was_read_from(homes):
    query = (
        f"period=2026-09&member={homes['ana'].pk}&account={homes['ana_account'].pk}"
        "&outcome=unresolved&source=rule&dir=out&min=10.5&max=20&q=hofer&decided=3%2C4"
        "&dashboard=period%3D2026-09&from=spending&mark=awaiting"
    )

    assert facets.Choice.from_query(QueryDict(query)).query() == query
    assert choice().query() == ""


def test_changing_the_period_the_member_or_the_outcome_leaves_the_dashboards_mark(homes):
    drilled = choice(
        period="2026-09", outcome="unresolved", **{"from": "spending", "mark": "awaiting"}
    )

    assert drilled.query(direction="out") == (
        "period=2026-09&outcome=unresolved&dir=out&from=spending&mark=awaiting"
    )
    assert drilled.query(period=None) == "outcome=unresolved"
    assert drilled.query(outcome="") == "period=2026-09"


@pytest.mark.parametrize(
    ("view", "key"),
    [
        ("spending", "food"),
        ("spending", "awaiting"),
        ("trends", "food:2026-09"),
        ("trends", "awaiting"),
        ("per_member", "ana:food"),
        ("per_member", "joint:awaiting"),
        ("money_flow", "food"),
        ("money_flow", "in:salary"),
        ("money_flow", "in:awaiting"),
    ],
)
def test_a_marks_transactions_link_lists_just_what_its_drill_down_does(household, view, key):
    keys = {
        "food": str(Category.objects.get(name="Food").pk),
        "salary": str(Subcategory.objects.get(name="Salary").pk),
        "ana": str(household["ana"].pk),
    }
    key = re.sub(r"food|salary|ana", lambda m: keys[m[0]], key)
    period = Period.month(2026, 9) if view != "trends" else Period.last12(2026, 10)
    filters = Filters()

    params = queries.transactions_params(view, period, filters, key)

    assert params is not None
    linked = facets.rows(facets.Choice.from_query(QueryDict(urlencode(params))))
    assert set(linked) == set(queries.drill_down(view, period, filters, key))


@pytest.mark.parametrize(
    ("view", "key"), [("cashflow", "2026-09"), ("money_flow", "household"), ("money_flow", "in")]
)
def test_a_mark_the_facets_cant_name_has_no_transactions_link(household, view, key):
    assert queries.transactions_params(view, Period.month(2026, 9), Filters(), key) is None


def test_a_marks_transactions_link_keeps_the_dashboards_filters(household):
    joint = Account.objects.get(name="Joint Revolut")
    filters = Filters(member="joint", accounts=frozenset([joint.pk]))

    assert queries.transactions_params("spending", Period.month(2026, 9), filters, "awaiting") == [
        ("period", "2026-09"),
        ("member", "joint"),
        ("account", str(joint.pk)),
        ("outcome", "unresolved"),
        ("dir", "out"),
    ]


def test_the_totals_count_every_row_but_leave_transfers_out_of_money_out_and_in(homes):
    account = homes["ana_account"]
    add(account, date(2026, 9, 1), "-12.50", "Shop")
    add(account, date(2026, 9, 2), "30.00", "Refund")
    add(account, date(2026, 9, 3), "-500.00", "To savings", is_transfer=True)

    assert facets.totals(choice()) == (3, Decimal("12.50"), Decimal("30.00"))
    assert facets.totals(choice(q="nothing")) == (0, Decimal(0), Decimal(0))
