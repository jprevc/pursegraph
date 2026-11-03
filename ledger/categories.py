"""Editing the two-level Category list while keeping its invariants: every Category has exactly one
catch-all Subcategory, listed last; a catch-all can't be deleted; a Category is deleted only when empty."""

from django.db import transaction
from django.db.models import Count, Max, Prefetch
from django.utils.translation import gettext as _
from django.utils.translation import ngettext

from .models import Category, Rule, Subcategory, Transaction


def with_counts() -> list[Category]:
    """The Categories in order, their Subcategories prefetched, each with the `transaction_count` and `rule_count`
    that deleting it would move to the catch-all."""
    subcategories = Subcategory.objects.annotate(
        transaction_count=Count("transactions", distinct=True),
        rule_count=Count("rules", distinct=True),
    ).order_by("is_catch_all", "position", "id")  # an aggregate leaves out Meta.ordering
    return list(
        Category.objects.prefetch_related(Prefetch("subcategories", queryset=subcategories))
    )


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


def delete_subcategory(subcategory: Subcategory) -> Subcategory:
    """Moves its Transactions and Rules to the Category's catch-all, keeping the Transactions' source. Returns the
    catch-all."""
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
    return catch_all


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


def deletion_refused(category: Category) -> str:
    """Why a Category from `with_counts` can't be deleted, in the Categories page's words; "" when nothing uses it."""
    subcategories = list(category.subcategories.all())
    transactions = sum(s.transaction_count for s in subcategories)  # type: ignore[attr-defined]
    rules = sum(s.rule_count for s in subcategories)  # type: ignore[attr-defined]
    if transactions:
        catch_all = next(s for s in subcategories if s.is_catch_all)
        return ngettext(
            "%(category)s still has %(count)d Transaction. Delete its Subcategories first, then recategorize what "
            "is left in %(catch_all)s.",
            "%(category)s still has %(count)d Transactions. Delete its Subcategories first, then recategorize what "
            "is left in %(catch_all)s.",
            transactions,
        ) % {"category": category.name, "count": transactions, "catch_all": catch_all.name}
    if rules:
        return ngettext(
            "%(count)d Rule still categorizes into %(category)s.",
            "%(count)d Rules still categorize into %(category)s.",
            rules,
        ) % {"category": category.name, "count": rules}
    return ""
