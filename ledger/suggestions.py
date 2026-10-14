"""LLM suggestions: Transactions still unresolved after Rules get a Subcategory suggested in the background.

`run_once` asks a Suggester about each unresolved Transaction that has no suggestion yet and stores
the suggestion with its confidence. One at least as confident as the auto-accept threshold also
sets the outcome (`source = llm`); the rest wait in the Review queue with the suggestion
preselected. The `categorize_worker` command calls it in a loop, backing off while the Suggester
is unavailable. Imports never wait for it.
"""

from dataclasses import dataclass
from decimal import Decimal
from typing import Protocol

from django.db import transaction

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
    """The Suggester couldn't answer, such as when Ollama is unreachable."""


class Suggester(Protocol):
    def suggest(self, query: Query) -> Suggestion:
        """Raises SuggestionsUnavailable when it can't answer."""
        ...


@dataclass(frozen=True)
class Run:
    """What one `run_once` did."""

    suggested: int
    """Transactions it stored a suggestion for, or found decided meanwhile."""
    error: SuggestionsUnavailable | None = None
    """Why it stopped early, if the Suggester failed."""


def run_once(suggester: Suggester) -> Run:
    """Asks `suggester` about a batch of unresolved Transactions with no suggestion.

    Stops at the first failure, which the sidebar then shows until a call succeeds again."""
    pending = list(_awaiting_suggestion()[:BATCH_SIZE])
    if not pending:
        return Run(0)
    subcategories = list(Subcategory.objects.select_related("category").order_by("category"))
    threshold = float(Setting.get(Setting.AUTO_ACCEPT_THRESHOLD))
    for done, candidate in enumerate(pending):
        try:
            suggestion = suggester.suggest(_query(candidate, subcategories))
        except SuggestionsUnavailable as error:
            Setting.put(Setting.SUGGESTIONS_UNAVAILABLE, "1")
            return Run(done, error)
        Setting.put(Setting.SUGGESTIONS_UNAVAILABLE, "")
        _store(candidate.pk, suggestion, threshold)
    return Run(len(pending))


def suggestions_unavailable() -> bool:
    """Whether the last call to the Suggester failed."""
    return Setting.get(Setting.SUGGESTIONS_UNAVAILABLE) == "1"


def backoff(attempt: int) -> int:
    """Seconds to wait after the `attempt`-th failure in a row: 5, 10, 20, … up to 5 minutes."""
    return min(5 * 2 ** (attempt - 1), 300)


def _awaiting_suggestion():
    return Transaction.objects.unresolved().filter(suggested_subcategory__isnull=True)


def _store(pk: int, suggestion: Suggestion, threshold: float) -> None:
    """Stores the suggestion, and accepts it if it's confident enough, unless the Transaction got
    an outcome or a suggestion meanwhile, such as from a Member."""
    with transaction.atomic():
        candidate = _awaiting_suggestion().select_for_update().filter(pk=pk).first()
        if candidate is None or not Subcategory.objects.filter(pk=suggestion.subcategory.pk):
            return
        candidate.suggested_subcategory = suggestion.subcategory
        candidate.confidence = suggestion.confidence
        candidate.save(update_fields=["suggested_subcategory", "confidence"])
        if suggestion.confidence >= threshold:
            candidate.set_outcome(suggestion.subcategory, source=Source.LLM)


def _query(candidate: Transaction, subcategories: list[Subcategory]) -> Query:
    return Query(
        direction=_direction(candidate),
        amount=abs(candidate.amount),
        description=candidate.description,
        detail=_detail(candidate),
        subcategories=subcategories,
        examples=_examples(candidate),
    )


def _examples(candidate: Transaction) -> list[Example]:
    """The latest manual Subcategory of each merchant other than `candidate`'s; that one would be a Rule's job."""
    latest_per_merchant = (
        Transaction.objects.filter(source=Source.MANUAL, subcategory__isnull=False)
        .exclude(description__iexact=candidate.description)
        .order_by("description", "-date", "-id")
        .distinct("description")
    )
    latest = Transaction.objects.filter(pk__in=latest_per_merchant.values("pk"))
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
