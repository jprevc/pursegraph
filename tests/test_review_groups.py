from datetime import date
from decimal import Decimal

import pytest

from ledger import review
from ledger.models import Source, Subcategory, Transaction
from tests.conftest import make_account

pytestmark = pytest.mark.django_db


@pytest.fixture
def accounts(member):
    return make_account("Ana's Revolut", "revolut", member), make_account(
        "Joint N26", "n26", member
    )


def txn(account, day, amount, description, **fields):
    return Transaction.objects.create(
        account=account, date=day, amount=amount, description=description, **fields
    )


def sub(category, name):
    return Subcategory.objects.get(category__name=category, name=name)


def described(groups):
    return [(g.description, g.size) for g in groups]


def test_waiting_transactions_with_one_description_form_a_group_newest_group_first(accounts):
    revolut, n26 = accounts
    txn(revolut, date(2026, 9, 24), "-11.02", "Bolt.eu")
    txn(n26, date(2026, 10, 2), "-14.90", "Bolt.eu")
    txn(revolut, date(2026, 9, 30), "-7.80", "Kavarna Zvezda")
    txn(revolut, date(2026, 9, 26), "-8.40", "Bolt.eu")
    txn(revolut, date(2026, 10, 1), "-5.00", "bolt.eu")  # exact description only
    txn(revolut, date(2026, 10, 3), "-9.00", "Decided", subcategory=sub("Food", "Groceries"))

    groups = review.waiting_groups()

    assert described(groups) == [("Bolt.eu", 3), ("bolt.eu", 1), ("Kavarna Zvezda", 1)]
    bolt = groups[0]
    assert [t.date for t in bolt.transactions] == [
        date(2026, 9, 24),
        date(2026, 9, 26),
        date(2026, 10, 2),
    ]
    assert bolt.total == Decimal("-34.32")


def test_an_ambiguous_transfer_side_is_a_group_of_its_own(accounts):
    revolut, _ = accounts
    txn(revolut, date(2026, 9, 1), "-50", "Savings", is_transfer=True, ambiguous_pairing=True)
    txn(revolut, date(2026, 9, 2), "-50", "Savings")

    groups = review.waiting_groups()

    assert described(groups) == [("Savings", 1), ("Savings", 1)]
    assert [g.ambiguous for g in groups] == [False, True]


def test_a_group_takes_its_newest_suggestion(accounts):
    revolut, _ = accounts
    fuel, transport = sub("Transport", "Fuel"), sub("Transport", "Public transport & car sharing")
    txn(revolut, date(2026, 9, 1), "-5", "Bolt.eu", suggested_subcategory=fuel, confidence=0.9)
    txn(
        revolut, date(2026, 9, 3), "-5", "Bolt.eu", suggested_subcategory=transport, confidence=0.78
    )
    txn(revolut, date(2026, 9, 5), "-5", "Bolt.eu")
    txn(revolut, date(2026, 9, 6), "-5", "Kavarna")

    bolt, kavarna = sorted(review.waiting_groups(), key=lambda g: g.description)

    assert (bolt.suggestion, bolt.confidence) == (transport, 0.78)
    assert kavarna.suggestion is None


def test_last_time_is_the_newest_outcome_of_the_description_outside_the_queue(accounts):
    revolut, n26 = accounts
    fuel, transport = sub("Transport", "Fuel"), sub("Transport", "Public transport & car sharing")
    txn(revolut, date(2026, 7, 1), "-5", "Bolt.eu", subcategory=transport, source=Source.MANUAL)
    txn(n26, date(2026, 8, 2), "-5", "Bolt.eu", subcategory=transport, source=Source.RULE)
    newest = txn(revolut, date(2026, 8, 12), "-5", "Bolt.eu", subcategory=fuel, source=Source.LLM)
    txn(revolut, date(2026, 6, 1), "-5", "Bolt.eu", subcategory=fuel, source=Source.MANUAL)
    txn(revolut, date(2026, 9, 1), "-5", "Bolt.eu")  # in the queue
    txn(revolut, date(2026, 9, 2), "-5", "Bolt.eu x", subcategory=transport, source=Source.MANUAL)

    last = review.last_time("Bolt.eu")

    assert last is not None
    assert (last.subcategory, last.is_transfer, last.date) == (fuel, False, date(2026, 8, 12))
    assert last.source_caption == "by LLM"
    assert last.count == 2
    assert last.outcome == str(fuel.pk)

    earlier = review.last_time("Bolt.eu", exclude=[newest.pk])
    assert earlier is not None
    assert (earlier.subcategory, earlier.count) == (transport, 2)


def test_last_time_of_a_transfer_and_of_a_new_description(accounts):
    revolut, _ = accounts
    txn(revolut, date(2026, 8, 1), "-50", "To savings", is_transfer=True, source=Source.MANUAL)
    txn(revolut, date(2026, 8, 2), "-50", "Ambiguous", is_transfer=True, ambiguous_pairing=True)

    last = review.last_time("To savings")
    assert last is not None
    assert (last.is_transfer, last.outcome, last.count) == (True, "transfer", 1)
    assert review.last_time("Ambiguous") is None
    assert review.last_time("Never seen") is None


@pytest.fixture
def covered(accounts, member):
    """Statements of both Accounts covering August and September 2026, so both months are Complete."""
    from ledger.models import Statement

    for i, account in enumerate(accounts):
        Statement.objects.create(
            account=account,
            format="csv",
            period_start=date(2026, 8, 1),
            period_end=date(2026, 9, 30),
            opening_balance=0,
            closing_balance=0,
            imported_by=member,
            sha256=str(i) * 64,
        )
    return accounts


@pytest.fixture
def today(monkeypatch):
    monkeypatch.setattr("dashboard.periods.today", lambda: date(2026, 10, 17))


def test_the_month_completed_is_the_newest_month_decided_into_that_is_complete(covered, today):
    revolut, _ = covered
    groceries = sub("Food", "Groceries")
    august = txn(revolut, date(2026, 8, 5), "-5", "A", subcategory=groceries)
    september = txn(revolut, date(2026, 9, 5), "-5", "S", subcategory=groceries)
    october = txn(revolut, date(2026, 10, 5), "-5", "O", subcategory=groceries)

    assert review.completed_month([august.pk, september.pk, october.pk]) == date(2026, 9, 1)
    assert review.completed_month([august.pk]) == date(2026, 8, 1)
    # October is in progress.
    assert review.completed_month([october.pk]) is None


def test_a_month_with_something_still_waiting_is_not_completed(covered, today):
    revolut, _ = covered
    groceries = sub("Food", "Groceries")
    august = txn(revolut, date(2026, 8, 5), "-5", "A", subcategory=groceries)
    september = txn(revolut, date(2026, 9, 5), "-5", "S", subcategory=groceries)
    txn(revolut, date(2026, 9, 9), "-5", "Still waiting")

    assert review.completed_month([august.pk, september.pk]) == date(2026, 8, 1)


def test_a_month_with_a_gap_is_not_completed(covered, today):
    revolut, _ = covered
    revolut.statements.update(period_end=date(2026, 9, 20))
    september = txn(revolut, date(2026, 9, 5), "-5", "S", subcategory=sub("Food", "Groceries"))

    assert review.completed_month([september.pk]) is None
