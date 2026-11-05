import html
import json
import re

import pytest

from ledger.models import Category, Source, Subcategory
from tests.conftest import disabled_reason, outcome_shown, page_text, subcategory_id, transaction_id
from tests.test_import import upload
from tests.test_rules import make_rule, make_transaction

pytestmark = pytest.mark.django_db

DEFAULTS = [
    "Food",
    "Home",
    "Transport",
    "Health",
    "Children",
    "Shopping",
    "Leisure",
    "Finance",
    "Other",
    "Income",
]


def category_id(name):
    return Category.objects.get(name=name).pk


def cards(page):
    """Each read-only Category card on the Categories page, in order: its Subcategories as (name, Transaction count,
    tags)."""
    found = re.findall(
        r'<section class="panel cat-card"[^>]*>\s*<div class="cat-head"><h2[^>]*>(?:<span[^>]*></span>)?([^<]*)</h2>(.*?)</section>',
        page,
        re.S,
    )
    return {
        name.strip(): [
            (
                html.unescape(sub.strip()),
                int(count),
                re.findall(r'<span class="tag[^"]*">([^<]*)<', tags),
            )
            for sub, tags, count in re.findall(
                r'<li><span class="sub-name">([^<]*)(.*?)</span><span class="fig">(\d+)</span></li>',
                body,
                re.S,
            )
        ]
        for name, body in found
    }


def category_order(client):
    """The Category names in the order the Categories page lists them."""
    return list(cards(client.get("/categories/").content.decode()))


def catch_alls(client):
    """Each Category's catch-all Subcategory, as the Categories page shows them."""
    return {
        category: [sub for sub, _, tags in subs if "catch-all" in tags]
        for category, subs in cards(client.get("/categories/").content.decode()).items()
    }


def test_the_default_categories_are_seeded_in_order(admin_client):
    shown = cards(admin_client.get("/categories/").content.decode())

    assert list(shown) == DEFAULTS
    names = {sub for subs in shown.values() for sub, _, _ in subs}
    assert {
        "Groceries",
        "Rent / mortgage",
        "Bank fees",
        "Cash withdrawal",
        "Payments to people",
        "Salary",
    } <= names
    tagged = [(c, sub) for c, subs in shown.items() for sub, _, tags in subs if "bank fees" in tags]
    assert tagged == [("Finance", "Bank fees")]


def test_every_default_category_has_exactly_one_catch_all(admin_client):
    assert catch_alls(admin_client) == {
        **{name: ["Other"] for name in DEFAULTS[:8]},
        "Other": ["Miscellaneous"],
        "Income": ["Other income"],
    }


def test_non_admins_are_forbidden(logged_in_client, admin_client):
    food = category_id("Food")
    groceries = subcategory_id("Food", "Groceries")

    for url, data in [
        ("/categories/", None),
        ("/categories/add/", {"name": "Pets", "kind": "spending"}),
        (f"/categories/{food}/save/", {"name": "Eating"}),
        (f"/categories/{food}/move/", {"direction": "down"}),
        (f"/categories/{food}/delete/", {}),
        (f"/categories/{food}/subcategories/add/", {"name": "Snacks"}),
        (f"/subcategories/{groceries}/move/", {"direction": "down"}),
        (f"/subcategories/{groceries}/delete/", {}),
    ]:
        response = logged_in_client.get(url) if data is None else logged_in_client.post(url, data)
        assert response.status_code == 403, url
    assert category_order(admin_client) == DEFAULTS
    page = admin_client.get("/categories/").content.decode()
    assert card(page, "Food")[0] == ("Groceries", 0)
    assert "Snacks" not in page


def test_only_admins_see_the_categories_link(logged_in_client, admin_client):
    assert b'href="/categories/"' in admin_client.get("/").content
    assert b'href="/categories/"' not in logged_in_client.get("/").content


def test_adding_a_category_gives_it_a_catch_all_and_puts_it_last(admin_client):
    response = admin_client.post("/categories/add/", {"name": "Pets", "kind": "spending"})

    assert response.status_code == 302
    assert category_order(admin_client)[-1] == "Pets"
    assert catch_alls(admin_client)["Pets"] == ["Other"]


def test_an_income_category_gets_an_other_income_catch_all(admin_client):
    admin_client.post("/categories/add/", {"name": "Pets", "kind": "income"})

    assert catch_alls(admin_client)["Pets"] == ["Other income"]


def test_a_category_needs_a_name(admin_client):
    response = admin_client.post(
        "/categories/add/", {"name": "  ", "kind": "spending"}, follow=True
    )

    assert "Name the Category." in response.content.decode()
    assert category_order(admin_client) == DEFAULTS


def test_new_subcategories_are_offered_as_outcomes(admin_client):
    upload(admin_client)

    admin_client.post(
        f"/categories/{category_id('Food')}/subcategories/add/", {"new-name": "Snacks"}
    )
    snacks = subcategory_id("Food", "Snacks")
    admin_client.post(
        f"/transactions/{transaction_id('Corner Shop')}/outcome/", {"outcome": snacks}
    )

    page = admin_client.get("/transactions/").content.decode()
    assert outcome_shown(page, "Corner Shop") == "Food → Snacks"
    # Listed before the catch-all, in the rows' outcome picker.
    table = page[page.index('<table class="rows">') :]
    assert table.index(">Food › Snacks<") < table.index(">Food › Other<")


def test_renaming_shows_everywhere(admin_client):
    upload(admin_client)

    admin_client.post(
        f"/categories/{category_id('Finance')}/save/",
        {"name": "Money", f"sub-{subcategory_id('Finance', 'Bank fees')}": "Fees"},
    )

    page = admin_client.get("/transactions/").content.decode()
    assert outcome_shown(page, "Fee: Corner Shop") == "Money → Fees"


def test_reordering_categories(admin_client):
    admin_client.post(f"/categories/{category_id('Income')}/move/", {"direction": "up"})
    admin_client.post(f"/categories/{category_id('Food')}/move/", {"direction": "down"})
    admin_client.post(f"/categories/{category_id('Food')}/move/", {"direction": "up"})
    admin_client.post(
        f"/categories/{category_id('Food')}/move/", {"direction": "up"}
    )  # already first

    assert category_order(admin_client) == [
        "Food",
        "Home",
        "Transport",
        "Health",
        "Children",
        "Shopping",
        "Leisure",
        "Finance",
        "Income",
        "Other",
    ]


def test_reordering_subcategories_keeps_the_catch_all_last(admin_client):
    admin_client.post(
        f"/subcategories/{subcategory_id('Finance', 'Bank fees')}/move/", {"direction": "down"}
    )
    admin_client.post(
        f"/subcategories/{subcategory_id('Finance', 'Taxes & fines')}/move/", {"direction": "down"}
    )

    finance = card(admin_client.get("/categories/").content.decode(), "Finance")
    assert [sub for sub, _ in finance] == [
        "Insurance (non-health)",
        "Bank fees",
        "Taxes & fines",
        "Other",
    ]


def test_deleting_a_subcategory_moves_its_transactions_to_the_catch_all(admin_client):
    upload(admin_client)

    response = admin_client.post(f"/subcategories/{subcategory_id('Finance', 'Bank fees')}/delete/")

    assert response.status_code == 302
    page = admin_client.get("/transactions/").content.decode()
    assert outcome_shown(page, "Fee: Corner Shop") == "Finance → Other"
    assert ">Bank fees<" not in page


def test_a_catch_all_cant_be_deleted(admin_client):
    response = admin_client.post(
        f"/subcategories/{subcategory_id('Food', 'Other')}/delete/", follow=True
    )

    assert "A catch-all Subcategory can&#x27;t be deleted." in response.content.decode()
    assert catch_alls(admin_client)["Food"] == ["Other"]


def test_a_category_with_transactions_cant_be_deleted(admin_client):
    upload(admin_client)

    response = admin_client.post(f"/categories/{category_id('Finance')}/delete/", follow=True)

    assert "Finance still has Transactions" in response.content.decode()
    assert "Finance" in category_order(admin_client)


def test_an_empty_category_can_be_deleted(admin_client):
    upload(admin_client)

    response = admin_client.post(f"/categories/{category_id('Children')}/delete/")

    assert response.status_code == 302
    assert "Children" not in category_order(admin_client)
    assert "Childcare" not in admin_client.get("/transactions/").content.decode()


# The read-only cards and editing one Category (docs/design/admin.md)


def card(page, name):
    """The read-only card of Category `name`: its Subcategories with their Transaction counts."""
    return [(sub, count) for sub, count, _ in cards(page)[name]]


def test_a_card_counts_each_subcategorys_transactions(admin_client):
    groceries = Subcategory.objects.get(category__name="Food", name="Groceries")
    for description in ("Mercator", "Spar"):
        make_transaction(description, subcategory=groceries, source=Source.MANUAL)

    rows = card(admin_client.get("/categories/").content.decode(), "Food")

    assert rows[0] == ("Groceries", 2)
    assert rows[-1] == ("Other", 0)


HTMX = {"HTTP_HX_REQUEST": "true"}


def editing_page(client, name):
    """The Categories page with Category `name` opened for editing."""
    return client.get(f"/categories/?edit={category_id(name)}").content.decode()


def editing(client, name):
    """The Categories page with Category `name` opened for editing, as text."""
    return page_text(editing_page(client, name))


def test_editing_counts_each_subcategorys_transactions_and_rules(admin_client):
    groceries = Subcategory.objects.get(category__name="Food", name="Groceries")
    make_transaction("Mercator", subcategory=groceries, source=Source.MANUAL)
    make_rule(admin_client, groceries.pk, description_contains="spar")

    text = editing(admin_client, "Food")

    assert "Editing Food Spending · place 1 of 10" in text
    assert "1 Transaction · 1 Rule" in text
    assert "0 Transactions catch-all · last" in text


def test_only_one_category_is_edited_at_a_time(admin_client):
    page = admin_client.get(f"/categories/?edit={category_id('Food')}").content.decode()

    assert len(re.findall(r'<a class="button ghost sm"[^>]*>.*?Edit</a>', page, re.S)) == 0
    assert page.count('disabled aria-label="Edit ') == 9


def test_a_used_category_says_why_it_cant_be_deleted(admin_client):
    groceries = Subcategory.objects.get(category__name="Food", name="Groceries")
    make_transaction("Mercator", subcategory=groceries, source=Source.MANUAL)
    make_rule(admin_client, subcategory_id("Home", "Utilities"), description_contains="elektro")

    assert (
        disabled_reason(editing_page(admin_client, "Food"), "Delete Food")
        == "Food still has 1 Transaction. Delete its Subcategories first, then recategorize what is left in Other."
    )
    assert (
        disabled_reason(editing_page(admin_client, "Home"), "Delete Home")
        == "1 Rule still categorizes into Home."
    )


def test_deleting_an_unused_category_is_confirmed_inline(admin_client):
    children = category_id("Children")

    confirm = admin_client.get(f"/categories/{children}/delete/", **HTMX).content.decode()

    assert "Delete Children and its catch-all Other? Nothing uses it." in page_text(confirm)
    assert category_order(admin_client) == DEFAULTS


def test_deleting_a_subcategory_is_confirmed_with_what_moves(admin_client):
    groceries = Subcategory.objects.get(category__name="Food", name="Groceries")
    make_transaction("Mercator", subcategory=groceries, source=Source.MANUAL)
    make_transaction("Spar", subcategory=groceries, source=Source.MANUAL)
    make_rule(admin_client, groceries.pk, description_contains="spar")

    confirm = admin_client.get(f"/subcategories/{groceries.pk}/delete/", **HTMX).content.decode()

    assert " ".join(re.sub(r"<[^>]+>", "", confirm).split()).startswith(
        "Delete Food › Groceries? Its 2 Transactions and 1 Rule move to Food › Other. "
        "Queued suggestions for it are asked again."
    )


def test_a_step_while_editing_keeps_the_names_typed_so_far(admin_client):
    groceries = subcategory_id("Food", "Groceries")

    page = admin_client.post(
        f"/subcategories/{groceries}/move/",
        {"direction": "down", "name": "Eating", f"sub-{groceries}": "Supermarket"},
        **HTMX,
    ).content.decode()

    assert 'name="name" value="Eating"' in page
    assert f'name="sub-{groceries}" value="Supermarket"' in page
    assert Category.objects.get(pk=category_id("Food")).name == "Food"  # not saved yet
    moved_back = admin_client.post(f"/subcategories/{groceries}/move/", {"direction": "up"}, **HTMX)
    assert json.loads(moved_back["HX-Trigger"])["announce"] == "Moved Groceries up."


def test_saving_a_blank_name_keeps_the_category_open(admin_client):
    food = category_id("Food")

    response = admin_client.post(f"/categories/{food}/save/", {"name": " "}, **HTMX)
    page = response.content.decode()

    assert "Give it a name." in page
    assert json.loads(response["HX-Trigger"])["announce"] == "Give it a name."
    assert "Editing Food" in page_text(page)
    assert Category.objects.get(pk=food).name == "Food"
