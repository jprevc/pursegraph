import re

import pytest

from ledger.models import Category, Subcategory
from tests.conftest import outcome_shown
from tests.test_import import upload
from tests.test_outcomes import subcategory_id, transaction_id

pytestmark = pytest.mark.django_db

DEFAULTS = ["Food", "Home", "Transport", "Health", "Children", "Shopping", "Leisure", "Finance", "Other", "Income"]


def category_id(name):
    return Category.objects.get(name=name).pk


def category_order(client):
    """The Category names in the order the Categories page lists them."""
    page = client.get("/categories/").content.decode()
    return [name.strip() for name in re.findall(r'<h3 class="category">([^<]*)<', page)]


def test_the_default_categories_are_seeded_in_order(admin_client):
    page = admin_client.get("/categories/").content.decode()

    assert category_order(admin_client) == DEFAULTS
    for subcategory in ("Groceries", "Rent / mortgage", "Bank fees", "Cash withdrawal", "Payments to people", "Salary"):
        assert f'value="{subcategory}"' in page
    assert page.count('<span class="muted">catch-all</span>') == 10


def test_every_default_category_has_exactly_one_catch_all():
    catch_alls = {s.category.name: s.name for s in Subcategory.objects.filter(is_catch_all=True)}

    assert catch_alls == {**{name: "Other" for name in DEFAULTS[:8]}, "Other": "Miscellaneous", "Income": "Other income"}


def test_non_admins_are_forbidden(logged_in_client):
    food = category_id("Food")
    groceries = subcategory_id("Food", "Groceries")

    for url, data in [
        ("/categories/", None),
        ("/categories/add/", {"name": "Pets", "kind": "spending"}),
        (f"/categories/{food}/rename/", {"name": "Eating"}),
        (f"/categories/{food}/move/", {"direction": "down"}),
        (f"/categories/{food}/delete/", {}),
        (f"/categories/{food}/subcategories/add/", {"name": "Snacks"}),
        (f"/subcategories/{groceries}/rename/", {"name": "Supermarket"}),
        (f"/subcategories/{groceries}/move/", {"direction": "down"}),
        (f"/subcategories/{groceries}/delete/", {}),
    ]:
        response = logged_in_client.get(url) if data is None else logged_in_client.post(url, data)
        assert response.status_code == 403, url
    assert Category.objects.filter(name="Food").exists()
    assert Subcategory.objects.filter(name="Groceries").exists()


def test_only_admins_see_the_categories_link(logged_in_client, admin_client):
    assert b'href="/categories/"' in admin_client.get("/").content


def test_members_dont_see_the_categories_link(logged_in_client):
    assert b'href="/categories/"' not in logged_in_client.get("/").content


def test_adding_a_category_gives_it_a_catch_all_and_puts_it_last(admin_client):
    response = admin_client.post("/categories/add/", {"name": "Pets", "kind": "spending"})

    assert response.status_code == 302
    assert category_order(admin_client)[-1] == "Pets"
    assert Subcategory.objects.get(category__name="Pets").name == "Other"


def test_an_income_category_gets_an_other_income_catch_all(admin_client):
    admin_client.post("/categories/add/", {"name": "Pets", "kind": "income"})

    assert Subcategory.objects.get(category__name="Pets").name == "Other income"


def test_a_category_needs_a_name(admin_client):
    response = admin_client.post("/categories/add/", {"name": "  ", "kind": "spending"}, follow=True)

    assert "Name the Category." in response.content.decode()
    assert Category.objects.count() == 10


def test_new_subcategories_are_offered_as_outcomes(admin_client):
    upload(admin_client)

    admin_client.post(f"/categories/{category_id('Food')}/subcategories/add/", {"name": "Snacks"})
    snacks = subcategory_id("Food", "Snacks")
    admin_client.post(f"/transactions/{transaction_id('Corner Shop')}/outcome/", {"outcome": snacks})

    page = admin_client.get("/transactions/").content.decode()
    assert outcome_shown(page, "Corner Shop") == "Food → Snacks"
    # Listed before the catch-all.
    assert page.index(">Snacks<") < page.index(">Other<")


def test_renaming_shows_everywhere(admin_client):
    upload(admin_client)

    admin_client.post(f"/categories/{category_id('Finance')}/rename/", {"name": "Money"})
    admin_client.post(f"/subcategories/{subcategory_id('Money', 'Bank fees')}/rename/", {"name": "Fees"})

    page = admin_client.get("/transactions/").content.decode()
    assert outcome_shown(page, "Fee: Corner Shop") == "Money → Fees"


def test_reordering_categories(admin_client):
    admin_client.post(f"/categories/{category_id('Income')}/move/", {"direction": "up"})
    admin_client.post(f"/categories/{category_id('Food')}/move/", {"direction": "down"})
    admin_client.post(f"/categories/{category_id('Food')}/move/", {"direction": "up"})
    admin_client.post(f"/categories/{category_id('Food')}/move/", {"direction": "up"})  # already first

    assert category_order(admin_client) == [
        "Food", "Home", "Transport", "Health", "Children", "Shopping", "Leisure", "Finance", "Income", "Other",
    ]


def test_reordering_subcategories_keeps_the_catch_all_last(admin_client):
    admin_client.post(f"/subcategories/{subcategory_id('Finance', 'Bank fees')}/move/", {"direction": "down"})
    admin_client.post(f"/subcategories/{subcategory_id('Finance', 'Taxes & fines')}/move/", {"direction": "down"})

    page = admin_client.get("/categories/").content.decode()
    finance = page[page.index('<h3 class="category">Finance'):page.index('<h3 class="category">Other')]
    positions = [finance.index(f'value="{name}"') for name in ("Insurance (non-health)", "Bank fees", "Taxes &amp; fines", "Other")]
    assert positions == sorted(positions)


def test_deleting_a_subcategory_moves_its_transactions_to_the_catch_all(admin_client):
    upload(admin_client)

    response = admin_client.post(f"/subcategories/{subcategory_id('Finance', 'Bank fees')}/delete/")

    assert response.status_code == 302
    page = admin_client.get("/transactions/").content.decode()
    assert outcome_shown(page, "Fee: Corner Shop") == "Finance → Other"
    assert ">Bank fees<" not in page


def test_a_catch_all_cant_be_deleted(admin_client):
    response = admin_client.post(f"/subcategories/{subcategory_id('Food', 'Other')}/delete/", follow=True)

    assert "A catch-all Subcategory can&#x27;t be deleted." in response.content.decode()
    assert Subcategory.objects.filter(category__name="Food", name="Other").exists()


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
