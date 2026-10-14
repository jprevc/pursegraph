"""Applying Rules to Transactions, and keeping the Rules' order.

At import, Rules categorize only unresolved Transactions. Applied to existing Transactions, a Rule
also overwrites outcomes other automatic processing set (`llm`, `rule`), never `manual`, `iban`,
`pairing` or `parser` ones."""

from django.db import transaction
from django.db.models import Min, QuerySet

from .models import Rule, Source, Transaction, TransactionQuerySet

# The automatic outcomes a Rule applied to existing Transactions may overwrite.
OVERWRITABLE = [Source.LLM, Source.RULE]


def apply_rules(transactions: TransactionQuerySet) -> int:
    """Categorizes the unresolved ones of `transactions` by the first Rule each matches. Returns how many."""
    count = 0
    for rule in Rule.objects.all():
        count += _set_outcome(transactions.unresolved().filter(rule.condition()), rule)
    return count


def overwritable_matches(rule: Rule) -> QuerySet[Transaction]:
    """The existing Transactions `rule` would categorize if applied to them."""
    matches = Transaction.objects.filter(rule.condition())
    return matches.unresolved() | matches.filter(source__in=OVERWRITABLE)


def apply_to_existing(rule: Rule) -> int:
    return _set_outcome(overwritable_matches(rule), rule)


def _set_outcome(transactions: QuerySet[Transaction], rule: Rule) -> int:
    """Transaction.set_outcome() in bulk: leaving Transfer unpairs both sides."""
    with transaction.atomic():
        if rule.subcategory_id is not None:
            Transaction.objects.filter(counterpart__in=transactions).update(counterpart=None)
        return transactions.update(
            subcategory=rule.subcategory_id,
            is_transfer=rule.subcategory_id is None,
            source=Source.RULE,
            rule=rule,
            **({"counterpart": None} if rule.subcategory_id is not None else {}),
        )


def place_at_top(rule: Rule) -> None:
    """Puts a new Rule before every other one, then saves it."""
    first = Rule.objects.aggregate(first=Min("position"))["first"]
    rule.position = 0 if first is None else first - 1
    rule.save()


def reorder(ids: list[int]) -> None:
    """Puts the Rules in the order of `ids`; Rules missing from it follow in their current order."""
    rules = list(Rule.objects.all())
    rank = {pk: i for i, pk in enumerate(ids)}
    rules.sort(key=lambda r: rank.get(r.pk, len(ids)))
    _renumber(rules)


def move(rule: Rule, direction: str) -> None:
    """Swaps `rule` with its neighbour in `direction` ("up" or "down")."""
    rules = list(Rule.objects.all())
    i = rules.index(rule)
    j = i - 1 if direction == "up" else i + 1
    if 0 <= j < len(rules):
        rules[i], rules[j] = rules[j], rules[i]
        _renumber(rules)


def _renumber(rules: list[Rule]) -> None:
    for position, rule in enumerate(rules):
        rule.position = position
    with transaction.atomic():
        Rule.objects.bulk_update(rules, ["position"])
