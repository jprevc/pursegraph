"""The `reparse` command: stored Statement files re-parsed and diffed against the stored Transactions."""

from decimal import Decimal
from io import StringIO

import pytest
from django.core.management import CommandError, call_command

from ledger.models import Statement, Transaction
from tests.test_import import upload

pytestmark = pytest.mark.django_db


def reparse(*args):
    out = StringIO()
    call_command("reparse", *args, stdout=out)
    return out.getvalue()


@pytest.fixture
def statement(logged_in_client):
    upload(logged_in_client)
    return Statement.objects.get()


def test_an_unchanged_statement_reports_no_differences(statement):
    output = reparse()

    assert "Ana's Revolut 2026-06-01–2026-06-11" in output
    assert "no differences" in output
    assert "1 Statement re-parsed: 1 unchanged, 0 with differences, 0 failed." in output


def test_a_changed_field_is_shown_with_its_stored_and_parsed_value(statement):
    Transaction.objects.filter(description="Mercator Žalec").update(
        description="Mercator Zalec", reference="old"
    )

    output = reparse()

    assert "~ 2026-06-11 -12.34 Mercator Zalec" in output
    assert "description: 'Mercator Zalec' → 'Mercator Žalec'" in output
    assert "reference: 'old' → ''" in output
    assert "0 unchanged, 1 with differences, 0 failed." in output


def test_a_row_the_parser_now_finds_is_added_and_one_it_no_longer_finds_is_removed(statement):
    Transaction.objects.filter(description="Fee: Corner Shop").delete()
    statement.transactions.create(
        account=statement.account, date="2026-06-07", amount=Decimal("-1.00"), description="Ghost"
    )

    output = reparse()

    assert "+ 2026-06-06 -0.50 Fee: Corner Shop" in output
    assert "- 2026-06-07 -1.00 Ghost" in output


def test_changed_statement_fields_are_shown(statement):
    Statement.objects.update(closing_balance=Decimal("1.00"))

    output = reparse()

    assert "closing_balance: 1.00 → " in output


def test_reparsing_changes_nothing(statement):
    Transaction.objects.filter(description="Mercator Žalec").update(description="Mercator Zalec")
    before = list(Transaction.objects.values())

    reparse()

    assert list(Transaction.objects.values()) == before


def test_a_file_that_no_longer_parses_is_reported_as_failed(statement):
    statement.file.open("wb")
    statement.file.write(b"Type,Product\nsomething,else\n")
    statement.file.close()

    output = reparse()

    assert "failed:" in output
    assert "0 unchanged, 0 with differences, 1 failed." in output


def test_a_missing_file_is_reported_as_failed(statement):
    statement.file.delete(save=False)

    output = reparse()

    assert "failed: the stored file is missing" in output


def test_a_file_whose_balances_no_longer_add_up_is_reported_as_failed_with_its_differences(
    statement,
):
    content = statement.file.read()
    statement.file.close()
    with statement.file.open("wb") as file:
        file.write(content.replace(b"COMPLETED,2152.64", b"COMPLETED,2000.00"))

    output = reparse()

    assert "failed: the balances don't add up" in output
    assert "closing_balance: 2152.64 → 2000.00" in output
    assert "0 unchanged, 0 with differences, 1 failed." in output


def test_only_the_named_statements_are_reparsed(logged_in_client, statement):
    upload_second = upload(
        logged_in_client,
        content=b"Type,Product,Started Date,Completed Date,Description,Amount,Fee,Currency,State,Balance\n"
        b"Card Payment,Current,2026-07-01 9:00:00,2026-07-01 9:00:00,Kiosk,-1,0,EUR,COMPLETED,99\n",
        filename="second.csv",
        new_account_name="Second",
    )
    assert upload_second.status_code == 200
    second = Statement.objects.exclude(pk=statement.pk).get()

    output = reparse(str(second.pk))

    assert "Second 2026-07-01–2026-07-01" in output
    assert "Ana's Revolut" not in output


def test_an_unknown_statement_id_is_an_error(statement):
    with pytest.raises(CommandError):
        reparse("999999")
