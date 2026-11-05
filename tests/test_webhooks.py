"""Webhooks: what Pursegraph POSTs to a real local receiver, when, and what the API & Webhooks page shows of it."""

import re
import socket
import time
from datetime import UTC, datetime

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import transaction
from django.utils import timezone

from ledger import webhooks
from ledger.models import Rule, Subcategory, Webhook
from ledger.suggestions import resuggest_queue
from tests.conftest import deliveries, page_text
from tests.test_import import FILENAME, FIXTURE, upload
from tests.test_rules import make_transaction

pytestmark = pytest.mark.django_db


@pytest.fixture
def at_1402(monkeypatch):
    moment = datetime(2026, 10, 27, 13, 2, tzinfo=UTC)
    monkeypatch.setattr(timezone, "now", lambda: moment)
    return moment


def closed_port_url():
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
    return f"http://127.0.0.1:{port}/hook"


def test_a_delivery_posts_only_the_count_waiting(receiver, at_1402):
    webhook = Webhook.objects.create(name="Home Assistant", url=receiver.url())

    webhooks.deliver(webhook, 3)

    [call] = receiver.calls()
    assert call["path"] == "/api/webhook/s3cret"
    assert call["headers"]["Content-Type"] == "application/json"
    assert call["body"] == {
        "event": "transactions_waiting",
        "at": "2026-10-27T13:02:00+00:00",
        "waiting": 3,
    }
    webhook.refresh_from_db()
    assert (webhook.last_attempt_at, webhook.last_outcome) == (at_1402, "delivered")


def outcome_of(webhook):
    webhook.refresh_from_db()
    return webhook.last_outcome, webhook.last_status


@pytest.mark.parametrize("status", [500, 404, 302])
def test_a_reply_other_than_2xx_is_a_failure_with_its_status(receiver, status):
    receiver.status = status
    webhook = Webhook.objects.create(name="Home Assistant", url=receiver.url())

    webhooks.deliver(webhook, 3)

    assert outcome_of(webhook) == ("http_error", status)


def test_a_receiver_that_doesnt_answer_in_time_has_timed_out(receiver, monkeypatch):
    monkeypatch.setattr(webhooks, "TIMEOUT", 0.2)
    receiver.delay = 1
    webhook = Webhook.objects.create(name="Home Assistant", url=receiver.url())

    webhooks.deliver(webhook, 3)

    assert outcome_of(webhook) == ("timed_out", None)


def test_a_receiver_that_isnt_listening_couldnt_be_reached():
    webhook = Webhook.objects.create(name="Home Assistant", url=closed_port_url())

    webhooks.deliver(webhook, 3)

    assert outcome_of(webhook) == ("unreachable", None)


def suggested(description, confidence=0.4):
    groceries = Subcategory.objects.get(category__name="Food", name="Groceries")
    return make_transaction(description, suggested_subcategory=groceries, confidence=confidence)


def test_re_suggest_tells_every_webhook_how_many_wait(
    admin_client, receiver, two_webhooks, django_capture_on_commit_callbacks
):
    suggested("Corner Shop")
    suggested("Hiša kave")
    make_transaction("Not asked yet")

    with django_capture_on_commit_callbacks(execute=True):
        admin_client.post("/suggestions/resuggest/")

    assert deliveries(receiver) == [("/ha", 3), ("/nas", 3)]


def test_re_suggest_with_nothing_waiting_afterwards_calls_no_webhook(
    admin_client, receiver, two_webhooks, django_capture_on_commit_callbacks
):
    make_transaction(
        "Decided",
        subcategory=Subcategory.objects.get(category__name="Food", name="Groceries"),
        source="manual",
    )

    with django_capture_on_commit_callbacks(execute=True):
        admin_client.post("/suggestions/resuggest/")

    assert deliveries(receiver) == []


def test_deleting_a_subcategory_tells_the_webhooks_its_suggestions_wait_again(
    admin_client, receiver, two_webhooks, django_capture_on_commit_callbacks
):
    suggested("Corner Shop")
    groceries = Subcategory.objects.get(category__name="Food", name="Groceries")

    with django_capture_on_commit_callbacks(execute=True):
        admin_client.post(f"/subcategories/{groceries.pk}/delete/")

    assert deliveries(receiver) == [("/ha", 1), ("/nas", 1)]


def test_deleting_a_subcategory_with_nothing_waiting_afterwards_calls_no_webhook(
    admin_client, receiver, two_webhooks, django_capture_on_commit_callbacks
):
    groceries = Subcategory.objects.get(category__name="Food", name="Groceries")

    with django_capture_on_commit_callbacks(execute=True):
        admin_client.post(f"/subcategories/{groceries.pk}/delete/")

    assert deliveries(receiver) == []


def test_an_import_tells_the_webhooks_how_many_wait(
    logged_in_client, receiver, two_webhooks, django_capture_on_commit_callbacks
):
    Rule.objects.create(
        description_contains="Ana Novak",
        subcategory=Subcategory.objects.get(category__name="Income", name="Salary"),
    )

    with django_capture_on_commit_callbacks(execute=True):
        upload(logged_in_client)

    # 8 Transactions: the salary by its Rule and the two fees as bank fees; 5 wait.
    assert deliveries(receiver) == [("/ha", 5), ("/nas", 5)]


def test_an_import_that_leaves_nothing_waiting_calls_no_webhook(
    logged_in_client, receiver, two_webhooks, django_capture_on_commit_callbacks
):
    groceries = Subcategory.objects.get(category__name="Food", name="Groceries")
    salary = Subcategory.objects.get(category__name="Income", name="Salary")
    Rule.objects.create(direction=Rule.Direction.OUT, subcategory=groceries)
    Rule.objects.create(direction=Rule.Direction.IN, subcategory=salary)

    with django_capture_on_commit_callbacks(execute=True):
        upload(logged_in_client)

    assert deliveries(receiver) == []


# Really committed, so the delivery threads see the Webhooks, and the default Categories are restored afterwards.
committed = pytest.mark.django_db(transaction=True, serialized_rollback=True)


@committed
def test_webhooks_are_called_only_once_the_action_commits(receiver, two_webhooks):
    suggested("Corner Shop")

    with transaction.atomic():
        resuggest_queue()
        time.sleep(0.2)
        assert receiver.received.empty()

    assert deliveries(receiver) == [("/ha", 1), ("/nas", 1)]


@committed
def test_an_action_rolled_back_calls_no_webhook(receiver, two_webhooks):
    suggested("Corner Shop")

    class Undone(Exception):
        pass

    with pytest.raises(Undone), transaction.atomic():
        resuggest_queue()
        raise Undone

    assert deliveries(receiver) == []


@committed
def test_a_slow_receiver_doesnt_hold_up_the_action(admin_client, receiver, two_webhooks):
    receiver.delay = 2
    suggested("Corner Shop")

    started = time.monotonic()
    response = admin_client.post("/suggestions/resuggest/")

    assert response.status_code == 302
    assert time.monotonic() - started < 1
    assert deliveries(receiver) == [("/ha", 1), ("/nas", 1)]


@committed
def test_a_fired_delivery_records_its_outcome(admin_client, receiver):
    receiver.status = 500
    failing = Webhook.objects.create(name="Home Assistant", url=receiver.url())
    unreachable = Webhook.objects.create(name="NAS", url=closed_port_url())
    suggested("Corner Shop")

    response = admin_client.post("/suggestions/resuggest/")

    assert response.status_code == 302
    receiver.calls()
    assert outcome_of(failing) == ("http_error", 500)
    assert outcome_of(unreachable) == ("unreachable", None)


def webhooks_shown(client):
    """The API & Webhooks page's Webhook rows, as text."""
    page = client.get("/api-and-webhooks/").content.decode()
    return [page_text(row) for row in re.findall(r'<div class="w-who">(.*?)</div>', page, re.S)]


def add_webhook(client, name="Home Assistant", url="https://ha.example:8123/api/webhook/s3cret"):
    return client.post("/api-and-webhooks/webhooks/", {"name": name, "url": url})


def test_with_no_webhook_the_page_says_programs_must_ask(admin_client):
    text = page_text(admin_client.get("/api-and-webhooks/").content.decode())

    assert "Webhooks · 0" in text
    assert "No Webhook yet" in text


def test_an_admin_adds_a_webhook_shown_with_its_url_masked(admin_client):
    response = add_webhook(admin_client)

    assert response.status_code == 302
    assert webhooks_shown(admin_client) == [
        "Home Assistant https://ha.example:8123/•••• · Never called"
    ]
    assert "s3cret" not in admin_client.get("/api-and-webhooks/").content.decode()


@pytest.mark.parametrize(
    "name, url",
    [
        ("", "https://ha.example/hook"),
        ("Home Assistant", ""),
        ("Home Assistant", "ftp://ha.example/hook"),
        ("Home Assistant", "https:///hook"),
        ("Home Assistant", "ha.example/hook"),
    ],
)
def test_a_webhook_needs_a_name_and_an_http_url(admin_client, name, url):
    response = add_webhook(admin_client, name, url)

    assert response.status_code == 200
    assert 'aria-invalid="true"' in response.content.decode()
    assert webhooks_shown(admin_client) == []


def test_a_webhook_can_be_on_a_host_without_a_domain(admin_client):
    add_webhook(admin_client, url="http://homeassistant:8123/api/webhook/s3cret")

    assert webhooks_shown(admin_client) == [
        "Home Assistant http://homeassistant:8123/•••• · Never called"
    ]


def delete_url(client):
    found = re.search(
        r'href="(/api-and-webhooks/webhooks/\d+/delete/)"',
        client.get("/api-and-webhooks/").content.decode(),
    )
    assert found, "no Delete"
    return found[1]


def test_deleting_is_confirmed_inline_and_removes_the_webhook(admin_client):
    add_webhook(admin_client)
    url = delete_url(admin_client)

    confirm = admin_client.get(url, headers={"HX-Request": "true"}).content.decode()
    assert "Delete <b>Home Assistant</b>? Pursegraph stops calling it." in confirm
    assert webhooks_shown(admin_client) != []

    admin_client.post(url)

    assert webhooks_shown(admin_client) == []


def notify_now(client, **headers):
    page = client.get("/api-and-webhooks/").content.decode()
    found = re.search(r'action="(/api-and-webhooks/webhooks/\d+/notify/)"', page)
    assert found, "no Notify now"
    return client.post(found[1], headers=headers)


def test_notify_now_tells_the_webhook_even_when_nothing_waits(admin_client, receiver, at_1402):
    add_webhook(admin_client, url=receiver.url())

    row = notify_now(admin_client, **{"HX-Request": "true"}).content.decode()

    [call] = receiver.calls()
    assert call["body"]["waiting"] == 0
    assert "Delivered 27 Oct 2026 14:02" in page_text(row)
    assert webhooks_shown(admin_client) == [
        f"Home Assistant http://127.0.0.1:{receiver.server.server_port}/•••• · Delivered 27 Oct 2026 14:02"
    ]


def test_notify_now_without_js_comes_back_to_the_page(admin_client, receiver):
    add_webhook(admin_client, url=receiver.url())
    make_transaction("Waiting")

    response = notify_now(admin_client)

    assert response.status_code == 302
    assert [call["body"]["waiting"] for call in receiver.calls()] == [1]


def test_notify_now_calls_only_that_webhook(admin_client, receiver):
    add_webhook(admin_client, "Home Assistant", receiver.url("/ha"))
    add_webhook(admin_client, "NAS", receiver.url("/nas"))

    notify_now(admin_client)

    assert [call["path"] for call in receiver.calls()] == ["/ha"]


def test_each_webhook_shows_its_latest_attempt(admin_client, receiver, at_1402, monkeypatch):
    monkeypatch.setattr(webhooks, "TIMEOUT", 0.2)
    receiver.status = 500
    closed = closed_port_url()
    webhooks.deliver(Webhook.objects.create(name="A", url=receiver.url()), 1)
    webhooks.deliver(Webhook.objects.create(name="B", url=closed), 1)
    receiver.delay = 1
    webhooks.deliver(Webhook.objects.create(name="C", url=receiver.url()), 1)
    Webhook.objects.create(name="D", url=receiver.url())

    port = receiver.server.server_port
    assert webhooks_shown(admin_client) == [
        f"A http://127.0.0.1:{port}/•••• · Failed 27 Oct 2026 14:02: HTTP 500",
        f"B {closed.removesuffix('hook')}•••• · Failed 27 Oct 2026 14:02: couldn't connect",
        f"C http://127.0.0.1:{port}/•••• · Failed 27 Oct 2026 14:02: timed out",
        f"D http://127.0.0.1:{port}/•••• · Never called",
    ]


def test_non_admins_cant_reach_webhooks(logged_in_client, admin_client, receiver):
    add_webhook(admin_client, url=receiver.url())
    pk = Webhook.objects.get().pk

    assert (
        logged_in_client.post(
            "/api-and-webhooks/webhooks/", {"name": "x", "url": receiver.url()}
        ).status_code
        == 403
    )
    assert logged_in_client.get(f"/api-and-webhooks/webhooks/{pk}/delete/").status_code == 403
    assert logged_in_client.post(f"/api-and-webhooks/webhooks/{pk}/delete/").status_code == 403
    assert logged_in_client.post(f"/api-and-webhooks/webhooks/{pk}/notify/").status_code == 403
    assert Webhook.objects.count() == 1
    assert receiver.calls() == []


@committed
def test_importing_several_statements_at_once_calls_each_webhook_for_each(
    logged_in_client, receiver, two_webhooks
):
    july = FIXTURE.replace(b"2026-06-", b"2026-07-").replace(b"2026-05-31", b"2026-07-01")

    logged_in_client.post(
        "/import/",
        {
            "file": [
                SimpleUploadedFile(FILENAME, FIXTURE),
                SimpleUploadedFile("account-statement_2026-07.csv", july),
            ],
            "account": "new",
            "new_account_name": "Ana's Revolut",
        },
    )

    # Each Statement import is an action of its own: after the first, its 6 wait; after the second, 12.
    assert deliveries(receiver) == [("/ha", 6), ("/ha", 12), ("/nas", 6), ("/nas", 12)]


def test_a_refused_webhook_keeps_the_page_current_in_the_sidebar(admin_client, household):
    page = add_webhook(admin_client, url="not a url").content.decode()

    assert re.search(r'<a[^>]*href="/api-and-webhooks/"[^>]*aria-current="page"', page)
