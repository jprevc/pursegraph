"""LLM suggestions: Transactions still unresolved after Rules get a Subcategory suggested in the background.

`run_once` asks a Suggester about each unresolved Transaction that has no suggestion yet and stores
the suggestion with its confidence. One at least as confident as the auto-accept threshold also
sets the outcome (`source = llm`); the rest wait in the Review queue with the suggestion
preselected. The `categorize_worker` command calls it in a loop, backing off while the Suggester
is unavailable. Imports never wait for it.

Admins retune it: changing the threshold applies from then on, and lowering it can accept the
queued suggestions that now clear it; re-suggesting the queue clears its stored suggestions so
they are asked again, such as after a model or prompt change.
"""

from collections.abc import Iterable
from dataclasses import dataclass
from decimal import Decimal
from typing import Protocol

from django.db import transaction
from django.db.models import QuerySet
from django.db.models.functions import Lower

from .models import Setting, Source, Subcategory, Transaction

# The `raw` keys whose text helps tell what a Transaction was for, across the parsers.
DETAIL_KEYS = ("Type", "n26_category", "purpose", "to", "from", "reference")

# At most this many few-shot examples, the most recent merchants first, to keep the prompt small.
MAX_EXAMPLES = 100

# Transactions asked about per run, so the loop notices new work and failures between batches.
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
    """What a Suggester is asked: one Transaction, the Subcategories to choose from, and examples."""

    direction: str
    """"in" or "out"."""
    amount: Decimal
    """Without its sign."""
    description: str
    detail: str
    """Text from the Transaction's `raw` that the parser saw, such as a purpose line."""
    subcategories: list[Subcategory]
    """With their Category."""
    examples: list[Example]


@dataclass(frozen=True)
class Suggestion:
    subcategory: Subcategory
    """One of the Query's Subcategories."""
    confidence: float
    """The model's own probability of `subcategory`, from 0 to 1."""


class SuggestionsUnavailable(Exception):
    """The Suggester can't answer at all, such as when Ollama is unreachable."""


class NoSuggestion(Exception):
    """The Suggester answered about one Transaction, but unusably; it goes to the Review queue unsuggested."""


class Suggester(Protocol):
    def suggest(self, query: Query) -> Suggestion:
        """Raises SuggestionsUnavailable when it can't answer, NoSuggestion when its answer is unusable."""
        ...


@dataclass(frozen=True)
class Run:
    """What one `run_once` did."""

    asked: int
    """Transactions it asked the Suggester about."""
    error: SuggestionsUnavailable | None = None
    """Why it stopped early, if the Suggester failed."""


def run_once(suggester: Suggester) -> Run:
    """Asks `suggester` about a batch of unresolved Transactions with no suggestion.

    Stops at the first failure, which the sidebar then shows until a call succeeds again."""
    pending = list(_awaiting_suggestion()[:BATCH_SIZE])
    for done, candidate in enumerate(pending):
        try:
            suggestion: Suggestion | None = suggester.suggest(_query(candidate))
        except SuggestionsUnavailable as error:
            Setting.put(Setting.SUGGESTIONS_UNAVAILABLE, "1")
            return Run(done, error)
        except NoSuggestion:
            suggestion = None
        Setting.put(Setting.SUGGESTIONS_UNAVAILABLE, "")
        _store(candidate.pk, suggestion)
    return Run(len(pending))


def threshold() -> Decimal:
    """The auto-accept threshold: a suggestion at least this confident sets the outcome by itself."""
    return Decimal(Setting.get(Setting.AUTO_ACCEPT_THRESHOLD))


def set_threshold(value: Decimal) -> None:
    """Changes the threshold for suggestions from now on; outcomes already set stay, whichever way it moves."""
    Setting.put(Setting.AUTO_ACCEPT_THRESHOLD, str(value))


def suggestions_clearing_threshold() -> "QuerySet[Transaction]":
    """The queued Transactions whose stored suggestion is at least as confident as the threshold: the worker
    accepts these as it stores them, and lowering the threshold leaves some."""
    return Transaction.objects.unresolved().filter(
        suggested_subcategory__isnull=False, confidence__gte=threshold()
    )


def accept_suggestions_clearing_threshold(pks: Iterable[int]) -> int:
    """Accepts the suggestions of the Transactions `pks` that still clear the threshold, as the worker would
    have (`source = llm`). Returns how many."""
    with transaction.atomic():
        return _accept_clearing(Transaction.objects.filter(pk__in=pks))


def resuggest_queue() -> int:
    """Clears the stored suggestions of the queued Transactions, so the worker asks about them again,
    such as after a model or prompt change. Returns how many it cleared."""
    return (
        Transaction.objects.unresolved()
        .filter(confidence__isnull=False)
        .update(suggested_subcategory=None, confidence=None)
    )


def suggestions_unavailable() -> bool:
    """Whether the last call to the Suggester failed."""
    return Setting.get(Setting.SUGGESTIONS_UNAVAILABLE) == "1"


def backoff(attempt: int) -> int:
    """Seconds to wait after the `attempt`-th failure in a row: 5, 10, 20, … up to 5 minutes."""
    return min(5 * 2 ** (attempt - 1), 300)


def _awaiting_suggestion() -> "QuerySet[Transaction]":
    return Transaction.objects.unresolved().filter(
        suggested_subcategory__isnull=True, confidence__isnull=True
    )


def _store(pk: int, suggestion: Suggestion | None) -> None:
    """Stores the suggestion, and accepts it if it's confident enough, unless the Transaction got
    an outcome or a suggestion meanwhile, such as from a Member. With no suggestion, it stores
    confidence 0 so the Transaction isn't asked about again. A suggestion of a Subcategory deleted
    meanwhile isn't stored, so the Transaction is asked about again."""
    with transaction.atomic():
        candidate = _awaiting_suggestion().select_for_update().filter(pk=pk).first()
        if candidate is None:
            return
        if suggestion is None:
            candidate.confidence = 0
            candidate.save(update_fields=["confidence"])
            return
        if not Subcategory.objects.filter(pk=suggestion.subcategory.pk).exists():
            return
        candidate.suggested_subcategory = suggestion.subcategory
        candidate.confidence = suggestion.confidence
        candidate.save(update_fields=["suggested_subcategory", "confidence"])
        _accept_clearing(Transaction.objects.filter(pk=pk))


def _accept_clearing(transactions: "QuerySet[Transaction]") -> int:
    """Accepts the suggestions of `transactions` that clear the threshold as it is now. Runs in a
    transaction; returns how many."""
    clearing = list(
        transactions.filter(pk__in=suggestions_clearing_threshold())
        .select_for_update(of=("self",))
        .select_related("suggested_subcategory")
    )
    for candidate in clearing:
        candidate.set_outcome(candidate.suggested_subcategory, source=Source.LLM)
    return len(clearing)


def _query(candidate: Transaction) -> Query:
    return Query(
        direction=_direction(candidate),
        amount=abs(candidate.amount),
        description=candidate.description,
        detail=_detail(candidate),
        # Read for each query, so a Subcategory deleted during a batch is no longer offered.
        subcategories=list(Subcategory.objects.select_related("category").order_by("category")),
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
