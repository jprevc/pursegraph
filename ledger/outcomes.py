"""What the Transaction row offers and keeps around a manual outcome: the Household's Most used outcomes, and
the outcomes a save replaced, so that Undo can put them back."""

from django.db import IntegrityError
from django.db import transaction as db_transaction
from django.db.models import Count

from .models import Category, Rule, Subcategory, Transaction

MOST_USED = 5


def most_used_outcomes() -> list[Subcategory]:
    """The Household's most used Subcategories, most Transactions first, ties in the Categories' own order."""
    return list(
        Subcategory.objects.annotate(used=Count("transactions"))
        .filter(used__gt=0)
        .select_related("category")
        .order_by("-used", "category__position", "category_id", "is_catch_all", "position", "id")[
            :MOST_USED
        ]
    )


def picker() -> dict:
    """What every Transaction row's outcome control offers: `categories` with their Subcategories, and
    `most_used`."""
    return {
        "categories": list(Category.objects.prefetch_related("subcategories")),
        "most_used": most_used_outcomes(),
    }


def snapshot(*transactions: Transaction | None) -> list[dict]:
    """The outcomes of the Transactions a save is about to change: the one saved, and the sides it pairs with or
    leaves. Kept in the session (so plain ids), for `restore`."""
    return [
        {
            "pk": t.pk,
            "subcategory": t.subcategory_id,
            "is_transfer": t.is_transfer,
            "source": t.source,
            "rule": t.rule_id,
            "counterpart": t.counterpart_id,
            "ambiguous_pairing": t.ambiguous_pairing,
        }
        for t in transactions
        if t is not None
    ]


class UndoRefused(Exception):
    """What the save replaced can't come back as it was, as something it pointed at has gone or changed since."""


def restore(states: list[dict]) -> None:
    """Puts back the outcomes `snapshot` kept, pairings included: all of them, or none."""
    if any(
        (s["subcategory"] and not Subcategory.objects.filter(pk=s["subcategory"]).exists())
        or (s["counterpart"] and not Transaction.objects.filter(pk=s["counterpart"]).exists())
        for s in states
    ):
        raise UndoRefused
    rules = set(
        Rule.objects.filter(pk__in=[s["rule"] for s in states if s["rule"]]).values_list(
            "pk", flat=True
        )
    )
    pks = [s["pk"] for s in states]
    try:
        with db_transaction.atomic():
            # Unlinked first, so that each pairing can be put back whichever side comes first.
            Transaction.objects.filter(pk__in=pks).update(counterpart=None)
            for s in states:
                Transaction.objects.filter(pk=s["pk"]).update(
                    subcategory_id=s["subcategory"],
                    is_transfer=s["is_transfer"],
                    source=s["source"],
                    rule_id=s["rule"] if s["rule"] in rules else None,
                    counterpart_id=s["counterpart"],
                    ambiguous_pairing=s["ambiguous_pairing"],
                )
    except IntegrityError as error:
        raise UndoRefused from error
