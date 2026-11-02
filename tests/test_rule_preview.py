"""What a Rule catches and does, as the Rules page and the Rule page show it (docs/design/rules.md)."""

import pytest

from ledger.models import Rule, Source, Subcategory
from ledger.rules import matched_span, preview, taken_above
from tests.test_rules import make_transaction

pytestmark = pytest.mark.django_db


def sub(category, name):
    return Subcategory.objects.get(category__name=category, name=name)


def descriptions(transactions):
    return [t.description for t in transactions]


def test_the_preview_groups_matches_by_what_saving_does():
    groceries, other = sub("Food", "Groceries"), sub("Food", "Other")
    make_transaction("HOFER waiting")
    make_transaction("HOFER by llm", subcategory=other, source=Source.LLM)
    make_transaction("HOFER by hand", subcategory=sub("Leisure", "Travel"), source=Source.MANUAL)
    make_transaction("HOFER already", subcategory=groceries, source=Source.LLM)
    make_transaction("HOFER by hand too", subcategory=groceries, source=Source.MANUAL)
    make_transaction("HOFER by parser", subcategory=other, source=Source.PARSER)
    make_transaction("Spar")

    p = preview(Rule(description_contains="hofer", subcategory=groceries))

    assert sorted(descriptions(p.change)) == ["HOFER by llm", "HOFER waiting"]
    assert descriptions(p.set_by_hand) == ["HOFER by hand"]
    assert descriptions(p.already) == ["HOFER already"]
    assert sorted(descriptions(p.keep)) == ["HOFER by hand too", "HOFER by parser"]


def test_a_transfer_rule_finds_the_transfers_already_made():
    make_transaction("Savings", is_transfer=True, source=Source.LLM)

    p = preview(Rule(description_contains="savings", subcategory=None))

    assert descriptions(p.already) == ["Savings"]
    assert p.change == []


def test_without_an_outcome_every_overwritable_match_would_change():
    make_transaction("Shop", subcategory=sub("Food", "Groceries"), source=Source.LLM)
    make_transaction("Shop by hand", subcategory=sub("Food", "Other"), source=Source.MANUAL)

    p = preview(Rule(description_contains="shop"), chosen=False)

    assert descriptions(p.change) == ["Shop"]
    assert descriptions(p.keep) == ["Shop by hand"]
    assert p.set_by_hand == p.already == []


def test_a_preview_without_a_condition_matches_nothing():
    make_transaction("Shop")

    p = preview(Rule(subcategory=sub("Food", "Groceries")))

    assert p.empty
    assert p.change == []


def test_the_preview_says_which_rules_it_takes_transactions_over_from():
    spar = Rule.objects.create(description_contains="spar", subcategory=sub("Food", "Other"))
    for name in ("SPAR 1", "SPAR 2"):
        make_transaction(name, subcategory=spar.subcategory, source=Source.RULE, rule=spar)

    p = preview(Rule(description_contains="spar", subcategory=sub("Food", "Groceries")))

    assert p.taken_over == [(spar, 2)]


def test_the_source_transaction_comes_first_in_its_group():
    make_transaction("Shop newest").save()
    source = make_transaction("Shop source")
    source.date = "2020-01-01"
    source.save()

    p = preview(Rule(description_contains="shop"), chosen=False, made_from=source)

    assert descriptions(p.change)[0] == "Shop source"


def test_matches_an_earlier_rule_takes_are_counted_by_that_rule():
    other = sub("Food", "Other")
    spar = Rule.objects.create(description_contains="spar", subcategory=other, position=0)
    fee = Rule.objects.create(description_contains="kasse", subcategory=other, position=1)
    broad = Rule.objects.create(description_contains="s", subcategory=other, position=2)
    for name in ("SPAR Bežigrad", "SPARKASSE fee", "Sparkasse fee", "Shop"):
        make_transaction(name)

    assert taken_above(broad) == [(spar, 3)]
    assert taken_above(fee) == [(spar, 2)]
    assert taken_above(spar) == []


@pytest.mark.parametrize(
    ("description", "contains", "span"),
    [
        ("SPAR Bežigrad", "spar", (0, 4)),
        ("Mercator Žalec", "zalec", (9, 14)),
        ("Hiša kave", "", None),
        ("Hiša kave", "nothing", None),
    ],
)
def test_the_matched_text_ignores_case_and_accents(description, contains, span):
    assert matched_span(description, contains) == span
