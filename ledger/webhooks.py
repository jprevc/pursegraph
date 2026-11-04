"""Webhooks: the URLs Pursegraph calls when Transactions are waiting for a Suggestion, so a Categorizer that can't
poll, such as one on a machine that sleeps, knows to fetch them
(docs/adr/0002-no-bundled-categorizer-webhooks-say-when-transactions-wait.md).

A delivery is one POST of `{"event": "transactions_waiting", "at": "<ISO 8601>", "waiting": <count>}`, never
Transaction data, with a 5 s timeout. Only a 2xx reply counts as delivered; there are no retries and no signing,
the secret being in the URL. Each Webhook keeps only its latest attempt.

An action that can leave Transactions waiting (a Statement import, a re-parse that re-runs outcomes, Ask again,
deleting a Subcategory) calls `fire_if_waiting()`. Once its database transaction commits, and only if a Transaction
is waiting then, every Webhook gets a delivery on a short-lived thread of its own, so a slow or failing receiver
never holds up or breaks the action. Each action fires on its own, with nothing combined across actions: importing
three Statements at once calls each Webhook three times. Receivers treat a delivery as "go fetch", which is safe to
repeat.
"""

import json
import logging
import socket
import threading
from http.client import HTTPException
from urllib.error import HTTPError, URLError
from urllib.request import HTTPRedirectHandler, Request, build_opener

from django.db import connection, transaction
from django.utils import timezone

from . import suggestions
from .models import Webhook

logger = logging.getLogger(__name__)

EVENT = "transactions_waiting"
# Seconds to wait for the receiver: to connect, and then for each read of its reply.
TIMEOUT = 5.0


class _NoRedirects(HTTPRedirectHandler):
    """A redirect is a reply like any other that isn't 2xx: it isn't followed, so the POST isn't turned into a GET or
    sent somewhere the admin didn't enter."""

    def redirect_request(self, *args, **kwargs):
        return None


_opener = build_opener(_NoRedirects)


def add(name: str, url: str) -> Webhook:
    return Webhook.objects.create(name=name, url=url)


def deliver(webhook: Webhook, waiting: int) -> Webhook:
    """POSTs to `webhook` that `waiting` Transactions are waiting, waiting for the reply, and records the attempt on
    it. Never raises for what the receiver does."""
    attempted_at = timezone.now()
    body = json.dumps({"event": EVENT, "at": attempted_at.isoformat(), "waiting": waiting})
    request = Request(
        webhook.url,
        data=body.encode(),
        method="POST",
        headers={"Content-Type": "application/json", "User-Agent": "Pursegraph"},
    )
    status: int | None = None
    try:
        with _opener.open(request, timeout=TIMEOUT) as response:
            status = response.status
        outcome = Webhook.Outcome.DELIVERED if 200 <= status < 300 else Webhook.Outcome.HTTP_ERROR
    except HTTPError as error:
        status = error.code
        outcome = Webhook.Outcome.HTTP_ERROR
    except URLError as error:
        timed_out = isinstance(error.reason, TimeoutError | socket.timeout)
        outcome = Webhook.Outcome.TIMED_OUT if timed_out else Webhook.Outcome.UNREACHABLE
    except TimeoutError:
        outcome = Webhook.Outcome.TIMED_OUT
    except (OSError, HTTPException, ValueError):
        outcome = Webhook.Outcome.UNREACHABLE
    attempt = {
        "last_attempt_at": attempted_at,
        "last_outcome": outcome,
        "last_status": status if outcome == Webhook.Outcome.HTTP_ERROR else None,
    }
    for field, value in attempt.items():
        setattr(webhook, field, value)
    # An update rather than a save: the Webhook may have been deleted meanwhile.
    Webhook.objects.filter(pk=webhook.pk).update(**attempt)
    return webhook


def fire_if_waiting() -> None:
    """Calls every Webhook once the current database transaction commits, if a Transaction is waiting for a
    Suggestion then. Not if it rolls back. Outside a transaction, at once."""
    transaction.on_commit(_send_to_all, robust=True)


def _send_to_all() -> None:
    waiting = suggestions.waiting_count()
    if not waiting:
        return
    for webhook in Webhook.objects.all():
        threading.Thread(
            target=_deliver_in_background,
            args=(webhook, waiting),
            name=f"webhook-{webhook.pk}",
            # Not a daemon, so a command such as `reparse --apply` doesn't exit before its deliveries are sent.
            daemon=False,
        ).start()


def _deliver_in_background(webhook: Webhook, waiting: int) -> None:
    try:
        deliver(webhook, waiting)
    except Exception:
        logger.exception("Calling the Webhook %s failed", webhook.pk)
    finally:
        # The thread's own database connection.
        connection.close()
