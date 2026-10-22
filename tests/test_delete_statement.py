"""Deleting a Statement: only its own Transactions go, and the Coverage shrinks."""

import pytest
from django.test import Client

from ledger.models import Bank, Source, Statement, Transaction
from tests.conftest import PASSWORD, make_account, page_text
from tests.test_duplicates import (
    JUNE_1_TO_10,
    import_page,
    revolut_csv,
    transactions_page,
    upload,
)

pytestmark = pytest.mark.django_db

JUNE = revolut_csv("500", JUNE_1_TO_10)
# June 8–12, overlapping the end of JUNE.
OVERLAP = revolut_csv(
    "2444.98",
    [
        ("2026-06-08", "Bakery", "-3.20"),
        ("2026-06-10", "Mercator", "-12.34"),
        ("2026-06-12", "Petrol", "-60"),
    ],
)


@pytest.fixture
def june(logged_in_client):
    upload(logged_in_client, ("june.csv", JUNE))
    return Statement.objects.get()


@pytest.fixture
def overlap(logged_in_client, june):
    upload(logged_in_client, ("overlap.csv", OVERLAP), account=str(june.account_id))
    return Statement.objects.get(period_start="2026-06-08")


def delete_url(statement):
    return f"/statements/{statement.pk}/delete/"


@pytest.fixture
def other_client(django_user_model):
    client = Client()
    client.force_login(django_user_model.objects.create_user(username="cene", password=PASSWORD))
    return client


def test_import_page_links_to_deleting_a_statement(logged_in_client, june):
    assert delete_url(june) in import_page(logged_in_client)


def test_confirmation_names_the_statement(logged_in_client, june):
    page = logged_in_client.get(delete_url(june)).content.decode()

    assert "Delete Statement" in page
    assert "1–10 Jun 2026" in page
    assert "No manual outcomes will be lost" in page


def test_deleting_removes_the_statement_its_transactions_and_its_file(
    logged_in_client, june, statement_files, django_capture_on_commit_callbacks
):
    with django_capture_on_commit_callbacks(execute=True):
        response = logged_in_client.post(delete_url(june))

    assert response.status_code == 302
    assert response.url == "/import/"
    assert not Statement.objects.exists()
    assert "No Transactions yet" in transactions_page(logged_in_client)
    assert not list(statement_files.rglob("*.*"))
    assert "No Statements yet" in import_page(logged_in_client)


def test_transactions_also_on_another_statement_survive(logged_in_client, june, overlap):
    logged_in_client.post(delete_url(june))

    page = transactions_page(logged_in_client)
    for kept in ("Bakery", "Mercator", "Petrol"):
        assert kept in page
    assert "Hisa kave" not in page
    assert sorted(Transaction.objects.values_list("description", flat=True)) == [
        "Bakery",
        "Mercator",
        "Petrol",
    ]
    assert list(Transaction.objects.get(description="Bakery").statements.all()) == [overlap]


def test_coverage_shrinks_to_the_remaining_statements(logged_in_client, june, overlap):
    logged_in_client.post(delete_url(june))

    assert june.account.coverage() == overlap.account.coverage()
    [covered] = june.account.coverage()
    assert (str(covered.start), str(covered.end)) == ("2026-06-08", "2026-06-12")
    assert "Covered 8–12 Jun 2026" in import_page(logged_in_client)


def test_the_deleted_file_can_be_imported_again(logged_in_client, june):
    logged_in_client.post(delete_url(june))

    response = upload(logged_in_client, ("june.csv", JUNE), account=str(june.account_id))

    assert "Transactions imported from 1 file" in page_text(response.content.decode())
    assert Transaction.objects.count() == 6


def test_confirmation_counts_the_manual_outcomes_that_will_be_lost(logged_in_client, june, overlap):
    Transaction.objects.filter(description__in=["Salary", "Hisa kave"]).update(source=Source.MANUAL)
    # Also on the overlap, so it survives and its manual outcome isn't lost.
    Transaction.objects.filter(description="Bakery").update(source=Source.MANUAL)
    Transaction.objects.filter(description="Corner Shop").update(source=Source.RULE)

    page = logged_in_client.get(delete_url(june)).content.decode()

    assert "2 manual outcomes will be lost" in page


def test_a_surviving_transfer_side_loses_its_counterpart(logged_in_client, june):
    savings = make_account("Savings", Bank.OTHER)
    salary = Transaction.objects.get(description="Salary")
    deposit = Transaction.objects.create(
        account=savings, date=salary.date, amount=-salary.amount, description="From Revolut"
    )
    for side, other in ((salary, deposit), (deposit, salary)):
        side.is_transfer, side.counterpart, side.source = True, other, Source.PAIRING
        side.save()

    logged_in_client.post(delete_url(june))

    deposit.refresh_from_db()
    assert deposit.is_transfer
    assert deposit.counterpart is None


def test_an_admin_can_delete_another_members_statement(admin_client, june):
    assert admin_client.get(delete_url(june)).status_code == 200

    admin_client.post(delete_url(june))

    assert not Statement.objects.exists()


def test_any_other_member_is_refused(logged_in_client, other_client, june):
    assert other_client.get(delete_url(june)).status_code == 403
    assert other_client.post(delete_url(june)).status_code == 403

    assert Statement.objects.exists()
    assert delete_url(june) not in import_page(other_client)
