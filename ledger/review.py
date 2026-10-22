"""The Review queue (docs/design/review-queue.md): the Transactions waiting for an outcome, in groups of one exact
description that are decided together, with the outcome the description got last time."""

from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from django.db.models import Q

from .models import SOURCE_CAPTIONS, Source, Subcategory, Transaction


@dataclass
class Group:
    """Transactions in the Review queue with one exact description, oldest first. An ambiguous Transfer side is a
    group of its own, as its other side is picked for it alone."""

    transactions: list[Transaction]

    @property
    def description(self) -> str:
        return self.transactions[0].description

    @property
    def size(self) -> int:
        return len(self.transactions)

    @property
    def newest(self) -> Transaction:
        return self.transactions[-1]

    @property
    def key(self) -> int:
        """The id that names the group in a URL: its newest Transaction's."""
        return self.newest.pk

    @property
    def pks(self) -> list[int]:
        return [t.pk for t in self.transactions]

    @property
    def total(self) -> Decimal:
        return sum((t.amount for t in self.transactions), Decimal(0))

    @property
    def ambiguous(self) -> bool:
        return self.transactions[0].ambiguous_pairing

    @property
    def waiting(self) -> bool:
        return any(t.is_unresolved or t.ambiguous_pairing for t in self.transactions)

    @property
    def counterparty(self) -> str:
        """The newest counterparty named."""
        return next(
            (t.counterparty_name for t in reversed(self.transactions) if t.counterparty_name), ""
        )

    @property
    def _suggested(self) -> Transaction | None:
        return next((t for t in reversed(self.transactions) if t.pending_suggestion_id), None)

    @property
    def suggestion(self) -> Subcategory | None:
        """The newest suggestion among its Transactions, accepted for all of them at once."""
        suggested = self._suggested
        return suggested.suggested_subcategory if suggested else None

    @property
    def confidence(self) -> float | None:
        suggested = self._suggested
        return suggested.confidence if suggested else None


def _queryset():
    return Transaction.objects.select_related(
        "account", "subcategory__category", "suggested_subcategory__category"
    ).order_by("date", "id")


def _sorted(groups: list[Group]) -> list[Group]:
    """Newest first, by their newest Transaction."""
    return sorted(groups, key=lambda g: (g.newest.date, g.newest.pk), reverse=True)


def waiting_groups() -> list[Group]:
    """The Review queue's groups, newest first."""
    by_description: dict[str, Group] = {}
    alone: list[Group] = []
    for t in _queryset().filter(pk__in=Transaction.objects.in_review_queue().values("pk")):
        if t.ambiguous_pairing:
            alone.append(Group([t]))
        elif group := by_description.get(t.description):
            group.transactions.append(t)
        else:
            by_description[t.description] = Group([t])
    return _sorted([*by_description.values(), *alone])


def group_of(pks: list[int]) -> Group | None:
    """The Transactions `pks` as one group, whatever their outcome now: a group decided just now."""
    transactions = list(_queryset().filter(pk__in=pks))
    return Group(transactions) if transactions else None


def sorted_groups(groups: list[Group]) -> list[Group]:
    return _sorted(groups)


@dataclass(frozen=True)
class LastTime:
    """The outcome the newest Transaction with a description got outside the Review queue, and how many of the
    description's Transactions have it."""

    subcategory: Subcategory | None
    is_transfer: bool
    date: date
    source: str
    count: int

    @property
    def outcome(self) -> str:
        """As an outcome form posts it: the Subcategory's id or "transfer"."""
        return str(self.subcategory.pk) if self.subcategory else "transfer"

    @property
    def source_caption(self) -> str:
        return str(SOURCE_CAPTIONS[Source(self.source)]) if self.source else ""


def last_time(description: str, exclude: list[int] = ()) -> LastTime | None:  # type: ignore[assignment]
    """What the exact `description` got last time, leaving out the Transactions `exclude` (the ones being decided);
    None for a description never decided."""
    decided = (
        Transaction.objects.filter(description=description, ambiguous_pairing=False)
        .filter(Q(subcategory__isnull=False) | Q(is_transfer=True))
        .exclude(pk__in=exclude)
    )
    newest = decided.select_related("subcategory__category").order_by("-date", "-id").first()
    if newest is None:
        return None
    return LastTime(
        subcategory=newest.subcategory,
        is_transfer=newest.is_transfer,
        date=newest.date,
        source=newest.source,
        count=decided.filter(
            subcategory=newest.subcategory, is_transfer=newest.is_transfer
        ).count(),
    )


def completed_month(decided: list[int]) -> date | None:
    """The first day of the newest month that the Transactions `decided` fall in and that is now Complete: every
    Account has a Statement for it, it is over, and nothing in it is awaiting review."""
    from dashboard.completeness import COMPLETE, Tracking
    from dashboard.periods import Period

    from .models import Account

    months = sorted(
        {
            d.replace(day=1)
            for d in Transaction.objects.filter(pk__in=decided).values_list("date", flat=True)
        },
        reverse=True,
    )
    tracking = Tracking(Account.objects.all())
    queue = Transaction.objects.in_review_queue()
    for month in months:
        period = Period.month(month.year, month.month)
        if (
            tracking.month(period).state == COMPLETE
            and period.end < tracking.today
            and not queue.filter(date__range=(period.start, period.end)).exists()
        ):
            return month
    return None
