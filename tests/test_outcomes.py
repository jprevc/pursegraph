import pytest

from ledger.models import Subcategory, Transaction
from tests.conftest import outcome_shown
from tests.test_import import upload

pytestmark = pytest.mark.django_db


def test_fee_transactions_are_categorized_as_bank_fees_at_import(logged_in_client):
    upload(logged_in_client)

    page = logged_in_client.get("/transactions/").content.decode()

    assert outcome_shown(page, "Fee: Corner Shop") == "Finance → Bank fees"
    assert outcome_shown(page, "Fee: To Janez Kranjc") == "Finance → Bank fees"
    assert outcome_shown(page, "Corner Shop") == "Awaiting review"


def transaction_id(description):
    return Transaction.objects.get(description=description).pk


def subcategory_id(category, name):
    return Subcategory.objects.get(category__name=category, name=name).pk


def test_inline_change_returns_the_updated_row_marked_manual(logged_in_client):
    upload(logged_in_client)

    response = logged_in_client.post(
        f"/transactions/{transaction_id('Corner Shop')}/outcome/",
        {"outcome": subcategory_id("Food", "Groceries")}, HTTP_HX_REQUEST="true",
    )

    row = response.content.decode()
    assert response.status_code == 200
    assert row.lstrip().startswith("<tr")
    assert outcome_shown(row, "Corner Shop") == "Food → Groceries"
    assert "Manual" in row


def test_inline_change_without_htmx_goes_back_to_the_page(logged_in_client):
    upload(logged_in_client)

    response = logged_in_client.post(
        f"/transactions/{transaction_id('To Janez Kranjc')}/outcome/",
        {"outcome": "transfer", "next": "/transactions/?q=Janez"},
    )

    assert response.status_code == 302
    assert response.url == "/transactions/?q=Janez"
    page = logged_in_client.get("/transactions/").content.decode()
    assert outcome_shown(page, "To Janez Kranjc") == "Transfer"


def test_a_transfer_can_be_categorized_again(logged_in_client):
    upload(logged_in_client)
    url = f"/transactions/{transaction_id('To Janez Kranjc')}/outcome/"
    logged_in_client.post(url, {"outcome": "transfer"})

    logged_in_client.post(url, {"outcome": subcategory_id("Other", "Payments to people")})

    page = logged_in_client.get("/transactions/").content.decode()
    assert outcome_shown(page, "To Janez Kranjc") == "Other → Payments to people"


def test_changing_an_automatic_outcome_makes_it_manual(logged_in_client):
    upload(logged_in_client)
    page = logged_in_client.get("/transactions/").content.decode()
    assert "Manual" not in page

    logged_in_client.post(
        f"/transactions/{transaction_id('Fee: Corner Shop')}/outcome/", {"outcome": subcategory_id("Finance", "Other")},
    )

    page = logged_in_client.get("/transactions/").content.decode()
    assert outcome_shown(page, "Fee: Corner Shop") == "Finance → Other"
    assert page.count("Manual") == 1


def test_an_unknown_outcome_is_refused(logged_in_client):
    upload(logged_in_client)
    url = f"/transactions/{transaction_id('Corner Shop')}/outcome/"

    assert logged_in_client.post(url, {"outcome": "999999"}).status_code == 400
    assert logged_in_client.post(url, {"outcome": ""}).status_code == 400
    assert logged_in_client.get(url).status_code == 405
    page = logged_in_client.get("/transactions/").content.decode()
    assert outcome_shown(page, "Corner Shop") == "Awaiting review"


def test_an_offsite_next_url_is_ignored(logged_in_client):
    upload(logged_in_client)

    response = logged_in_client.post(
        f"/transactions/{transaction_id('Corner Shop')}/outcome/", {"outcome": "transfer", "next": "https://evil.example/"},
    )

    assert response.url == "/transactions/"
