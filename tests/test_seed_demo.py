"""The demo Household that screenshots and manual checks run against."""

import pytest
from django.core.management import CommandError, call_command
from django.db.models import F
from django.utils import timezone

from dashboard.periods import Period
from ledger.management.commands.seed_demo import PASSWORD
from ledger.models import Account, Category, Rule, Source, Subcategory, Transaction
from tests.conftest import log_in

pytestmark = pytest.mark.django_db


def test_seed_demo_gives_an_admin_who_sees_last_months_transactions(client):
    call_command("seed_demo")

    log_in(client, "ana", PASSWORD)

    assert client.get("/accounts/").status_code == 200
    page = client.get("/transactions/").content.decode()
    assert "Salary" in page


def test_seed_demo_leaves_some_transactions_awaiting_review():
    call_command("seed_demo")

    assert Transaction.objects.unresolved().exists()


def test_seed_demo_refuses_a_database_that_already_has_members(member):
    with pytest.raises(CommandError):
        call_command("seed_demo")

    assert not Transaction.objects.exists()


def test_seed_demo_has_coverage_with_a_gap_and_an_account_tracked_later():
    call_command("seed_demo")

    accounts = {a.name: a.coverage() for a in Account.objects.all()}
    [sparkasse] = accounts["Ana's Sparkasse"]
    [joint] = accounts["Joint Revolut"]
    assert joint.start > sparkasse.start
    assert len(accounts["Luka's N26"]) == 2


def test_seed_demo_has_a_savings_account_without_statements_that_ana_saves_into_monthly():
    call_command("seed_demo")

    savings = Account.objects.get(name="Ana's savings")
    assert not savings.receives_statements
    assert [o.username for o in savings.owners.all()] == ["ana"]
    [iban] = savings.ibans.all()
    deposits = Transaction.objects.filter(
        account__name="Ana's Sparkasse", counterparty_iban=iban.iban
    )
    assert deposits.count() >= 9
    assert all(d.is_transfer and d.counterpart is None and d.amount < 0 for d in deposits)


def test_seed_demo_pairs_each_salary_accounts_monthly_transfer_into_the_joint_account():
    call_command("seed_demo")

    joint = Account.objects.get(name="Joint Revolut")
    for name in ("Ana's Sparkasse", "Luka's N26"):
        paid_in = Transaction.objects.filter(account__name=name, counterpart__account=joint)
        assert paid_in.count() >= 6  # the months both Accounts have Statements for
        for side in paid_in:
            other = side.counterpart
            assert other is not None
            assert side.is_transfer and other.is_transfer
            assert other.amount == -side.amount
            assert side.counterparty_iban == joint.ibans.get().iban
            assert other.counterparty_iban == side.account.ibans.get().iban


def test_seed_demo_leaves_one_recent_transfer_with_two_equally_close_sides_in_the_review_queue():
    call_command("seed_demo")

    [side] = Transaction.objects.filter(ambiguous_pairing=True, account__name="Joint Revolut")
    assert side in Transaction.objects.in_review_queue()
    assert len(side.pairing_candidates()) == 2
    assert (timezone.localdate() - side.date).days < 31


def test_seed_demo_has_three_refunds_in_different_months():
    call_command("seed_demo")

    refunds = Transaction.objects.filter(
        amount__gt=0, subcategory__category__kind=Category.Kind.SPENDING
    )
    assert refunds.count() == 3
    assert len({(r.date.year, r.date.month) for r in refunds}) == 3


def test_seed_demo_names_merchants_and_its_rules_match_them():
    call_command("seed_demo")

    spending = Transaction.objects.filter(subcategory__category__kind=Category.Kind.SPENDING)
    named_after_subcategory = spending.filter(description__startswith=F("subcategory__name"))
    assert not named_after_subcategory.exists()
    assert all(t.counterparty_name for t in spending)
    subcategory_names = set(Subcategory.objects.values_list("name", flat=True))
    for rule in Rule.objects.exclude(description_contains=""):
        assert rule.description_contains not in subcategory_names
        categorized = rule.transactions.all()
        assert categorized.exists()
        assert all(
            rule.description_contains.lower() in t.description.lower()
            and t.subcategory == rule.subcategory
            for t in categorized
        )


def test_seed_demo_pays_the_rent_from_the_joint_account_on_the_first_of_each_month_it_tracks():
    call_command("seed_demo")

    rent = Transaction.objects.filter(subcategory__name="Rent / mortgage")
    assert {t.account.name for t in rent} == {"Joint Revolut"}
    assert {t.date.day for t in rent} == {1}
    # The Joint Revolut is tracked from ten months back, the running month included.
    assert rent.count() == 11


def test_seed_demo_has_two_manual_splits_in_the_dashboards_default_period_one_of_groceries():
    call_command("seed_demo")

    splits = Transaction.objects.filter(is_split=True)
    assert splits.count() == 2
    last_month = Period.default()
    part_subcategories = []
    for split in splits:
        assert split.source == Source.MANUAL
        assert split.subcategory is None and split.rule is None
        assert last_month.start <= split.date <= last_month.end
        parts = list(split.parts.select_related("subcategory__category"))
        assert len(parts) >= 2
        assert len({p.subcategory for p in parts}) == len(parts)
        assert all(p.amount < 0 for p in parts)
        assert sum(p.amount for p in parts) == split.amount
        part_subcategories.append(
            {(p.subcategory.category.name, p.subcategory.name) for p in parts}
        )
    assert {("Food", "Groceries"), ("Home", "Furniture & household")} in part_subcategories
    # The other one counts in two Categories, neither Food nor Home.
    [other] = [o for o in part_subcategories if ("Food", "Groceries") not in o]
    categories = {category for category, _name in other}
    assert len(categories) == 2
    assert not categories & {"Food", "Home"}
