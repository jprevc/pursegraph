"""What the Transaction row offers and keeps around a manual outcome: the Household's Most used outcomes, a Split
into Parts, and the outcomes a save replaced, so that Undo can put them back."""

from decimal import Decimal

from django.db import IntegrityError
from django.db import transaction as db_transaction
from django.db.models import Count
from django.utils.translation import gettext as _

from pursegraph import figures

from .models import Category, Part, Rule, Source, Subcategory, Transaction

CENT = Decimal("0.01")

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
            "is_split": t.is_split,
            # (Subcategory id, amount) of each Part, the amount as text.
            "parts": [[p.subcategory_id, str(p.amount)] for p in t.parts.all()],
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
    """Puts back the outcomes `snapshot` kept, pairings, Parts and the Rules that set them included: all of them, or
    none. Refused once a Subcategory, Rule or other side they name is gone."""
    pks = [s["pk"] for s in states]
    try:
        with db_transaction.atomic():
            for model, named in (
                (
                    Subcategory,
                    {s["subcategory"] for s in states if s["subcategory"]}
                    | {sub for s in states for sub, _amount in s.get("parts", [])},
                ),
                (Rule, {s["rule"] for s in states if s["rule"]}),
                (Transaction, {s["counterpart"] for s in states if s["counterpart"]}),
            ):
                if model.objects.select_for_update().filter(pk__in=named).count() != len(named):
                    raise UndoRefused
            # Unlinked first, so that each pairing can be put back whichever side comes first.
            Transaction.objects.filter(pk__in=pks).update(counterpart=None)
            Part.objects.filter(transaction__in=pks).delete()
            for s in states:
                Transaction.objects.filter(pk=s["pk"]).update(
                    subcategory_id=s["subcategory"],
                    is_transfer=s["is_transfer"],
                    is_split=s.get("is_split", False),
                    source=s["source"],
                    rule_id=s["rule"],
                    counterpart_id=s["counterpart"],
                    ambiguous_pairing=s["ambiguous_pairing"],
                )
                Part.objects.bulk_create(
                    Part(transaction_id=s["pk"], subcategory_id=sub, amount=Decimal(amount))
                    for sub, amount in s.get("parts", [])
                )
    except IntegrityError as error:
        raise UndoRefused from error


class SplitRefused(Exception):
    """The Parts don't make a Split of the Transaction. The message says why, for the Member."""


def split(transaction: Transaction, parts: list[tuple[Subcategory, Decimal]]) -> list[dict]:
    """Makes `transaction`'s outcome a Split into `parts`, by hand, replacing whatever it was: it leaves Transfer as
    picking a Subcategory does, and the Review queue. Returns what Undo needs to put back, as `snapshot` does.

    Refused, with nothing changed, unless there are at least two Parts, each in a different Subcategory, none zero,
    all in the Transaction's direction, all spending or all income, adding up to its amount to the cent."""
    _check_split(transaction, parts)
    with db_transaction.atomic():
        transaction = Transaction.objects.select_for_update().get(pk=transaction.pk)
        if transaction.amount != sum((amount for _sub, amount in parts), Decimal(0)):
            raise SplitRefused(_("The Transaction's amount changed meanwhile."))
        before = snapshot(transaction, transaction.counterpart)
        if transaction.counterpart_id:
            Transaction.objects.filter(pk=transaction.counterpart_id).update(counterpart=None)
        transaction.parts.all().delete()
        Transaction.objects.filter(pk=transaction.pk).update(
            subcategory=None,
            is_transfer=False,
            is_split=True,
            source=Source.MANUAL,
            rule=None,
            counterpart=None,
            ambiguous_pairing=False,
        )
        Part.objects.bulk_create(
            Part(transaction=transaction, subcategory=subcategory, amount=amount)
            for subcategory, amount in parts
        )
    return before


def _check_split(transaction: Transaction, parts: list[tuple[Subcategory, Decimal]]) -> None:
    if len(parts) < 2:
        raise SplitRefused(_("A Split needs at least two Parts."))
    subcategories = [subcategory for subcategory, _amount in parts]
    if len({s.pk for s in subcategories}) < len(subcategories):
        raise SplitRefused(_("Each Part needs a Subcategory of its own."))
    amounts = [amount for _sub, amount in parts]
    if any(amount != amount.quantize(CENT) for amount in amounts):
        raise SplitRefused(_("Each Part is an amount to the cent."))
    if any(amount == 0 for amount in amounts):
        raise SplitRefused(_("A Part can't be zero."))
    if any((amount > 0) != (transaction.amount > 0) for amount in amounts):
        raise SplitRefused(
            _("Every Part is money in, as the Transaction is.")
            if transaction.amount > 0
            else _("Every Part is money out, as the Transaction is.")
        )
    if len({s.category.kind for s in subcategories}) > 1:
        raise SplitRefused(_("A Split's Parts are all spending or all income."))
    total = sum(amounts, Decimal(0))
    if total != transaction.amount:
        raise SplitRefused(
            _("The Parts add up to %(total)s, not the Transaction's %(amount)s.")
            % {"total": figures.money(abs(total)), "amount": figures.money(abs(transaction.amount))}
        )
