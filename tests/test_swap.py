"""The shell's swap convention, as far as the server keeps it: announcements, the page title, and a session that
has expired under an HTMX swap."""

import json
import re

import pytest
from django.http import HttpResponse

from pursegraph.htmx import announce
from tests.test_import import upload

SWAP = {"HX-Request": "true"}


def test_announce_sets_the_message_as_an_htmx_trigger():
    response = announce(HttpResponse(), "Cash flow, September 2026")

    assert json.loads(response["HX-Trigger"]) == {"announce": "Cash flow, September 2026"}


def test_announce_keeps_the_triggers_already_set():
    response = HttpResponse(headers={"HX-Trigger": json.dumps({"themechange": None})})

    announce(response, "142 Transactions")

    assert json.loads(response["HX-Trigger"]) == {
        "themechange": None,
        "announce": "142 Transactions",
    }


def test_announce_keeps_a_trigger_set_by_name_alone():
    response = HttpResponse(headers={"HX-Trigger": "refresh"})

    announce(response, "Page 3 of 8, 51–75 of 192")

    assert json.loads(response["HX-Trigger"]) == {
        "refresh": None,
        "announce": "Page 3 of 8, 51–75 of 192",
    }


def test_a_swap_after_the_session_expired_sends_the_whole_page_to_log_in(client):
    response = client.get(
        "/spending/transactions/?period=2026-09&category=1",
        headers={
            "HX-Request": "true",
            "HX-Current-URL": "http://testserver/spending/?period=2026-09",
        },
    )

    assert response.status_code == 401
    # Back to the page that was showing, not to the fragment it asked for.
    assert response["HX-Redirect"] == "/login/?next=/spending/%3Fperiod%3D2026-09"


def test_a_page_asked_for_after_the_session_expired_still_redirects_to_log_in(client):
    response = client.get("/spending/?period=2026-09")

    assert response.status_code == 302
    assert response["Location"] == "/login/?next=/spending/%3Fperiod%3D2026-09"


def page_title(page):
    title = re.findall(r"<title>([^<]*)</title>", page)
    assert len(title) == 1, f"{len(title)} titles"
    return title[0]


@pytest.mark.django_db
@pytest.mark.parametrize("headers", [{}, SWAP], ids=["page", "swap"])
def test_a_dashboard_view_is_titled_by_the_view_then_the_period(
    logged_in_client, household, headers
):
    page = logged_in_client.get("/cashflow/", {"period": "2026-09"}, headers=headers)

    assert page_title(page.content.decode()) == "Cashflow · September 2026 · Pursegraph"


@pytest.mark.django_db
def test_a_dashboard_view_swapped_in_names_its_new_period(logged_in_client, household):
    page = logged_in_client.get("/spending/", {"period": "2026-08"}, headers=SWAP)

    assert page_title(page.content.decode()) == "Spending by Category · August 2026 · Pursegraph"


@pytest.mark.django_db
@pytest.mark.parametrize("headers", [{}, SWAP], ids=["page", "swap"])
def test_transactions_is_titled_alike_whole_or_swapped_in(logged_in_client, headers):
    page = logged_in_client.get("/transactions/", headers=headers)

    assert page_title(page.content.decode()) == "Transactions · Pursegraph"


@pytest.mark.django_db
def test_the_review_queue_title_counts_what_is_left_to_review(logged_in_client):
    assert page_title(logged_in_client.get("/review/").content.decode()) == (
        "Review queue · Pursegraph"
    )
    upload(logged_in_client)

    page = logged_in_client.get("/review/").content.decode()

    assert page_title(page) == "Review queue (6) · Pursegraph"


@pytest.mark.django_db
def test_the_drill_down_keeps_the_page_title(logged_in_client, household):
    page = logged_in_client.get(
        "/cashflow/transactions/", {"period": "2026-09", "key": "2026-09"}, headers=SWAP
    )

    assert "<title>" not in page.content.decode()


@pytest.mark.django_db
@pytest.mark.parametrize(
    ("url", "headers"),
    [
        ("/", {}),
        ("/cashflow/", SWAP),
        ("/transactions/", {}),
        ("/transactions/", SWAP),
        ("/review/", {}),
        ("/import/", {}),
        ("/rules/", {}),
    ],
)
def test_every_page_has_one_h1_that_a_swap_can_focus(logged_in_client, household, url, headers):
    page = logged_in_client.get(url, headers=headers).content.decode()

    assert len(re.findall(r'<h1 [^>]*tabindex="-1"', page)) == 1
    assert "<h1>" not in page


@pytest.mark.django_db
def test_an_empty_dashboard_still_has_an_h1(logged_in_client):
    page = logged_in_client.get("/").content.decode()

    assert re.search(r'<h1 [^>]*tabindex="-1"[^>]*>Dashboard</h1>', page)
