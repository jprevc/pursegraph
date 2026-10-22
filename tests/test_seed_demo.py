"""The demo Household that screenshots and manual checks run against."""

import pytest
from django.core.management import CommandError, call_command

from ledger.management.commands.seed_demo import PASSWORD
from ledger.models import Account, Transaction
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
