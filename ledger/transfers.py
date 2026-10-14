"""Recognising Transfers at import, and pairing their two sides.

The IBAN rule makes a new Transaction paying to or from any Household IBAN a Transfer. Pairing
then links each unpaired Transfer side with the Transaction in another Account that has the equal
and opposite amount within ±3 days; a side paying to a Household IBAN pairs only within that
IBAN's Account. The closest pairs are linked first. Pairing works in either import order: a side
already imported finds its counterpart among the new Transactions, and a new side finds it among
the existing ones. A counterpart categorized by a Rule or the LLM becomes a Transfer.

A tie, whether a side has several equally close candidates or a candidate several equally close
sides, leaves those sides unpaired and in the Review queue as ambiguous pairings, until a Member
picks a counterpart or keeps the side one-sided, or a later import brings a closer counterpart.

Manual outcomes are never changed: a manual Transfer may be paired, but a manually categorized
Transaction is never a counterpart.
"""

from collections import Counter
from dataclasses import dataclass
from datetime import timedelta
from itertools import groupby

from django.db import transaction
from django.db.models import Q, Subquery

from .models import AccountIBAN, Source, Transaction, TransactionQuerySet
from .rules import OVERWRITABLE

WINDOW = timedelta(days=3)


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
    could pair with, closest pairs first."""
    result = Pairing()
    new_pks = set(new.values_list("pk", flat=True))
    with transaction.atomic():
        # Every possible pair once, as (distance, side, candidate). Locking the candidates keeps a
        # concurrent import from pairing them too.
        possible: dict[frozenset[int], tuple[int, Transaction, Transaction]] = {}
        for side in _sides(new):
            for candidate in _candidates(side).select_for_update(of=("self",)):
                possible.setdefault(
                    frozenset((side.pk, candidate.pk)),
                    (_distance(side, candidate), side, candidate),
                )
        done: set[int] = set()
        ordered = sorted(possible.values(), key=lambda p: (p[0], p[1].date, p[1].pk, p[2].pk))
        for _, group in groupby(ordered, key=lambda p: p[0]):
            open_pairs = [(s, c) for _, s, c in group if s.pk not in done and c.pk not in done]
            # How many open pairs at this distance each Transaction is in; more than one is a tie.
            ends = Counter(t.pk for open_pair in open_pairs for t in open_pair)
            for side, candidate in open_pairs:
                if ends[side.pk] == 1 and ends[candidate.pk] == 1:
                    converted = _link(side, candidate, source=Source.PAIRING)
                    # A new Transaction's Category was set by this very import, so isn't reported.
                    result.converted_count += converted and candidate.pk not in new_pks
                else:
                    for t in (side, candidate):
                        if t.is_transfer and not t.ambiguous_pairing:
                            t.ambiguous_pairing = True
                            t.save(update_fields=["ambiguous_pairing"])
                            result.ambiguous_count += 1
                done |= {side.pk, candidate.pk}
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
    unpaired = Transaction.objects.filter(is_transfer=True, counterpart__isnull=True)
    sides = set(unpaired.filter(pk__in=new.values("pk")))
    for t in new.filter(counterpart__isnull=True).filter(_counterpart_outcome()):
        sides.update(unpaired.filter(_within_reach_of(t)))
    return list(sides)


def _candidates(side: Transaction) -> TransactionQuerySet:
    candidates = (
        Transaction.objects.filter(_within_reach_of(side), counterpart__isnull=True)
        .filter(_counterpart_outcome())
        .select_related("account")
    )
    # Paid to or from a Household IBAN: the other side can only be in that IBAN's Account.
    if side.counterparty_iban and (
        known := AccountIBAN.objects.filter(iban=side.counterparty_iban).first()
    ):
        candidates = candidates.filter(account_id=known.account_id)
    return candidates


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
        | Q(source__in=OVERWRITABLE)
    )


def _distance(side: Transaction, candidate: Transaction) -> int:
    return abs((candidate.date - side.date).days)


def _link(side: Transaction, counterpart: Transaction, *, source: str) -> bool:
    """Pairs the two, settling any ambiguous pairing of either. A `counterpart` that isn't a Transfer yet
    becomes one, set by `source`. Returns whether it was categorized before."""
    converted = counterpart.subcategory_id is not None
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
