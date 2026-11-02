"""Applying Rules to Transactions, and keeping the Rules' order.

At import, Rules categorize only unresolved Transactions. Applied to existing Transactions, a Rule
also overwrites outcomes other automatic processing set (`llm`, `rule`), never `manual`, `iban`,
`pairing` or `parser` ones, and pairs the Transfers it makes as import does."""

import unicodedata
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from django.db import transaction
from django.db.models import Min, QuerySet

from .models import Rule, Source, Transaction, TransactionQuerySet

if TYPE_CHECKING:
    from .transfers import Pairing

# The automatic outcomes a Rule applied to existing Transactions may overwrite.
OVERWRITABLE = [Source.LLM, Source.RULE]

# Payment processors put the merchant after "*" ("PAYPAL *STEAMGAMES").
PROCESSORS = {"PAYPAL", "SUMUP", "SQ", "ZETTLE", "IZETTLE", "GOOGLE", "APPLE"}
# Towns in descriptions make a Rule store-specific, as store numbers do.
TOWNS = {
    "LJUBLJANA", "MARIBOR", "KRANJ", "CELJE", "KOPER", "NOVO", "MESTO", "VELENJE", "PTUJ", "TRBOVLJE",
    "KAMNIK", "JESENICE", "DOMZALE", "SKOFJA", "LOKA", "IZOLA", "PIRAN", "POSTOJNA", "NOVA", "GORICA",
    "MURSKA", "SOBOTA", "SLOVENJ", "GRADEC", "ZALEC", "BLED", "BOHINJ", "VRHNIKA", "LOGATEC", "LITIJA",
    "GROSUPLJE", "KOCEVJE", "BEZIGRAD", "SISKA", "VIC", "MOSTE", "CRNUCE", "TRNOVO", "BTC",
}  # fmt: skip


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


def apply_to_existing(rule: Rule) -> tuple[int, "Pairing"]:
    """Applies `rule` to the existing Transactions it matches, then pairs the Transfers it made, as at
    import. Returns how many it set, and what pairing did."""
    from .transfers import Pairing, pair  # transfers imports OVERWRITABLE from here

    with transaction.atomic():
        matches = overwritable_matches(rule)
        pks = list(matches.values_list("pk", flat=True))
        count = _set_outcome(matches, rule)
        pairing = Pairing()
        if rule.subcategory_id is None:
            pairing = pair(Transaction.objects.filter(pk__in=pks))
    return count, pairing


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
            ambiguous_pairing=False,
            **({"counterpart": None} if rule.subcategory_id is not None else {}),
        )


@dataclass
class Preview:
    """What saving a Rule does to the existing Transactions it matches, newest first, in the Rule page's groups.
    `taken_over` names the other Rules whose Transactions it would change, and `shadowed` the earlier Rules that
    win on some of its matches at import, each with how many."""

    empty: bool = False
    change: list[Transaction] = field(default_factory=list)
    set_by_hand: list[Transaction] = field(default_factory=list)
    already: list[Transaction] = field(default_factory=list)
    keep: list[Transaction] = field(default_factory=list)
    taken_over: list[tuple[Rule, int]] = field(default_factory=list)
    shadowed: list[tuple[Rule, int]] = field(default_factory=list)


def preview(rule: Rule, *, chosen: bool = True, made_from: Transaction | None = None) -> Preview:
    """What saving `rule`, saved or not, and applying it would do: the matches that would change, those set by hand
    to another outcome, those already its outcome and those that keep theirs. Without an outcome `chosen` yet,
    every match it may overwrite would change. `made_from` (Make a Rule's Transaction) comes first in its group."""
    if not rule.condition():
        return Preview(empty=True)
    p = Preview()
    matches = (
        Transaction.objects.filter(rule.condition())
        .select_related("account", "subcategory__category", "rule")
        .order_by("-date", "-pk")
    )
    rules: dict[int, int] = {}
    for t in matches:
        same = chosen and (
            t.subcategory_id == rule.subcategory_id
            if rule.subcategory_id
            else t.is_transfer and not t.subcategory_id
        )
        if not (t.is_unresolved or t.source in OVERWRITABLE):
            (p.set_by_hand if chosen and t.source == Source.MANUAL and not same else p.keep).append(
                t
            )
        elif same:
            p.already.append(t)
        else:
            p.change.append(t)
            if t.rule_id and t.rule_id != rule.pk:
                rules[t.rule_id] = rules.get(t.rule_id, 0) + 1
    p.taken_over = [(r, rules[r.pk]) for r in Rule.objects.filter(pk__in=rules)]
    if rule.pk:
        p.shadowed = taken_above(rule)
    if made_from is not None:
        for group in (p.change, p.set_by_hand, p.already, p.keep):
            group.sort(key=lambda t: t.pk != made_from.pk)
    return p


def taken_above(rule: Rule) -> list[tuple[Rule, int]]:
    """The earlier Rules that win on some of `rule`'s matches at import, in order, each with how many."""
    taken = []
    matches = Transaction.objects.filter(rule.condition())
    for earlier in Rule.objects.all():
        if earlier.pk == rule.pk:
            break
        n = matches.filter(earlier.condition()).count()
        if n:
            taken.append((earlier, n))
        matches = matches.exclude(earlier.condition())
    return taken


def matched_span(description: str, contains: str) -> tuple[int, int] | None:
    """Where `contains` is in `description`, ignoring case and accents as a Rule does: its start and end."""
    if not contains.strip():
        return None
    folded, starts = "", []
    for i, c in enumerate(description):
        f = fold(c)
        folded += f
        starts += [i] * len(f)
    at = folded.find(fold(contains.strip()))
    if at < 0:
        return None
    end = at + len(fold(contains.strip()))
    return starts[at], starts[end - 1] + 1


def fold(text: str) -> str:
    """`text` without accents, in capitals, as a Rule's description condition compares it."""
    decomposed = unicodedata.normalize("NFKD", text)
    return "".join(c for c in decomposed if not unicodedata.combining(c)).upper()


def merchant_words(description: str) -> tuple[list[str], tuple[int, int] | None]:
    """The words of `description`, and the run of them that names its merchant, first to last: what Make a Rule
    pre-fills. Store numbers and towns are dropped, and after a payment processor the word after "*" is used."""
    words = description.split()
    if not words:
        return words, None
    head, star, tail = words[0].partition("*")
    if star and head and tail and fold(head) in PROCESSORS:
        words = [head, f"*{tail}", *words[1:]]
    bare = [fold(w).strip("*.,-") for w in words]
    first = 1 if len(words) > 1 and bare[0] in PROCESSORS else 0
    # At most two words, the second only while it is neither a number nor a town.
    second = first + 1
    named = second < len(words) and bare[second] and bare[second] not in TOWNS
    if named and not any(c.isdigit() for c in words[second]):
        return words, (first, second)
    return words, (first, first)


def words_text(words: list[str], run: tuple[int, int] | None) -> str:
    """The words of `run` as a description condition, without a processor's "*"."""
    return " ".join(words[run[0] : run[1] + 1]).lstrip("*") if run else ""


def run_of(words: list[str], text: str) -> tuple[int, int] | None:
    """The run of `words` that `text` names, as a description condition, ignoring case and accents."""
    wanted = fold(text.strip())
    for first in range(len(words)):
        for last in range(first, len(words)):
            if fold(words_text(words, (first, last))) == wanted:
                return first, last
    return None


def word_chips(description: str, contains: str) -> list[tuple[str, bool]]:
    """Make a Rule's word chips: the words of `description`, each with whether the condition `contains` uses it."""
    words, _suggested = merchant_words(description)
    run = run_of(words, contains)
    return [(w, bool(run and run[0] <= i <= run[1])) for i, w in enumerate(words)]


def places() -> dict[int, int]:
    """Each Rule's place in the order, from 1, by its id."""
    return {pk: place for place, pk in enumerate(Rule.objects.values_list("pk", flat=True), 1)}


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
