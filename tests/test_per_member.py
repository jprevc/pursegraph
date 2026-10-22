import re
from datetime import date

import pytest

from ledger.models import Category, Subcategory, Transaction

from .conftest import EUR, drill_rows, view_chart, view_table

pytestmark = pytest.mark.django_db

TODAY = date(2026, 10, 15)


@pytest.fixture(autouse=True)
def today(monkeypatch):
    monkeypatch.setattr("dashboard.periods.today", lambda: TODAY)


def category_key(name):
    return str(Category.objects.get(name=name).pk)


def test_per_member_puts_joint_accounts_in_their_own_bucket(logged_in_client, household):
    page = logged_in_client.get("/per-member/", {"period": "2026-09"}).content.decode()

    assert "Per Member" in page
    assert view_table(page) == [
        ["ana", f"162,30{EUR}"],
        ["marko", f"40,00{EUR}"],
        ["Joint", f"60,00{EUR}"],
    ]


def test_each_members_spending_is_split_by_category(logged_in_client, household):
    page = logged_in_client.get("/per-member/", {"period": "2026-09"}).content.decode()

    categories = re.findall(
        r'<tr class="subcategory"[^>]*>\s*<td><button[^>]*>([^<]*)</button></td>\s*<td class="num">([^<]*)</td>',
        page,
    )
    assert categories == [
        ("Food", f"80,00{EUR}"),
        ("Shopping", f"70,00{EUR}"),
        ("Awaiting review", f"12,30{EUR}"),
        ("Food", f"40,00{EUR}"),
        ("Food", f"60,00{EUR}"),
    ]


def test_a_member_with_a_full_name_is_shown_by_it(logged_in_client, household):
    household["marko"].first_name = "Marko Novak"
    household["marko"].save()

    page = logged_in_client.get("/per-member/", {"period": "2026-09"}).content.decode()

    assert [row[0] for row in view_table(page)] == ["ana", "Marko Novak", "Joint"]


def test_the_chart_stacks_each_members_categories(logged_in_client, household):
    ana, marko = household["ana"].pk, household["marko"].pk
    food = category_key("Food")
    page = logged_in_client.get("/per-member/", {"period": "2026-09"}).content.decode()

    chart = view_chart(page, "per_member")
    assert chart["members"] == ["ana", "marko", "Joint"]
    assert [(s["name"], [p["value"] for p in s["data"]]) for s in chart["segments"]] == [
        ("Food", [80, 40, 60]),
        ("Shopping", [70, 0, 0]),
        ("Awaiting review", [12.3, 0, 0]),
    ]
    assert [p["key"] for p in chart["segments"][0]["data"]] == [
        f"{ana}:{food}",
        f"{marko}:{food}",
        f"joint:{food}",
    ]
    assert chart["drill"] == "/per-member/transactions/?period=2026-09&key="


def test_drill_down_into_a_member_or_one_segment(logged_in_client, household):
    ana = household["ana"].pk
    url = "/per-member/transactions/"
    params = {"period": "2026-09"}

    assert drill_rows(logged_in_client, url, {**params, "key": f"{ana}"}) == [
        "Mercator", "Shoe shop", "Shoe shop refund", "Unknown shop",
    ]  # fmt: skip
    assert drill_rows(logged_in_client, url, {**params, "key": f"{ana}:awaiting"}) == [
        "Unknown shop"
    ]
    assert drill_rows(
        logged_in_client, url, {**params, "key": f"joint:{category_key('Food')}"}
    ) == ["Spar"]


def test_a_category_netting_to_a_refund_draws_a_negative_segment(logged_in_client, household):
    shopping = Subcategory.objects.get(category__name="Shopping", name="Other")
    account = Transaction.objects.get(description="Shoe shop").account
    Transaction.objects.create(
        account=account, date=date(2026, 9, 14), amount="200.00", description="Big refund",
        subcategory=shopping, source="manual",
    )  # fmt: skip
    page = logged_in_client.get("/per-member/", {"period": "2026-09"}).content.decode()

    segments = {
        s["name"]: [p["value"] for p in s["data"]]
        for s in view_chart(page, "per_member")["segments"]
    }
    assert segments["Shopping"] == [-130, 0, 0]
    assert view_table(page)[0] == ["ana", f"−37,70{EUR}"]
