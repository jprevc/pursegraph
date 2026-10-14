"""Recognising Transfers at import, and pairing their two sides.

The IBAN rule makes a new Transaction paying to or from any Household IBAN a Transfer. Pairing
then links each unpaired Transfer side with the Transaction in another Account that has the equal
and opposite amount within ±3 days, the closest date winning. Pairing works in either import
order: a side already imported finds its counterpart among the new Transactions, and a new side
finds it among the existing ones. A counterpart categorized by a Rule or the LLM becomes a
Transfer. A tie between candidates leaves the side unpaired and in the Review queue as an
ambiguous pairing, until a Member picks its counterpart or keeps it one-sided. Manual outcomes are never changed: a manual Transfer may be paired, but a manually
categorized Transaction is never a counterpart.
"""

from dataclasses import dataclass
from datetime import timedelta

from django.db import transaction
from django.db.models import Q, Subquery

from .models import AccountIBAN, Source, Transaction, TransactionQuerySet

WINDOW = timedelta(days=3)

# The categorized outcomes pairing may turn into a Transfer.
CONVERTIBLE = [Source.RULE, Source.LLM]


@dataclass
class Pairing:
    """What a pairing run did."""

    converted_count: int = 0
    """Categorized Transactions converted to Transfers to pair them."""
    ambiguous_count: int = 0
    """Transfer sides left in the Review queue for a tie between candidates."""


def apply_iban_rule(transactions: TransactionQuerySet) -> None:
    """Makes the unresolved ones of `transactions` whose counterparty IBAN is a Household IBAN Transfers."""
    transactions.unresolved().filter(
        counterparty_iban__in=Subquery(AccountIBAN.objects.values("iban"))
    ).update(is_transfer=True, source=Source.IBAN)


def pair(new: TransactionQuerySet) -> Pairing:
    """Pairs the unpaired Transfer sides among `new`, and those already imported that a Transaction of `new`
    could pair with."""
    result = Pairing()
    with transaction.atomic():
        for side in _sides(new):
            side.refresh_from_db()
            if side.counterpart_id:  # paired as an earlier side's counterpart
                continue
            closest = closest_candidates(side)
            if len(closest) == 1:
                result.converted_count += _link(side, closest[0], source=Source.PAIRING)
            elif closest:
                side.ambiguous_pairing = True
                side.save(update_fields=["ambiguous_pairing"])
                result.ambiguous_count += 1
    return result


class NotACandidate(Exception):
    """The picked Transaction isn't one of the side's closest candidates."""


def settle(side: Transaction, counterpart_pk: int | None) -> None:
    """A Member's pick for an ambiguous pairing: one of its closest candidates, or None to keep it one-sided."""
    with transaction.atomic():
        if counterpart_pk is not None:
            closest = {c.pk: c for c in closest_candidates(side)}
            if counterpart_pk not in closest:
                raise NotACandidate
            _link(side, closest[counterpart_pk], source=Source.MANUAL)
        side.ambiguous_pairing = False
        side.save(update_fields=["ambiguous_pairing"])


def closest_candidates(side: Transaction) -> list[Transaction]:
    """The Transactions `side` could pair with that are closest to it in date: one, or several in a tie."""
    candidates = list(_candidates(side))
    if not candidates:
        return []
    nearest = min(_distance(side, c) for c in candidates)
    return [c for c in candidates if _distance(side, c) == nearest]


def _sides(new: TransactionQuerySet) -> list[Transaction]:
    unpaired = Transaction.objects.filter(
        is_transfer=True, counterpart__isnull=True, ambiguous_pairing=False
    )
    sides = set(unpaired.filter(pk__in=new.values("pk")))
    for t in new.filter(counterpart__isnull=True).filter(_counterpart_outcome()):
        sides.update(unpaired.filter(_within_reach_of(t)))
    return sorted(sides, key=lambda t: (t.date, t.pk))


def _candidates(side: Transaction) -> TransactionQuerySet:
    return (
        Transaction.objects.filter(_within_reach_of(side), counterpart__isnull=True)
        .filter(_counterpart_outcome())
        .select_related("account")
    )


def _within_reach_of(t: Transaction) -> Q:
    """The Transactions in another Account with the equal and opposite amount, within the window."""
    return Q(
        amount=-t.amount,
        date__range=(t.date - WINDOW, t.date + WINDOW),
    ) & ~Q(account_id=t.account_id)


def _counterpart_outcome() -> Q:
    """Outcomes a counterpart may have: a Transfer already, none, or a Category set by a Rule or the LLM."""
    return (
        Q(is_transfer=True)
        | Q(subcategory__isnull=True, is_transfer=False)
        | Q(source__in=CONVERTIBLE)
    )


def _distance(side: Transaction, candidate: Transaction) -> int:
    return abs((candidate.date - side.date).days)


def _link(side: Transaction, counterpart: Transaction, *, source: str) -> int:
    """Pairs the two, settling any ambiguous pairing of either. A `counterpart` that isn't a Transfer yet
    becomes one, set by `source`. Returns 1 if it was categorized before, else 0."""
    converted = int(counterpart.subcategory_id is not None)
    if not counterpart.is_transfer:
        counterpart.subcategory = None
        counterpart.is_transfer = True
        counterpart.source = source
        counterpart.rule = None
    counterpart.counterpart = side
    counterpart.ambiguous_pairing = False
    counterpart.save(
        update_fields=[
            "subcategory",
            "is_transfer",
            "source",
            "rule",
            "counterpart",
            "ambiguous_pairing",
        ]
    )
    side.counterpart = counterpart
    side.ambiguous_pairing = False
    side.save(update_fields=["counterpart", "ambiguous_pairing"])
    return converted
