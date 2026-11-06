"""Splitting a Transaction from Change (docs/design/split-editor.md): the endpoints the Split editor posts to, on a
Transaction row and for a Review queue group, Undo, and how a Split Transaction's row and Part rows read."""

import html
import json
import re
from datetime import date
from decimal import Decimal

import pytest

from ledger import outcomes
from ledger.models import Part, Source, Subcategory, Transaction

from .conftest import make_account, outcome_shown

pytestmark = pytest.mark.django_db

NBSP = " "


def sub(category, name):
    return Subcategory.objects.get(category__name=category, name=name)


def groceries():
    return sub("Food", "Groceries")


def household():
    return sub("Home", "Furniture & household")


@pytest.fixture
def account(member):
    return make_account("Ana's N26", "n26", member)


def add(account, amount, description="INTERSPAR", day=date(2026, 9, 5), **outcome):
    return Transaction.objects.create(
        account=account, date=day, amount=Decimal(amount), description=description, **outcome
    )


def parts_of(t):
    return [(p.subcategory, p.amount) for p in Part.objects.filter(transaction=t)]


def split_posted(t, *parts):
    """What the editor posts for `t`: the Parts' Subcategories, and its amount of each as typed."""
    return {
        "subcategory": [s.pk for s, _amount in parts],
        f"amount-{t.pk}": [amount for _s, amount in parts],
    }


def announced(response):
    return json.loads(response["HX-Trigger"])["announce"]


def rows_of(page, t):
    """The <tbody> holding `t`'s row and its Part rows."""
    found = re.search(rf'<tbody id="transaction-{t.pk}-rows".*?</tbody>', page, re.S)
    assert found, f"no rows for {t}"
    return found[0]


def part_rows(page, t):
    """Each Part row under `t`: (its emphasis, "Category › Subcategory", amount)."""
    return [
        (
            classes.strip(),
            html.unescape(" ".join(re.sub(r"<[^>]+>", " ", outcome).split())),
            amount.replace(NBSP, " "),
        )
        for classes, outcome, amount in re.findall(
            r'<tr class="part([^"]*)">.*?<td class="c-out"[^>]*>(.*?)</td>\s*<td class="num amt">([^<]*)</td>',
            rows_of(page, t),
            re.S,
        )
    ]


# Splitting a Transaction from its row


def test_splitting_a_row_saves_the_parts_by_hand_and_returns_the_row_with_them(
    logged_in_client, account
):
    t = add(account, "-80.00")

    response = logged_in_client.post(
        f"/transactions/{t.pk}/split/",
        split_posted(t, (groceries(), "50,00"), (household(), "30.00")),
        HTTP_HX_REQUEST="true",
    )

    assert response.status_code == 200
    t.refresh_from_db()
    assert t.is_split and t.source == Source.MANUAL
    assert parts_of(t) == [(groceries(), Decimal("-50.00")), (household(), Decimal("-30.00"))]
    page = response.content.decode()
    assert page.lstrip().startswith(f'<tbody id="transaction-{t.pk}-rows"')
    assert outcome_shown(page, "INTERSPAR") == "Split"
    assert part_rows(page, t) == [
        ("", "Food › Groceries", "−50,00 €"),
        ("", "Home › Furniture & household", "−30,00 €"),
    ]
    assert "Saved as a Split into 2 Parts" in page
    assert f'hx-post="/transactions/{t.pk}/undo/"' in page
    assert "Make a Rule" not in page
    assert announced(response) == "Saved INTERSPAR as a Split into 2 Parts."


def test_money_in_is_split_into_parts_of_money_in(logged_in_client, account):
    t = add(account, "300.00", "Payslip")

    logged_in_client.post(
        f"/transactions/{t.pk}/split/",
        split_posted(t, (sub("Income", "Salary"), "200"), (sub("Income", "Interest"), "100,00")),
        HTTP_HX_REQUEST="true",
    )

    assert parts_of(t) == [
        (sub("Income", "Salary"), Decimal("200.00")),
        (sub("Income", "Interest"), Decimal("100.00")),
    ]


@pytest.mark.parametrize(
    ("amounts", "reason"),
    [
        (("50,00", "20,00"), "The Parts add up to 70,00 €, not the Transaction's 80,00 €."),
        (("80,00", "0"), "A Part can't be zero."),
        (("80,00", ""), "Part 2 needs an amount."),
    ],
)
def test_a_refused_split_says_why_and_changes_nothing(logged_in_client, account, amounts, reason):
    t = add(account, "-80.00")

    response = logged_in_client.post(
        f"/transactions/{t.pk}/split/",
        split_posted(t, (groceries(), amounts[0]), (household(), amounts[1])),
        HTTP_HX_REQUEST="true",
    )

    assert response.status_code == 400
    assert response.content.decode().replace(NBSP, " ") == reason
    t.refresh_from_db()
    assert t.is_unresolved and not Part.objects.exists()


def test_a_split_naming_a_deleted_subcategory_is_refused(logged_in_client, account):
    t = add(account, "-80.00")

    response = logged_in_client.post(
        f"/transactions/{t.pk}/split/",
        {"subcategory": [groceries().pk, 999999], f"amount-{t.pk}": ["50", "30"]},
        HTTP_HX_REQUEST="true",
    )

    assert response.status_code == 400
    assert response.content.decode() == "A Subcategory was deleted meanwhile."


def test_undo_after_splitting_puts_back_the_outcome_it_replaced(logged_in_client, account):
    t = add(account, "-80.00", subcategory=groceries(), source=Source.RULE)
    logged_in_client.post(
        f"/transactions/{t.pk}/split/",
        split_posted(t, (groceries(), "50"), (household(), "30")),
        HTTP_HX_REQUEST="true",
    )

    response = logged_in_client.post(f"/transactions/{t.pk}/undo/", HTTP_HX_REQUEST="true")

    assert response.status_code == 200
    t.refresh_from_db()
    assert (t.subcategory, t.is_split, t.source) == (groceries(), False, Source.RULE)
    assert not Part.objects.exists()
    assert '<tr class="part' not in response.content.decode()


def test_editing_a_split_replaces_its_parts_and_undo_brings_the_old_ones_back(
    logged_in_client, account
):
    t = add(account, "-80.00")
    outcomes.split(t, [(groceries(), Decimal("-50.00")), (household(), Decimal("-30.00"))])
    restaurants = sub("Food", "Restaurants & cafés")

    logged_in_client.post(
        f"/transactions/{t.pk}/split/",
        split_posted(t, (groceries(), "40"), (household(), "30"), (restaurants, "10")),
        HTTP_HX_REQUEST="true",
    )
    assert [amount for _s, amount in parts_of(t)] == [Decimal(-40), Decimal(-30), Decimal(-10)]

    logged_in_client.post(f"/transactions/{t.pk}/undo/", HTTP_HX_REQUEST="true")
    assert parts_of(t) == [(groceries(), Decimal("-50.00")), (household(), Decimal("-30.00"))]


# A Split Transaction's row


@pytest.fixture
def hypermarket(account):
    t = add(account, "-80.00")
    outcomes.split(t, [(groceries(), Decimal("-50.00")), (household(), Decimal("-30.00"))])
    t.refresh_from_db()
    return t


def test_a_split_row_shows_its_full_amount_split_by_hand_and_its_part_rows(
    logged_in_client, hypermarket
):
    page = logged_in_client.get("/transactions/").content.decode()

    rows = rows_of(page, hypermarket)
    assert re.search(r'<td class="num amt">−80,00.€</td>', rows)
    assert 'class="split-name">Split</span><span class="minibar"' in rows
    assert ">by hand</span>" in rows
    assert part_rows(page, hypermarket) == [
        ("", "Food › Groceries", "−50,00 €"),
        ("", "Home › Furniture & household", "−30,00 €"),
    ]
    # Part rows have no Change of their own.
    assert rows.count("data-change") == 1


def test_a_split_rows_change_offers_to_edit_the_split(logged_in_client, hypermarket):
    rows = rows_of(logged_in_client.get("/transactions/").content.decode(), hypermarket)

    assert '<option value="" selected disabled>Split into 2 Parts</option>' in rows
    assert '<option value="split">Edit the Split…</option>' in rows
    assert f'data-parts="{groceries().pk}:-50.00,{household().pk}:-30.00"' in rows


def test_an_unsplit_rows_change_offers_split_into_parts(logged_in_client, account):
    t = add(account, "-12.00", "Hofer")
    page = logged_in_client.get("/transactions/").content.decode()

    assert '<option value="split">Split into Parts…</option>' in rows_of(page, t)
    # The chip panel's own row, and the editor it opens.
    assert "data-split-open>" in page
    assert 'class="split-editor"' in page


def test_filtered_to_a_category_the_matching_part_is_emphasised_and_the_others_dimmed(
    logged_in_client, hypermarket
):
    food = groceries().category
    page = logged_in_client.get(
        "/transactions/", {"outcome": f"category-{food.pk}"}
    ).content.decode()

    assert [shown for shown, _outcome, _amount in part_rows(page, hypermarket)] == ["em", "dim"]


def test_a_split_saved_on_a_filtered_page_comes_back_with_the_matching_part_emphasised(
    logged_in_client, hypermarket
):
    food = groceries().category
    response = logged_in_client.post(
        f"/transactions/{hypermarket.pk}/split/",
        {
            **split_posted(hypermarket, (groceries(), "40"), (household(), "40")),
            "listed": f"/transactions/?outcome=category-{food.pk}",
        },
        HTTP_HX_REQUEST="true",
    )

    page = response.content.decode()
    assert [shown for shown, _outcome, _amount in part_rows(page, hypermarket)] == ["em", "dim"]


def test_a_split_saved_in_the_drill_down_comes_back_in_total_with_the_counted_part_emphasised(
    logged_in_client, hypermarket
):
    listed = f"/spending/transactions/?period=2026-09&category={groceries().category.pk}"
    response = logged_in_client.post(
        f"/transactions/{hypermarket.pk}/split/",
        {**split_posted(hypermarket, (groceries(), "40"), (household(), "40")), "listed": listed},
        HTTP_HX_REQUEST="true",
    )

    page = response.content.decode()
    assert re.search(r"−80,00.€<small>in total</small>", rows_of(page, hypermarket))
    assert [shown for shown, _outcome, _amount in part_rows(page, hypermarket)] == ["em", "dim"]
    # Its Undo, and a save after it, keep to the same list.
    assert f'name="listed" value="{listed}"' in html.unescape(rows_of(page, hypermarket))


def test_an_undo_that_puts_a_split_back_keeps_its_emphasis(logged_in_client, hypermarket):
    listed = f"/transactions/?outcome=category-{groceries().category.pk}"
    logged_in_client.post(
        f"/transactions/{hypermarket.pk}/outcome/",
        {"outcome": groceries().pk, "listed": listed},
        HTTP_HX_REQUEST="true",
    )

    response = logged_in_client.post(
        f"/transactions/{hypermarket.pk}/undo/", {"listed": listed}, HTTP_HX_REQUEST="true"
    )

    page = response.content.decode()
    assert [shown for shown, _outcome, _amount in part_rows(page, hypermarket)] == ["em", "dim"]
    assert "in total" not in page


def test_a_row_tells_its_saves_the_address_of_the_list_it_is_in(logged_in_client, hypermarket):
    query = f"outcome=category-{groceries().category.pk}"
    page = logged_in_client.get(f"/transactions/?{query}").content.decode()

    assert f'name="listed" value="/transactions/?{query}"' in rows_of(page, hypermarket)


def test_in_the_drill_down_the_split_is_in_total_and_only_the_counted_part_stands_out(
    logged_in_client, hypermarket
):
    food = groceries().category
    page = logged_in_client.get(
        "/spending/transactions/", {"period": "2026-09", "category": food.pk}
    ).content.decode()

    rows = rows_of(page, hypermarket)
    assert "txn is-split in-total" in rows
    assert re.search(r"−80,00.€<small>in total</small>", rows)
    assert [shown for shown, _outcome, _amount in part_rows(page, hypermarket)] == ["em", "dim"]
    assert "For a Split, only its Food Part counts here." in page


def test_a_saved_one_outcome_replacing_a_split_drops_its_part_rows(logged_in_client, hypermarket):
    response = logged_in_client.post(
        f"/transactions/{hypermarket.pk}/outcome/",
        {"outcome": groceries().pk},
        HTTP_HX_REQUEST="true",
    )

    page = response.content.decode()
    assert outcome_shown(page, "INTERSPAR") == "Food → Groceries"
    assert '<tr class="part' not in page
    assert "Make a Rule" in page


# A Review queue group


@pytest.fixture
def bolt(account):
    """Two Bolt.eu rides waiting in the Review queue."""
    return [
        add(account, "-6.90", "Bolt.eu", date(2026, 11, 1)),
        add(account, "-14.40", "Bolt.eu", date(2026, 11, 3)),
    ]


def review_split(client, rides, *subcategories, amounts):
    return client.post(
        "/review/split/",
        {
            "transaction": [t.pk for t in rides],
            "subcategory": [s.pk for s in subcategories],
            **{f"amount-{t.pk}": typed for t, typed in zip(rides, amounts, strict=True)},
        },
        HTTP_HX_REQUEST="true",
    )


def test_the_review_queue_offers_to_split_a_group_as_one(logged_in_client, bolt):
    page = logged_in_client.get(f"/review/?group={bolt[-1].pk}").content.decode()

    assert "Split all 2 into Parts…" in page
    script = re.search(r'<script id="split-group"[^>]*>(.*?)</script>', page, re.S)
    assert script
    data = json.loads(script[1])
    assert data["url"] == "/review/split/"
    assert [(r["pk"], r["amount"]) for r in data["rows"]] == [
        (bolt[0].pk, "-6.90"),
        (bolt[1].pk, "-14.40"),
    ]


def test_a_group_is_split_in_one_save_and_undo_puts_the_whole_group_back(logged_in_client, bolt):
    transport = sub("Transport", "Public transport & car sharing")

    response = review_split(
        logged_in_client,
        bolt,
        groceries(),
        transport,
        amounts=[["1,00", "5,90"], ["2,00", "12,40"]],
    )

    assert response.status_code == 200
    assert parts_of(bolt[0]) == [(groceries(), Decimal("-1.00")), (transport, Decimal("-5.90"))]
    assert parts_of(bolt[1]) == [(groceries(), Decimal("-2.00")), (transport, Decimal("-12.40"))]
    page = response.content.decode()
    assert "Saved all 2 as Splits into 2 Parts" in page
    assert "Make a Rule" not in page
    assert announced(response).startswith("Saved 2 × Bolt.eu as a Split into 2 Parts.")

    logged_in_client.post(
        "/review/undo/", {"transaction": [t.pk for t in bolt]}, HTTP_HX_REQUEST="true"
    )
    for t in bolt:
        t.refresh_from_db()
        assert t.is_unresolved
    assert not Part.objects.exists()


def test_a_refused_group_split_names_the_transaction_and_saves_none(logged_in_client, bolt):
    response = review_split(
        logged_in_client,
        bolt,
        groceries(),
        household(),
        amounts=[["1,00", "5,90"], ["2,00", "12,00"]],
    )

    assert response.status_code == 400
    assert response.content.decode().replace(NBSP, " ") == (
        "3 Nov 2026 · 14,40 €: The Parts add up to 14,00 €, not the Transaction's 14,40 €."
    )
    assert not Part.objects.exists()


def test_a_split_decided_in_the_review_queue_shows_its_parts(logged_in_client, account):
    t = add(account, "-80.00")

    response = review_split(logged_in_client, [t], groceries(), household(), amounts=[["50", "30"]])

    page = response.content.decode()
    assert "Saved as a Split into 2 Parts" in page
    assert re.search(
        r'<ul class="part-lines">.*Groceries.*−50,00.€.*Furniture &amp; household.*−30,00.€',
        page,
        re.S,
    )
