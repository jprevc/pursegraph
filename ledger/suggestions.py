"""Suggestions: Transactions still unresolved after Rules get a Subcategory suggested by a Categorizer.

A Categorizer fetches the unresolved Transactions that have no suggestion yet (`waiting`) through the Categorizer
API (ledger/api.py) and sends back a Suggestion with its confidence (`receive`). One at least as confident as the
auto-accept threshold also sets the outcome (`source = categorizer`); the rest wait in the Review queue with the
suggestion preselected. Imports never wait for it.

Admins retune it: changing the threshold applies from then on, and lowering it can accept the
queued suggestions that now clear it; re-suggesting the queue clears its stored suggestions so
they are asked again, such as after a model or prompt change.
"""

from collections.abc import Iterable
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from enum import StrEnum

from django.db import transaction
from django.db.models import Min, QuerySet
from django.db.models.functions import Lower
from django.utils import timezone

from . import categorizers
from .models import CategorizerToken, Setting, Source, Subcategory, Transaction

# The `raw` keys whose text helps tell what a Transaction was for, across the parsers.
DETAIL_KEYS = ("Type", "n26_category", "purpose", "to", "from", "reference")

# At most this many few-shot examples, the most recent merchants first, to keep a Categorizer's request small.
MAX_EXAMPLES = 100

# Transactions a Categorizer fetches at once by default.
BATCH_SIZE = 50


@dataclass(frozen=True)
class Example:
    """A Member's latest manual outcome for one merchant: how this household categorizes it."""

    direction: str
    description: str
    detail: str
    subcategory: Subcategory


@dataclass(frozen=True)
class Query:
    """What a Categorizer is asked about one Transaction, with examples."""

    direction: str
    """"in" or "out"."""
    amount: Decimal
    """Without its sign."""
    description: str
    detail: str
    """Text from the Transaction's `raw` that the parser saw, such as a purpose line."""
    examples: list[Example]


@dataclass(frozen=True)
class Suggestion:
    subcategory: Subcategory
    """One of the Subcategories offered."""
    confidence: float
    """The Categorizer's own probability of `subcategory`, from 0 to 1."""


def threshold() -> Decimal:
    """The auto-accept threshold: a suggestion at least this confident sets the outcome by itself."""
    return Decimal(Setting.get(Setting.AUTO_ACCEPT_THRESHOLD))


def set_threshold(value: Decimal) -> None:
    """Changes the threshold for suggestions from now on; outcomes already set stay, whichever way it moves."""
    Setting.put(Setting.AUTO_ACCEPT_THRESHOLD, str(value))


def suggestions_clearing_threshold() -> "QuerySet[Transaction]":
    """The queued Transactions whose stored suggestion is at least as confident as the threshold: `receive`
    accepts these as it stores them, and lowering the threshold leaves some."""
    return Transaction.objects.unresolved().filter(
        suggested_subcategory__isnull=False, confidence__gte=threshold()
    )


def accept_suggestions_clearing_threshold(pks: Iterable[int]) -> int:
    """Accepts the suggestions of the Transactions `pks` that still clear the threshold, as `receive` would
    have (`source = categorizer`). Returns how many."""
    with transaction.atomic():
        return _accept_clearing(Transaction.objects.filter(pk__in=pks))


def resuggest_queue() -> int:
    """Clears the stored suggestions of the queued Transactions, so Categorizers are asked about them again,
    such as after a model or prompt change, and calls the Webhooks if any are waiting then. Returns how many it
    cleared."""
    from . import webhooks

    with transaction.atomic():
        cleared = (
            Transaction.objects.unresolved()
            .filter(confidence__isnull=False)
            .update(suggested_subcategory=None, confidence=None)
        )
        webhooks.fire_if_waiting()
    return cleared


def waiting_count() -> int:
    """How many Transactions are waiting for a Suggestion."""
    return _awaiting_suggestion().count()


# The threshold's steps on the Suggestions page, in % sure; the chart's bins are as wide, so each bin is wholly on
# one side of the line.
STEPS = range(50, 101, 5)
BIN_WIDTH = 5


@dataclass(frozen=True)
class Overview:
    """The Suggestions page's figures."""

    queued: int
    """Transactions in the Review queue."""
    with_suggestion: int
    """Queued Transactions with a suggestion."""
    waiting: int
    """Unresolved Transactions waiting for a Suggestion."""
    waiting_since: datetime | None
    """When the Statement of the one waiting longest was imported: the first Statement it was on."""
    last_suggestion: CategorizerToken | None
    """The token that sent the last Suggestion stored, with when (`last_suggestion_at`); it may be revoked since."""
    by_categorizers_this_month: int
    """Transactions dated this month whose outcome a Categorizer set."""
    askable_again: int
    """Queued Transactions with an answer, usable or not, that `resuggest_queue` would clear."""
    cant_ask_again: "CantAskAgain | None"
    """Why Ask again can't run, or None when it can."""
    bins: list[int]
    """The queued suggestions by how sure they are, in BIN_WIDTH % bins from 0 to 100 %."""
    clearing: dict[int, int]
    """For each of the threshold's STEPS, how many queued suggestions are at least that sure."""


def overview() -> Overview:
    queued = Transaction.objects.unresolved()
    sureness = list(
        queued.filter(suggested_subcategory__isnull=False, confidence__isnull=False).values_list(
            "confidence", flat=True
        )
    )
    bins = [0] * (100 // BIN_WIDTH)
    for confidence in sureness:
        bins[min(int(confidence * 100 + 1e-9) // BIN_WIDTH, len(bins) - 1)] += 1
    today = timezone.localdate()
    return Overview(
        queued=queued.count(),
        with_suggestion=len(sureness),
        waiting=waiting_count(),
        waiting_since=_awaiting_suggestion().aggregate(since=Min("statements__imported_at"))[
            "since"
        ],
        last_suggestion=CategorizerToken.objects.filter(last_suggestion_at__isnull=False)
        .order_by("-last_suggestion_at")
        .first(),
        by_categorizers_this_month=Transaction.objects.filter(
            source=Source.CATEGORIZER, date__year=today.year, date__month=today.month
        ).count(),
        askable_again=queued.filter(confidence__isnull=False).count(),
        cant_ask_again=cant_ask_again(),
        bins=bins,
        clearing={step: sum(c * 100 + 1e-9 >= step for c in sureness) for step in STEPS},
    )


class CantAskAgain(StrEnum):
    """Why Ask again can't run, in the order the Suggestions page checks them."""

    NO_CATEGORIZER = "no_categorizer"
    """No token is unrevoked, so nothing would suggest the cleared Transactions again."""
    EMPTY_QUEUE = "empty_queue"
    """The Review queue is empty."""
    NO_SUGGESTION = "no_suggestion"
    """Nothing in the Review queue has a Categorizer's answer to clear yet."""


def cant_ask_again() -> CantAskAgain | None:
    """Why Ask again can't run now, or None when it can."""
    if not categorizers.active().exists():
        return CantAskAgain.NO_CATEGORIZER
    if not Transaction.objects.unresolved().exists():
        return CantAskAgain.EMPTY_QUEUE
    if not Transaction.objects.unresolved().filter(confidence__isnull=False).exists():
        return CantAskAgain.NO_SUGGESTION
    return None


def _awaiting_suggestion() -> "QuerySet[Transaction]":
    return Transaction.objects.unresolved().filter(
        suggested_subcategory__isnull=True, confidence__isnull=True
    )


@dataclass(frozen=True)
class Received:
    """What became of a Suggestion sent back by a Categorizer."""

    stored: bool
    """False when it was ignored: the Transaction already had an outcome or a Suggestion, or the Subcategory was
    deleted meanwhile."""
    accepted: bool
    """It cleared the auto-accept threshold and set the outcome."""


def waiting(limit: int) -> tuple[list[Subcategory], list[tuple[int, Query]]]:
    """For a Categorizer: the Subcategories to choose from, and up to `limit` Transactions waiting for a
    Suggestion, oldest first, each by id with what it is asked. Nothing is claimed: the same ones come back until
    Suggestions for them arrive."""
    return _subcategories(), [
        (candidate.pk, _query(candidate)) for candidate in _awaiting_suggestion()[:limit]
    ]


def receive(pk: int, suggestion: Suggestion | None, token: CategorizerToken) -> Received:
    """Stores a Categorizer's Suggestion for the Transaction `pk`, or with None that it has none, and records that
    `token` sent it."""
    with transaction.atomic():
        received = _store(pk, suggestion)
        if received.stored:
            token.last_suggestion_at = timezone.now()
            token.save(update_fields=["last_suggestion_at"])
    return received


def label(subcategory: Subcategory) -> str:
    """How a Categorizer sees a Subcategory: "Category > Subcategory"."""
    return f"{subcategory.category.name} > {subcategory.name}"


def _store(pk: int, suggestion: Suggestion | None) -> Received:
    """Stores the suggestion, and accepts it if it's confident enough, unless the Transaction got
    an outcome or a suggestion meanwhile, such as from a Member. With no suggestion, it stores
    confidence 0 so the Transaction isn't asked about again. A suggestion of a Subcategory deleted
    meanwhile isn't stored, so the Transaction is asked about again."""
    with transaction.atomic():
        candidate = _awaiting_suggestion().select_for_update().filter(pk=pk).first()
        if candidate is None:
            return Received(stored=False, accepted=False)
        if suggestion is None:
            candidate.confidence = 0
            candidate.save(update_fields=["confidence"])
            return Received(stored=True, accepted=False)
        if not Subcategory.objects.filter(pk=suggestion.subcategory.pk).exists():
            return Received(stored=False, accepted=False)
        candidate.suggested_subcategory = suggestion.subcategory
        candidate.confidence = suggestion.confidence
        candidate.save(update_fields=["suggested_subcategory", "confidence"])
        return Received(
            stored=True, accepted=bool(_accept_clearing(Transaction.objects.filter(pk=pk)))
        )


def _accept_clearing(transactions: "QuerySet[Transaction]") -> int:
    """Accepts the suggestions of `transactions` that clear the threshold as it is now. Runs in a
    transaction; returns how many."""
    clearing = list(
        transactions.filter(pk__in=suggestions_clearing_threshold())
        .select_for_update(of=("self",))
        .select_related("suggested_subcategory")
    )
    for candidate in clearing:
        candidate.set_outcome(candidate.suggested_subcategory, source=Source.CATEGORIZER)
    return len(clearing)


def _subcategories() -> list[Subcategory]:
    return list(Subcategory.objects.select_related("category").order_by("category"))


def _query(candidate: Transaction) -> Query:
    return Query(
        direction=_direction(candidate),
        amount=abs(candidate.amount),
        description=candidate.description,
        detail=_detail(candidate),
        examples=_examples(candidate),
    )


def _examples(candidate: Transaction) -> list[Example]:
    """The latest manual Subcategory of each merchant other than `candidate`'s; that one would be a Rule's job."""
    latest_per_merchant = (
        Transaction.objects.filter(source=Source.MANUAL, subcategory__isnull=False)
        .annotate(merchant=Lower("description"))
        .exclude(merchant=candidate.description.lower())
        .order_by("merchant", "-date", "-id")
        .distinct("merchant")
    )
    latest = Transaction.objects.filter(pk__in=[t.pk for t in latest_per_merchant.only("pk")])
    return [
        Example(_direction(t), t.description, _detail(t), t.subcategory)
        for t in latest.select_related("subcategory__category").order_by("-date", "-id")[
            :MAX_EXAMPLES
        ]
        if t.subcategory
    ]


def _direction(t: Transaction) -> str:
    return "in" if t.amount > 0 else "out"


def _detail(t: Transaction) -> str:
    raw = t.raw if isinstance(t.raw, dict) else {}
    parts = [str(raw[key]).strip() for key in DETAIL_KEYS if raw.get(key)]
    if t.counterparty_name and t.counterparty_name != t.description:
        parts.insert(0, t.counterparty_name)
    return "; ".join(part for part in parts if part)
