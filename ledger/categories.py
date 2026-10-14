"""Editing the two-level Category list while keeping its invariants: every Category has exactly one
catch-all Subcategory, listed last; a catch-all can't be deleted; a Category is deleted only when empty."""

from django.db import transaction
from django.db.models import Max
from django.utils.translation import gettext as _

from .models import Category, Rule, Subcategory, Transaction


class CategoryEditRefused(Exception):
    """The change would break an invariant. The message is shown to the admin."""


def add_category(name: str, kind: str) -> Category:
    with transaction.atomic():
        category = Category.objects.create(
            name=name, kind=kind, position=_next_position(Category.objects.all())
        )
        # Stored data, so not translated; named like the seeded catch-alls.
        catch_all = "Other income" if kind == Category.Kind.INCOME else "Other"
        Subcategory.objects.create(category=category, name=catch_all, is_catch_all=True)
    return category


def add_subcategory(category: Category, name: str) -> Subcategory:
    position = _next_position(category.subcategories.filter(is_catch_all=False))
    return Subcategory.objects.create(category=category, name=name, position=position)


def rename(item: Category | Subcategory, name: str) -> None:
    item.name = name
    item.save(update_fields=["name"])


def _next_position(siblings) -> int:
    last = siblings.aggregate(last=Max("position"))["last"]
    return 0 if last is None else last + 1


def move_category(category: Category, direction: str) -> None:
    _move(list(Category.objects.all()), category, direction)


def move_subcategory(subcategory: Subcategory, direction: str) -> None:
    if not subcategory.is_catch_all:
        _move(
            list(subcategory.category.subcategories.filter(is_catch_all=False)),
            subcategory,
            direction,
        )


def _move(siblings, item, direction):
    """Swaps `item` with its neighbour in `direction` ("up" or "down") and renumbers the siblings."""
    i = siblings.index(item)
    j = i - 1 if direction == "up" else i + 1
    if not 0 <= j < len(siblings):
        return
    siblings[i], siblings[j] = siblings[j], siblings[i]
    for position, sibling in enumerate(siblings):
        sibling.position = position
    type(item).objects.bulk_update(siblings, ["position"])


def delete_subcategory(subcategory: Subcategory) -> None:
    """Moves its Transactions and Rules to the Category's catch-all, keeping the Transactions' source."""
    if subcategory.is_catch_all:
        raise CategoryEditRefused(_("A catch-all Subcategory can't be deleted."))
    with transaction.atomic():
        catch_all = subcategory.category.subcategories.get(is_catch_all=True)
        subcategory.transactions.update(subcategory=catch_all)
        subcategory.rules.update(subcategory=catch_all)
        # Its suggestions are cleared, so the LLM is asked again.
        Transaction.objects.filter(suggested_subcategory=subcategory).update(
            suggested_subcategory=None, confidence=None
        )
        subcategory.delete()


def delete_category(category: Category) -> None:
    if Transaction.objects.filter(subcategory__category=category).exists():
        raise CategoryEditRefused(
            _("%(category)s still has Transactions, so it can't be deleted.")
            % {"category": category.name}
        )
    if Rule.objects.filter(subcategory__category=category).exists():
        raise CategoryEditRefused(
            _("Rules still categorize into %(category)s, so it can't be deleted.")
            % {"category": category.name}
        )
    category.delete()
