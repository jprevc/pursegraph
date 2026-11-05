"""A Split: a Transaction's outcome as several Parts, each an exact amount in its own Subcategory (ADR 0003), and how
every rule about outcomes treats one."""

import json
from datetime import date
from decimal import Decimal

import pytest
from django.db import connection
from django.db.migrations.executor import MigrationExecutor

from ledger import categories, outcomes, suggestions
from ledger.forms import RuleForm
from ledger.models import Part, Rule, Source, Statement, Subcategory, Transaction
from ledger.reparse import apply_changes, reparse
from ledger.rules import apply_rules, apply_to_existing, preview
from ledger.transfers import pair
from tests.conftest import make_account
from tests.test_import import upload
from tests.test_rules import make_transaction

pytestmark = pytest.mark.django_db


def sub(category, name):
    return Subcategory.objects.get(category__name=category, name=name)


def groceries():
    return sub("Food", "Groceries")


def household():
    return sub("Home", "Furniture & household")


def parts_of(t):
    return [(p.subcategory, p.amount) for p in Part.objects.filter(transaction=t)]


def hypermarket(**outcome):
    """A €-80.00 payment, split into Groceries -50.00 and Household goods -30.00 unless `outcome` says otherwise."""
    t = make_transaction("INTERSPAR", "-80.00", **outcome)
    if not outcome:
        outcomes.split(t, [(groceries(), Decimal("-50.00")), (household(), Decimal("-30.00"))])
        t.refresh_from_db()
    return t


def outcome_of(t):
    t.refresh_from_db()
    return (t.subcategory, t.is_transfer, t.is_split, t.source, parts_of(t))


# Splitting


def test_a_split_saves_its_parts_by_hand_and_leaves_the_review_queue():
    t = make_transaction("INTERSPAR", "-80.00")
    assert Transaction.objects.in_review_queue().filter(pk=t.pk).exists()

    outcomes.split(t, [(groceries(), Decimal("-50.00")), (household(), Decimal("-30.00"))])

    t.refresh_from_db()
    assert parts_of(t) == [(groceries(), Decimal("-50.00")), (household(), Decimal("-30.00"))]
    assert (t.is_split, t.subcategory, t.is_transfer, t.source) == (True, None, False, "manual")
    assert not t.is_unresolved
    assert not Transaction.objects.in_review_queue().filter(pk=t.pk).exists()


def test_a_split_reads_as_split_and_its_parts():
    assert hypermarket().outcome_label == (
        "Split: Food › Groceries 50,00 €, Home › Furniture & household 30,00 €"
    )


@pytest.mark.parametrize(
    ("parts", "message"),
    [
        ([("groceries", "-80.00")], "A Split needs at least two Parts."),
        ([("groceries", "-50.00"), ("household", "-20.00")], "The Parts add up to 70,00"),
        ([("groceries", "-50.00"), ("groceries", "-30.00")], "Each Part needs a Subcategory"),
        ([("groceries", "-90.00"), ("household", "10.00")], "Every Part is money out"),
        ([("groceries", "-80.00"), ("household", "0")], "A Part can't be zero."),
        ([("groceries", "-50.00"), ("salary", "-30.00")], "all spending or all income"),
        ([("groceries", "-50.005"), ("household", "-29.995")], "to the cent"),
    ],
)
def test_an_invalid_split_is_refused_with_a_reason_and_changes_nothing(parts, message):
    named = {"groceries": groceries(), "household": household(), "salary": sub("Income", "Salary")}
    t = make_transaction("INTERSPAR", "-80.00", subcategory=groceries(), source=Source.RULE)

    with pytest.raises(outcomes.SplitRefused, match=message):
        outcomes.split(t, [(named[name], Decimal(amount)) for name, amount in parts])

    assert outcome_of(t) == (groceries(), False, False, "rule", [])


def test_money_in_splits_into_parts_of_money_in():
    t = make_transaction("Payroll", "100.00")
    salary, gifts = sub("Income", "Salary"), sub("Income", "Gifts received")

    with pytest.raises(outcomes.SplitRefused, match="Every Part is money in"):
        outcomes.split(t, [(salary, Decimal("110.00")), (gifts, Decimal("-10.00"))])
    outcomes.split(t, [(salary, Decimal("90.00")), (gifts, Decimal("10.00"))])

    assert outcome_of(t)[2:] == (True, "manual", [(salary, Decimal(90)), (gifts, Decimal(10))])


def test_splitting_a_transfer_side_unpairs_both_sides():
    side = make_transaction("To savings", "-80.00", is_transfer=True, source=Source.PAIRING)
    other = Transaction.objects.create(
        account=make_account("Savings", "n26"),
        date=side.date,
        amount=Decimal("80.00"),
        description="From checking",
        is_transfer=True,
        source=Source.PAIRING,
        counterpart=side,
    )
    Transaction.objects.filter(pk=side.pk).update(counterpart=other)
    side.refresh_from_db()

    outcomes.split(side, [(groceries(), Decimal("-50.00")), (household(), Decimal("-30.00"))])

    side.refresh_from_db()
    other.refresh_from_db()
    assert (side.is_transfer, side.is_split, side.counterpart) == (False, True, None)
    assert (other.is_transfer, other.counterpart) == (True, None)


def test_a_split_transaction_is_no_counterpart_for_a_transfer():
    split = hypermarket()
    Transaction.objects.create(
        account=make_account("Savings", "n26"),
        date=split.date,
        amount=Decimal("80.00"),
        description="From checking",
        is_transfer=True,
        source=Source.IBAN,
    )

    pair(Transaction.objects.all())

    assert outcome_of(split)[2] is True
    assert split.counterpart is None


# Changing it, and Undo


def test_picking_one_outcome_replaces_the_split_and_undo_brings_it_back(logged_in_client):
    t = hypermarket()
    split = outcome_of(t)

    logged_in_client.post(f"/transactions/{t.pk}/outcome/", {"outcome": groceries().pk})
    assert outcome_of(t) == (groceries(), False, False, "manual", [])
    assert not Part.objects.exists()

    response = logged_in_client.post(f"/transactions/{t.pk}/undo/", HTTP_HX_REQUEST="true")
    assert response.status_code == 200
    assert outcome_of(t) == split
    said = json.loads(response["HX-Trigger"])["announce"]
    assert said == (
        "Undone. INTERSPAR is back to Split: Food › Groceries 50,00\u00a0€, Home › Furniture & household "
        "30,00\u00a0€."
    )


def test_picking_transfer_replaces_the_split():
    t = hypermarket()

    t.set_outcome(None, source=Source.MANUAL)

    assert outcome_of(t) == (None, True, False, "manual", [])


def test_undo_of_a_split_puts_back_the_outcome_it_replaced():
    t = make_transaction("INTERSPAR", "-80.00", subcategory=groceries(), source=Source.RULE)
    t.rule = Rule.objects.create(description_contains="INTERSPAR", subcategory=groceries())
    t.save()

    before = outcomes.split(t, [(groceries(), Decimal("-50.00")), (household(), Decimal("-30.00"))])
    outcomes.restore(before)

    t.refresh_from_db()
    assert outcome_of(t) == (groceries(), False, False, "rule", [])
    assert t.rule is not None


def test_undo_is_refused_once_a_parts_subcategory_is_gone():
    t = hypermarket()
    before = outcomes.snapshot(t)
    t.set_outcome(groceries(), source=Source.MANUAL)
    categories.delete_subcategory(household())

    with pytest.raises(outcomes.UndoRefused):
        outcomes.restore(before)

    assert outcome_of(t) == (groceries(), False, False, "manual", [])


# Rules


def test_applying_a_rule_lists_a_split_as_set_by_hand_and_leaves_it():
    t = hypermarket()
    rule = Rule.objects.create(description_contains="interspar", subcategory=groceries())

    assert [m.pk for m in preview(rule).set_by_hand] == [t.pk]
    apply_to_existing(rule)
    apply_rules(Transaction.objects.all())

    assert outcome_of(t)[2:4] == (True, "manual")


def test_make_a_rule_from_a_split_names_no_outcome():
    form = RuleForm.from_transaction(hypermarket())

    assert form.initial == {"description_contains": "INTERSPAR"}


# Categorizers


def test_a_split_is_never_a_categorizer_example_nor_waits_for_a_suggestion():
    hypermarket()
    make_transaction("HOFER", subcategory=groceries(), source=Source.MANUAL)
    make_transaction("Unknown shop")

    _subcategories, waiting = suggestions.waiting(10)

    assert [q.description for _pk, q in waiting] == ["Unknown shop"]
    assert [e.description for e in waiting[0][1].examples] == ["HOFER"]


# Deleting Subcategories and Categories


def test_deleting_a_subcategory_merges_the_parts_that_meet_in_the_catch_all():
    food_other = sub("Food", "Other")
    takeaway = sub("Food", "Fast food & takeaway")
    t = make_transaction("INTERSPAR", "-80.00")
    outcomes.split(
        t,
        [
            (groceries(), Decimal("-40.00")),
            (takeaway, Decimal("-10.00")),
            (household(), Decimal("-30.00")),
        ],
    )

    categories.delete_subcategory(groceries())

    assert outcome_of(t)[2:] == (
        True,
        "manual",
        [
            (takeaway, Decimal("-10.00")),
            (household(), Decimal("-30.00")),
            (food_other, Decimal("-40.00")),
        ],
    )

    categories.delete_subcategory(takeaway)

    assert outcome_of(t)[2:] == (
        True,
        "manual",
        [(household(), Decimal("-30.00")), (food_other, Decimal("-50.00"))],
    )


def test_a_split_left_with_one_part_becomes_a_plain_outcome_by_hand():
    food_other = sub("Food", "Other")
    t = make_transaction("INTERSPAR", "-80.00")
    outcomes.split(t, [(groceries(), Decimal("-50.00")), (food_other, Decimal("-30.00"))])

    categories.delete_subcategory(groceries())

    assert outcome_of(t) == (food_other, False, False, "manual", [])


def test_a_category_holding_parts_counts_them_and_cant_be_deleted():
    hypermarket()
    home = household().category
    categories.delete_subcategory(household())

    with pytest.raises(categories.CategoryEditRefused, match="Home still has Transactions"):
        categories.delete_category(home)
    counted = next(c for c in categories.with_counts() if c.pk == home.pk)
    assert categories.deletion_refused(counted).startswith("Home still has 1 Transaction.")


# Re-parse and Statement deletion


@pytest.fixture
def statement(logged_in_client):
    upload(logged_in_client)
    return Statement.objects.get()


def split_mercator(stored_amount, **stored):
    """Mercator Žalec (-12.34 on its Statement), stored as `stored_amount` and split in two halves."""
    t = Transaction.objects.get(description="Mercator Žalec")
    Transaction.objects.filter(pk=t.pk).update(amount=Decimal(stored_amount), **stored)
    t.refresh_from_db()
    half = Decimal(stored_amount) / 2
    outcomes.split(t, [(groceries(), half), (household(), half)])
    return t


def test_a_reparse_that_changes_a_splits_amount_drops_it_into_the_review_queue(statement):
    t = split_mercator("-20.00")

    changes = apply_changes(reparse(statement))

    assert outcome_of(t) == (None, False, False, "", [])
    assert t.amount == Decimal("-12.34")
    assert Transaction.objects.in_review_queue().filter(pk=t.pk).exists()
    assert [(c.transaction.pk, c.before, c.after) for c in changes] == [
        (
            t.pk,
            "Split: Food / Groceries 10.00, Home / Furniture & household 10.00 (Manual)",
            "awaiting review (Split removed: the amount changed)",
        )
    ]


def test_a_reparse_that_keeps_a_splits_amount_keeps_it(statement):
    t = split_mercator("-12.34", description="Mercator Zalec")

    assert apply_changes(reparse(statement)) == []

    assert outcome_of(t)[2:4] == (True, "manual")
    assert t.description == "Mercator Žalec"


def test_deleting_a_statement_removes_its_transactions_parts(statement):
    split_mercator("-12.34")
    assert statement.lost_manual_outcome_count() == 1

    statement.delete_with_transactions()

    assert not Part.objects.exists()


# The migration


@pytest.mark.django_db(transaction=True, serialized_rollback=True)
def test_the_migration_leaves_existing_outcomes_as_they_were():
    executor = MigrationExecutor(connection)
    before = [("ledger", "0013_drop_suggestions_unavailable")]
    executor.migrate(before)
    executor.loader.build_graph()
    apps = executor.loader.project_state(before).apps
    account = apps.get_model("ledger", "Account").objects.create(name="Checking", bank="n26")
    old_sub = apps.get_model("ledger", "Subcategory").objects.get(
        category__name="Food", name="Groceries"
    )
    for description, outcome in [
        ("Shop", {"subcategory": old_sub, "source": "manual"}),
        ("Savings", {"is_transfer": True, "source": "iban"}),
        ("Waiting", {}),
    ]:
        apps.get_model("ledger", "Transaction").objects.create(
            account=account,
            date=date(2026, 9, 1),
            amount=Decimal("-5"),
            description=description,
            **outcome,
        )

    try:
        executor = MigrationExecutor(connection)
        executor.migrate(executor.loader.graph.leaf_nodes())
        rows = Transaction.objects.order_by("description").values_list(
            "description", "subcategory__name", "is_transfer", "is_split", "source"
        )
        assert list(rows) == [
            ("Savings", None, True, False, "iban"),
            ("Shop", "Groceries", False, False, "manual"),
            ("Waiting", None, False, False, ""),
        ]
        assert [t.description for t in Transaction.objects.unresolved()] == ["Waiting"]
    finally:
        MigrationExecutor(connection).migrate(
            MigrationExecutor(connection).loader.graph.leaf_nodes()
        )
