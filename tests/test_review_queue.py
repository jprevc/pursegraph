import pytest

from tests.conftest import outcome_shown
from tests.test_import import upload
from tests.test_outcomes import transaction_id

pytestmark = pytest.mark.django_db

# The fixture's eight Transactions, less its two fees.
UNRESOLVED = ["Hiša kave", "Payment from Ana Novak", "Corner Shop", "To Janez Kranjc", "Čevljar", "Mercator Žalec"]


def test_review_queue_lists_unresolved_transactions_oldest_first(logged_in_client):
    upload(logged_in_client)

    page = logged_in_client.get("/review/").content.decode()

    positions = [page.index(f">{description}<") for description in UNRESOLVED]
    assert positions == sorted(positions)
    assert "Fee: " not in page
    assert outcome_shown(page, "Corner Shop") == "Awaiting review"


def test_resolved_transactions_leave_the_queue(logged_in_client):
    upload(logged_in_client)

    logged_in_client.post(f"/transactions/{transaction_id('To Janez Kranjc')}/outcome/", {"outcome": "transfer"})

    page = logged_in_client.get("/review/").content.decode()
    assert ">To Janez Kranjc<" not in page
    assert ">Corner Shop<" in page


def test_sidebar_shows_the_review_queue_count(logged_in_client):
    assert "Review queue (0)" in logged_in_client.get("/").content.decode()
    upload(logged_in_client)
    assert "Review queue (6)" in logged_in_client.get("/").content.decode()

    logged_in_client.post(f"/transactions/{transaction_id('Corner Shop')}/outcome/", {"outcome": "transfer"})

    assert "Review queue (5)" in logged_in_client.get("/transactions/").content.decode()


def test_an_empty_review_queue_says_so(logged_in_client):
    assert "Nothing to review" in logged_in_client.get("/review/").content.decode()
