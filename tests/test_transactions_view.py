from datetime import date

import pytest

from ledger.models import Account, Category, Subcategory, Transaction
from tests.conftest import transaction_id
from tests.test_import import upload

pytestmark = pytest.mark.django_db

ALL = [
    "Hiša kave", "Payment from Ana Novak", "Corner Shop", "Fee: Corner Shop", "To Janez Kranjc",
    "Fee: To Janez Kranjc", "Čevljar", "Mercator Žalec",
]


def shown(client, **params):
    page = client.get("/transactions/", params).content.decode()
    return [description for description in ALL if f">{description}<" in page]


def test_search_matches_the_description_ignoring_case_and_accents(logged_in_client):
    upload(logged_in_client)

    assert shown(logged_in_client, q="corner") == ["Corner Shop", "Fee: Corner Shop"]
    assert shown(logged_in_client, q="cevljar") == ["Čevljar"]
    assert shown(logged_in_client, q="ŽALEC") == ["Mercator Žalec"]


def test_search_matches_the_counterparty(logged_in_client):
    upload(logged_in_client)
    Transaction.objects.filter(description="Hiša kave").update(counterparty_name="Kavarna d.o.o.")

    assert shown(logged_in_client, q="kavarna") == ["Hiša kave"]


def test_filter_by_account(logged_in_client):
    upload(logged_in_client)
    other = Account.objects.create(name="Bor's N26", bank="n26")
    Transaction.objects.filter(description="Čevljar").update(account=other)

    assert shown(logged_in_client, account=other.pk) == ["Čevljar"]


def test_filter_by_outcome(logged_in_client):
    upload(logged_in_client)
    logged_in_client.post(f"/transactions/{transaction_id('To Janez Kranjc')}/outcome/", {"outcome": "transfer"})
    groceries = Subcategory.objects.get(category__name="Food", name="Groceries")
    logged_in_client.post(f"/transactions/{transaction_id('Mercator Žalec')}/outcome/", {"outcome": groceries.pk})
    food = Category.objects.get(name="Food")

    assert shown(logged_in_client, outcome="unresolved") == ["Hiša kave", "Payment from Ana Novak", "Corner Shop", "Čevljar"]
    assert shown(logged_in_client, outcome="transfer") == ["To Janez Kranjc"]
    assert shown(logged_in_client, outcome=f"category-{food.pk}") == ["Mercator Žalec"]
    assert shown(logged_in_client, outcome=f"subcategory-{groceries.pk}") == ["Mercator Žalec"]


def test_filters_combine_and_stay_filled_in(logged_in_client):
    upload(logged_in_client)

    page = logged_in_client.get("/transactions/", {"q": "corner", "outcome": "unresolved"}).content.decode()

    assert ">Corner Shop<" in page
    assert ">Fee: Corner Shop<" not in page
    assert 'value="corner"' in page
    assert '<option value="unresolved" selected>' in page


def test_no_matches_says_so(logged_in_client):
    upload(logged_in_client)

    page = logged_in_client.get("/transactions/", {"q": "nothing like this"}).content.decode()

    assert "No Transactions match." in page
    assert "Import your first Statement" not in page


def test_long_lists_are_paged_newest_first(logged_in_client):
    account = Account.objects.create(name="Joint N26", bank="n26")
    Transaction.objects.bulk_create(
        Transaction(account=account, date=date(2026, 1, 1 + i % 28), amount=-1, description=f"Row {i:03}")
        for i in range(120)
    )

    first = logged_in_client.get("/transactions/").content.decode()
    second = logged_in_client.get("/transactions/", {"page": 2, "q": "row"}).content.decode()

    assert first.count('<tr id="transaction-') == 100
    assert ">Row 027<" in first  # 28 Jan
    assert second.count('<tr id="transaction-') == 20
    assert "?q=row&page=1" in second
