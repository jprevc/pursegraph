import json
import re
from datetime import date

import pytest

from ledger.models import Setting, Source, Transaction
from tests.conftest import subcategory_id, transaction_id
from tests.test_rules import make_transaction

pytestmark = pytest.mark.django_db

WAITING = "/api/categorizer/v1/transactions/"


def suggestion_url(description):
    return f"{WAITING}{transaction_id(description)}/suggestion/"


def create_token(admin_client, name="Qwen on the NAS"):
    """Creates a token on the API & Webhooks page, as an admin would, and returns its secret as the page shows it once."""
    page = admin_client.post("/api-and-webhooks/", {"name": name}, follow=True).content.decode()
    secret = re.search(r'value="(pgc_[^"]+)"', page)
    assert secret, "no token shown"
    return secret[1]


@pytest.fixture
def secret(admin_client):
    return create_token(admin_client)


@pytest.fixture
def api(client, secret):
    """A client calling the API with the token, as a Categorizer would."""

    class Api:
        def fetch(self, **params):
            return client.get(WAITING, params, headers={"Authorization": f"Bearer {secret}"})

        def send(self, description, body):
            return client.post(
                suggestion_url(description),
                body if isinstance(body, str) else json.dumps(body),
                content_type="application/json",
                headers={"Authorization": f"Bearer {secret}"},
            )

    return Api()


@pytest.mark.parametrize("authorization", [None, "Bearer nope", "Basic abc", "Bearer "])
def test_without_a_valid_token_the_api_answers_401(client, authorization):
    headers = {"Authorization": authorization} if authorization else {}

    response = client.get(WAITING, headers=headers)

    assert response.status_code == 401
    assert response["WWW-Authenticate"] == "Bearer"
    assert response.json() == {"error": "A valid API token is required."}


def test_a_logged_in_member_without_a_token_gets_401(logged_in_client):
    make_transaction("Corner Shop")

    assert logged_in_client.get(WAITING).status_code == 401
    assert (
        logged_in_client.post(
            suggestion_url("Corner Shop"), "{}", content_type="application/json"
        ).status_code
        == 401
    )


def test_a_token_reaches_nothing_but_the_api(client, secret):
    response = client.get("/transactions/", headers={"Authorization": f"Bearer {secret}"})

    assert response.status_code == 302
    assert response["Location"].startswith("/login/")


def test_fetching_returns_the_waiting_transactions_with_what_a_prompt_needs(api, logged_in_client):
    make_transaction("Corner Shop", "-12.30", raw={"purpose": "Weekly shop"})
    make_transaction("Plača", "1500.00")
    make_transaction(
        "Hofer", subcategory_id=subcategory_id("Food", "Groceries"), source=Source.MANUAL
    )
    make_transaction("Already asked", confidence=0)

    body = api.fetch().json()

    assert [t["description"] for t in body["transactions"]] == ["Corner Shop", "Plača"]
    corner, salary = body["transactions"]
    assert corner == {
        "id": transaction_id("Corner Shop"),
        "direction": "out",
        "amount": "12.30",
        "description": "Corner Shop",
        "detail": "Weekly shop",
        "examples": [
            {
                "direction": "out",
                "description": "Hofer",
                "detail": "",
                "subcategory": subcategory_id("Food", "Groceries"),
            }
        ],
    }
    assert (salary["direction"], salary["amount"]) == ("in", "1500.00")
    assert {"id": subcategory_id("Food", "Groceries"), "label": "Food > Groceries"} in body[
        "subcategories"
    ]


def test_fetching_claims_nothing_and_stops_at_the_limit(api):
    for description in ("A", "B", "C"):
        make_transaction(description)

    first = api.fetch(limit=2).json()["transactions"]
    again = api.fetch(limit=2).json()["transactions"]

    assert [t["description"] for t in first] == ["A", "B"]
    assert again == first


@pytest.mark.parametrize("limit", ["0", "201", "ten", "-1", "²"])
def test_a_bad_limit_is_a_400(api, limit):
    assert api.fetch(limit=limit).status_code == 400


def test_a_confident_suggestion_sets_the_outcome(api):
    make_transaction("Corner Shop")

    response = api.send(
        "Corner Shop", {"subcategory": subcategory_id("Food", "Groceries"), "confidence": 0.95}
    )

    assert response.json() == {"stored": True, "accepted": True}
    corner = Transaction.objects.get(description="Corner Shop")
    assert (corner.subcategory_id, corner.source) == (
        subcategory_id("Food", "Groceries"),
        Source.CATEGORIZER,
    )
    assert api.fetch().json()["transactions"] == []


def test_a_less_sure_suggestion_waits_in_the_review_queue(api, logged_in_client):
    make_transaction("Corner Shop")

    response = api.send(
        "Corner Shop", {"subcategory": subcategory_id("Food", "Groceries"), "confidence": 0.5}
    )

    assert response.json() == {"stored": True, "accepted": False}
    corner = Transaction.objects.get(description="Corner Shop")
    assert corner.is_unresolved
    assert corner.pending_suggestion_id == subcategory_id("Food", "Groceries")
    assert api.fetch().json()["transactions"] == []


def test_the_auto_accept_threshold_applies(api):
    Setting.put(Setting.AUTO_ACCEPT_THRESHOLD, "0.50")
    make_transaction("Corner Shop")

    response = api.send(
        "Corner Shop", {"subcategory": subcategory_id("Food", "Groceries"), "confidence": 0.5}
    )

    assert response.json() == {"stored": True, "accepted": True}


def test_no_suggestion_is_stored_so_the_transaction_isnt_handed_out_again(api):
    make_transaction("Corner Shop")

    response = api.send("Corner Shop", {"subcategory": None})

    assert response.json() == {"stored": True, "accepted": False}
    corner = Transaction.objects.get(description="Corner Shop")
    assert (corner.is_unresolved, corner.suggested_subcategory, corner.confidence) == (
        True,
        None,
        0,
    )
    assert api.fetch().json()["transactions"] == []


def test_the_first_suggestion_wins(api):
    make_transaction("Corner Shop")
    api.send("Corner Shop", {"subcategory": subcategory_id("Food", "Groceries"), "confidence": 0.5})

    response = api.send(
        "Corner Shop",
        {"subcategory": subcategory_id("Food", "Restaurants & cafés"), "confidence": 0.99},
    )

    assert response.json() == {"stored": False, "accepted": False}
    corner = Transaction.objects.get(description="Corner Shop")
    assert (corner.pending_suggestion_id, corner.confidence) == (
        subcategory_id("Food", "Groceries"),
        0.5,
    )


def test_a_suggestion_for_a_resolved_transaction_is_ignored(api):
    make_transaction(
        "Corner Shop", subcategory_id=subcategory_id("Food", "Groceries"), source=Source.MANUAL
    )

    response = api.send(
        "Corner Shop",
        {"subcategory": subcategory_id("Food", "Restaurants & cafés"), "confidence": 0.99},
    )

    assert response.json() == {"stored": False, "accepted": False}
    corner = Transaction.objects.get(description="Corner Shop")
    assert (corner.subcategory_id, corner.source, corner.confidence) == (
        subcategory_id("Food", "Groceries"),
        Source.MANUAL,
        None,
    )


def test_an_unknown_or_deleted_subcategory_is_rejected(api, admin_client):
    make_transaction("Corner Shop")
    cafes = subcategory_id("Food", "Restaurants & cafés")
    admin_client.post(f"/subcategories/{cafes}/delete/")

    for unknown in (cafes, 999999):
        response = api.send("Corner Shop", {"subcategory": unknown, "confidence": 0.5})
        assert response.status_code == 400
        assert "error" in response.json()
    assert [t["description"] for t in api.fetch().json()["transactions"]] == ["Corner Shop"]


@pytest.mark.parametrize(
    "body",
    [
        "not json",
        "[]",
        {},
        {"subcategory": "Groceries", "confidence": 0.5},
        {"subcategory": True, "confidence": 0.5},
        {"subcategory": 1},
        {"subcategory": 1, "confidence": 1.5},
        {"subcategory": 1, "confidence": -0.1},
        {"subcategory": 1, "confidence": "0.5"},
    ],
)
def test_a_malformed_body_is_a_400(api, body):
    make_transaction("Corner Shop")

    response = api.send("Corner Shop", body)

    assert response.status_code == 400
    assert Transaction.objects.get(description="Corner Shop").confidence is None


def test_a_suggestion_for_an_unknown_transaction_is_a_404(api, client, secret):
    response = client.post(
        f"{WAITING}999999/suggestion/",
        json.dumps({"subcategory": None}),
        content_type="application/json",
        headers={"Authorization": f"Bearer {secret}"},
    )

    assert response.status_code == 404


def test_a_revoked_token_gets_401(api, admin_client, client, secret):
    make_transaction("Corner Shop")
    page = admin_client.get("/api-and-webhooks/").content.decode()
    revoke = re.search(r'href="(/api-and-webhooks/tokens/\d+/revoke/)"', page)
    assert revoke, "no Revoke"
    confirm = admin_client.get(revoke[1]).content.decode()
    assert f'action="{revoke[1]}"' in confirm

    admin_client.post(revoke[1])

    assert api.fetch().status_code == 401
    assert api.send("Corner Shop", {"subcategory": None}).status_code == 401
    assert Transaction.objects.get(description="Corner Shop").confidence is None


def test_the_oldest_transactions_come_first(api):
    make_transaction("Newer")
    older = make_transaction("Older")
    Transaction.objects.filter(pk=older.pk).update(date=date(2026, 1, 1))

    assert [t["description"] for t in api.fetch().json()["transactions"]] == ["Older", "Newer"]
