import html
import re
from datetime import date

import pytest

from ledger.models import Category, Subcategory, Transaction

from .conftest import EUR, drill_rows, view_chart

pytestmark = pytest.mark.django_db

TODAY = date(2026, 10, 15)


@pytest.fixture(autouse=True)
def today(monkeypatch):
    monkeypatch.setattr("dashboard.periods.today", lambda: TODAY)


def category_key(name):
    return str(Category.objects.get(name=name).pk)


def income_key(name):
    return f"in:{Subcategory.objects.get(category__name='Income', name=name).pk}"


def flow_table(page):
    """Each group of the table, Money in and Money out, with its lines, then the balance line."""
    rows = re.findall(r'<tr class="(mark|subcategory|balance)"[^>]*>(.*?)</tr>', page, re.S)
    return [
        (
            kind,
            *[
                html.unescape(c)
                for c in re.findall(r"<td[^>]*>(?:<button[^>]*>)?([^<]*)(?:</button>)?</td>", cells)
            ],
        )
        for kind, cells in rows
    ]


def test_money_flow_runs_from_income_to_categories(logged_in_client, household):
    page = logged_in_client.get("/money-flow/", {"period": "2026-09"}).content.decode()

    assert "Money flow" in page
    assert flow_table(page) == [
        ("mark", "Money in", f"3.550,00{EUR}"),
        ("subcategory", "Salary", f"3.500,00{EUR}"),
        ("subcategory", "Interest", f"5,00{EUR}"),
        ("subcategory", "Income awaiting review", f"45,00{EUR}"),
        ("mark", "Money out", f"262,30{EUR}"),
        ("subcategory", "Food", f"180,00{EUR}"),
        ("subcategory", "Shopping", f"70,00{EUR}"),
        ("subcategory", "Awaiting review", f"12,30{EUR}"),
        ("balance", "Left over", f"3.287,70{EUR}"),
    ]


def test_the_sankey_has_uniquely_named_nodes_and_balanced_links(logged_in_client, household):
    food, shopping = category_key("Food"), category_key("Shopping")
    salary, interest = income_key("Salary"), income_key("Interest")
    page = logged_in_client.get("/money-flow/", {"period": "2026-09"}).content.decode()

    chart = view_chart(page, "money_flow")
    nodes = [(n["name"], n["label"], n["key"]) for n in chart["nodes"]]
    assert nodes == [
        (salary, "Salary", salary),
        (interest, "Interest", interest),
        ("in:awaiting", "Income awaiting review", "in:awaiting"),
        ("household", "Household", "household"),
        (food, "Food", food),
        (shopping, "Shopping", shopping),
        ("awaiting", "Awaiting review", "awaiting"),
        ("left_over", "Left over", None),
    ]
    assert len({n["name"] for n in chart["nodes"]}) == len(chart["nodes"])
    links = [(link["source"], link["target"], link["value"]) for link in chart["links"]]
    assert links == [
        (salary, "household", 3500),
        (interest, "household", 5),
        ("in:awaiting", "household", 45),
        ("household", food, 180),
        ("household", shopping, 70),
        ("household", "awaiting", 12.3),
        ("household", "left_over", 3287.7),
    ]
    assert chart["drill"] == "/money-flow/transactions/?period=2026-09&key="


def test_spending_more_than_came_in_is_spent_beyond_money_in(logged_in_client, household):
    page = logged_in_client.get("/money-flow/", {"period": "2026-10"}).content.decode()

    assert flow_table(page)[-1] == ("balance", "Spent beyond money in", f"777,00{EUR}")
    chart = view_chart(page, "money_flow")
    assert ("beyond", "household", 777) in [
        (link["source"], link["target"], link["value"]) for link in chart["links"]
    ]


def test_drill_down_into_a_node(logged_in_client, household):
    url = "/money-flow/transactions/"
    params = {"period": "2026-09"}

    assert drill_rows(logged_in_client, url, {**params, "key": income_key("Salary")}) == [
        "Ana's salary", "Marko's salary",
    ]  # fmt: skip
    assert drill_rows(logged_in_client, url, {**params, "key": "in:awaiting"}) == [
        "Unknown payment in"
    ]
    assert drill_rows(logged_in_client, url, {**params, "key": category_key("Food")}) == [
        "Mercator", "Gostilna", "Spar",
    ]  # fmt: skip
    assert drill_rows(logged_in_client, url, {**params, "key": "awaiting"}) == ["Unknown shop"]
    assert drill_rows(logged_in_client, url, {**params, "key": "in"}) == [
        "Ana's salary", "Marko's salary", "Unknown payment in", "Interest",
    ]  # fmt: skip
    assert len(drill_rows(logged_in_client, url, {**params, "key": "household"})) == 10


def test_a_category_netting_to_a_refund_keeps_the_sankey_balanced(logged_in_client, household):
    shopping = Subcategory.objects.get(category__name="Shopping", name="Other")
    account = Transaction.objects.get(description="Shoe shop").account
    Transaction.objects.create(
        account=account, date=date(2026, 9, 14), amount="200.00", description="Big refund",
        subcategory=shopping, source="manual",
    )  # fmt: skip

    chart = view_chart(
        logged_in_client.get("/money-flow/", {"period": "2026-09"}).content.decode(), "money_flow"
    )

    links = chart["links"]
    assert category_key("Shopping") not in {link["target"] for link in links}
    into = sum(link["value"] for link in links if link["target"] == "household")
    out_of = sum(link["value"] for link in links if link["source"] == "household")
    assert into == pytest.approx(out_of)


def test_each_income_node_wears_its_own_income_categorys_hue(logged_in_client, household):
    gifts = Category.objects.create(name="Gifts", kind=Category.Kind.INCOME)
    birthday = Subcategory.objects.create(category=gifts, name="Birthday")
    account = Transaction.objects.get(description="Shoe shop").account
    Transaction.objects.create(
        account=account, date=date(2026, 9, 20), amount="50.00", description="From grandma",
        subcategory=birthday, source="manual",
    )  # fmt: skip
    page = logged_in_client.get("/money-flow/", {"period": "2026-09"}).content.decode()

    hues = {n["label"]: n["category"] for n in view_chart(page, "money_flow")["nodes"]}
    income = category_key("Income")
    assert hues == {
        "Salary": income,
        "Interest": income,
        "Birthday": str(gifts.pk),
        "Income awaiting review": "awaiting",
        "Household": None,
        "Food": category_key("Food"),
        "Shopping": category_key("Shopping"),
        "Awaiting review": "awaiting",
        "Left over": None,
    }
