"""The `reparse` command: stored Statement files re-parsed and diffed against the stored Transactions."""

from decimal import Decimal
from io import StringIO

import pytest
from django.core.management import CommandError, call_command

from ledger.models import Rule, Source, Statement, Subcategory, Transaction
from tests.conftest import make_account, transaction_id
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


def test_a_duplicate_is_compared_only_by_what_the_duplicate_check_matched(
    logged_in_client, statement
):
    # Overlaps the first Statement on 11 Jun, where it lists the same row under another description.
    response = upload(
        logged_in_client,
        content=b"Type,Product,Started Date,Completed Date,Description,Amount,Fee,Currency,State,Balance\n"
        b"Card Payment,Current,2026-06-10 21:15:00,2026-06-11 6:30:12,MERCATOR ZALEC,-12.34,0,EUR,COMPLETED,2152.64\n"
        b"Card Payment,Current,2026-06-12 9:00:00,2026-06-12 9:00:00,Kiosk,-1,0,EUR,COMPLETED,2151.64\n",
        filename="overlap.csv",
        account=statement.account.pk,
    )
    assert "1 Duplicate" in response.content.decode()
    second = Statement.objects.exclude(pk=statement.pk).get()

    output = reparse(str(second.pk))

    assert "no differences" in output


def test_a_parser_crash_fails_only_that_statement(statement, monkeypatch):
    def crash(content, format):
        raise ValueError("boom")

    monkeypatch.setattr("ledger.reparse.parse", crash)

    output = reparse()

    assert "failed: ValueError: boom" in output
    assert "0 unchanged, 0 with differences, 1 failed." in output


def test_a_changed_fee_flag_is_shown(statement):
    Transaction.objects.filter(description="Fee: Corner Shop").update(is_fee=False)

    output = reparse()

    assert "~ 2026-06-06 -0.50 Fee: Corner Shop" in output
    assert "is_fee: False → True" in output


def groceries():
    return Subcategory.objects.get(category__name="Food", name="Groceries")


def test_apply_takes_a_description_fix_on_and_keeps_the_manual_outcome(statement):
    Transaction.objects.filter(description="Mercator Žalec").update(
        description="Mercator Zalec", raw={}, subcategory=groceries(), source=Source.MANUAL
    )

    output = reparse("--apply", str(statement.pk))

    fixed = Transaction.objects.get(pk=transaction_id("Mercator Žalec"))
    assert fixed.raw["Description"] == "Mercator Žalec"
    assert (fixed.subcategory, fixed.source) == (groceries(), Source.MANUAL)
    assert "applied" in output
    assert "1 Statement re-parsed: 1 applied, 0 refused, 0 unchanged, 0 failed." in output


def shopping():
    return Subcategory.objects.get(category__name="Shopping", name="Other")


def test_apply_reruns_an_automatic_outcome_and_clears_the_llm_suggestion(statement):
    Rule.objects.create(description_contains="Mercator", subcategory=groceries())
    Transaction.objects.filter(description="Mercator Žalec").update(
        description="Shop 123",
        subcategory=shopping(),
        source=Source.LLM,
        suggested_subcategory=shopping(),
        confidence=0.95,
    )

    output = reparse("--apply")

    fixed = Transaction.objects.get(pk=transaction_id("Mercator Žalec"))
    assert (fixed.subcategory, fixed.source) == (groceries(), Source.RULE)
    assert (fixed.suggested_subcategory, fixed.confidence) == (None, None)
    assert (
        "2026-06-11 -12.34 Mercator Žalec: Shopping / Other (LLM) → Food / Groceries (Rule)"
        in output
    )


def test_apply_leaves_an_outcome_alone_when_only_the_running_balance_changed(statement):
    Transaction.objects.filter(description="Mercator Žalec").update(
        running_balance=Decimal("1.00"),
        subcategory=shopping(),
        source=Source.LLM,
        suggested_subcategory=shopping(),
        confidence=0.95,
    )

    output = reparse("--apply")

    fixed = Transaction.objects.get(pk=transaction_id("Mercator Žalec"))
    assert fixed.running_balance == Decimal("2152.64")
    assert (fixed.subcategory, fixed.source, fixed.confidence) == (shopping(), Source.LLM, 0.95)
    assert "1 applied" in output


def pair_mercator_with_savings(amount, description):
    """Mercator Žalec, stored at `amount` and `description`, as a paired Transfer side to a Savings Account."""
    savings = make_account("Savings", "n26")
    other_side = savings.transactions.create(
        date="2026-06-11", amount=-amount, description="From Revolut"
    )
    mercator = Transaction.objects.get(description="Mercator Žalec")
    Transaction.objects.filter(pk=mercator.pk).update(
        amount=amount, description=description, is_transfer=True, source=Source.PAIRING
    )
    Transaction.objects.filter(pk=mercator.pk).update(counterpart=other_side)
    Transaction.objects.filter(pk=other_side.pk).update(
        counterpart=mercator, is_transfer=True, source=Source.PAIRING
    )
    return mercator, other_side


def test_apply_repairs_a_rerun_transfer_side_with_its_counterpart(statement):
    mercator, other_side = pair_mercator_with_savings(Decimal("-12.34"), "Shop 123")

    output = reparse("--apply")

    mercator.refresh_from_db()
    other_side.refresh_from_db()
    assert (mercator.is_transfer, mercator.counterpart) == (True, other_side)
    assert other_side.counterpart == mercator
    assert "Transfer" not in output  # no outcome changed


def test_apply_leaves_the_counterpart_of_a_side_that_no_longer_pairs_a_one_sided_transfer(
    statement,
):
    mercator, other_side = pair_mercator_with_savings(Decimal("-12.00"), "Mercator Žalec")

    output = reparse("--apply")

    mercator.refresh_from_db()
    other_side.refresh_from_db()
    assert (mercator.amount, mercator.is_unresolved) == (Decimal("-12.34"), True)
    assert (other_side.is_transfer, other_side.counterpart) == (True, None)
    assert (
        "2026-06-11 12.00 From Revolut: Transfer, paired with 2026-06-11 -12.00 Mercator Žalec (Pairing)"
        " → Transfer, one-sided (Pairing)" in output
    )
    assert "Mercator Žalec: Transfer, paired with" in output
    assert "→ awaiting review" in output


def misspell_mercator():
    Transaction.objects.filter(description="Mercator Žalec").update(description="Mercator Zalec")


def assert_mercator_still_misspelt():
    assert Transaction.objects.filter(description="Mercator Zalec").exists()


def test_apply_skips_a_statement_whose_reparse_failed(statement):
    misspell_mercator()
    statement.file.delete(save=False)

    output = reparse("--apply")

    assert_mercator_still_misspelt()
    assert "failed: the stored file is missing" in output
    assert "0 applied, 0 refused, 0 unchanged, 1 failed." in output


def test_apply_refuses_a_statement_with_statement_level_changes(statement):
    misspell_mercator()
    Statement.objects.update(closing_balance=Decimal("1.00"))

    output = reparse("--apply")

    assert_mercator_still_misspelt()
    assert "refused: the Statement's own fields changed" in output
    assert "0 applied, 1 refused, 0 unchanged, 0 failed." in output


def test_apply_refuses_a_statement_with_added_or_removed_rows(statement):
    misspell_mercator()
    Transaction.objects.filter(description="Fee: Corner Shop").delete()

    output = reparse("--apply")

    assert_mercator_still_misspelt()
    assert "refused: rows were added or removed" in output


def test_apply_leaves_a_statement_with_no_differences_alone(statement):
    output = reparse("--apply")

    assert "no differences" in output
    assert "0 applied, 0 refused, 1 unchanged, 0 failed." in output


@pytest.fixture
def overlapping(logged_in_client, statement):
    """A second Statement of the Account that has Mercator Žalec as a Duplicate."""
    upload(
        logged_in_client,
        content=b"Type,Product,Started Date,Completed Date,Description,Amount,Fee,Currency,State,Balance\n"
        b"Card Payment,Current,2026-06-10 21:15:00,2026-06-11 6:30:12,Mercator \xc5\xbdalec,-12.34,0,EUR,COMPLETED,2152.64\n"
        b"Card Payment,Current,2026-06-12 9:00:00,2026-06-12 9:00:00,Kiosk,-1,0,EUR,COMPLETED,2151.64\n",
        filename="overlap.csv",
        account=statement.account.pk,
    )
    return Statement.objects.exclude(pk=statement.pk).get()


def test_apply_refuses_a_changed_duplicate(statement, overlapping):
    Transaction.objects.filter(description="Mercator Žalec").update(running_balance=Decimal("1.00"))

    output = reparse("--apply", str(overlapping.pk))

    assert Transaction.objects.get(description="Mercator Žalec").running_balance == Decimal("1.00")
    assert (
        f"refused: 2026-06-11 -12.34 Mercator Žalec is a Duplicate here; "
        f"re-parse Statement {statement.pk}, which first had it, instead" in output
    )


def test_apply_refuses_an_amount_or_balance_change_of_a_transaction_another_statement_has(
    statement, overlapping
):
    Transaction.objects.filter(description="Mercator Žalec").update(running_balance=Decimal("1.00"))

    output = reparse("--apply", str(statement.pk))

    assert Transaction.objects.get(description="Mercator Žalec").running_balance == Decimal("1.00")
    assert (
        f"refused: the amount or running balance of 2026-06-11 -12.34 Mercator Žalec changed, "
        f"but Statement {overlapping.pk} has it too" in output
    )


def test_apply_takes_a_description_fix_of_a_shared_transaction_on_the_statement_that_first_had_it(
    statement, overlapping
):
    misspell_mercator()

    output = reparse("--apply", str(statement.pk))

    assert Transaction.objects.filter(description="Mercator Žalec").exists()
    assert "1 applied" in output


@pytest.fixture
def second(logged_in_client, statement):
    """A Statement of another Account, whose Kiosk Transaction is stored misspelt as Kiosc."""
    upload(
        logged_in_client,
        content=b"Type,Product,Started Date,Completed Date,Description,Amount,Fee,Currency,State,Balance\n"
        b"Card Payment,Current,2026-07-01 9:00:00,2026-07-01 9:00:00,Kiosk,-1,0,EUR,COMPLETED,99\n",
        filename="second.csv",
        new_account_name="Second",
    )
    Transaction.objects.filter(description="Kiosk").update(description="Kiosc")
    return Statement.objects.get(account__name="Second")


def test_a_refused_statement_doesnt_stop_the_others_from_being_applied(statement, second):
    misspell_mercator()
    Statement.objects.filter(pk=statement.pk).update(closing_balance=Decimal("1.00"))

    output = reparse("--apply")

    assert_mercator_still_misspelt()
    assert Transaction.objects.filter(description="Kiosk").exists()
    assert "2 Statements re-parsed: 1 applied, 1 refused, 0 unchanged, 0 failed." in output


def test_a_failure_while_applying_rolls_back_only_that_statement(statement, second, monkeypatch):
    from ledger import reparse as reparse_module

    run_automatic_steps = reparse_module.run_automatic_steps
    calls = []

    def fail_first(new):
        calls.append(new)
        if len(calls) == 1:
            raise RuntimeError("boom")
        return run_automatic_steps(new)

    monkeypatch.setattr(reparse_module, "run_automatic_steps", fail_first)
    misspell_mercator()

    output = reparse("--apply")

    assert_mercator_still_misspelt()
    assert Transaction.objects.filter(description="Kiosk").exists()
    assert "failed: RuntimeError: boom" in output
    assert "2 Statements re-parsed: 1 applied, 0 refused, 0 unchanged, 1 failed." in output


def test_apply_categorizes_a_row_the_parser_now_marks_as_a_fee(statement):
    Transaction.objects.filter(description="Fee: Corner Shop").update(
        is_fee=False, subcategory=None, source=""
    )

    output = reparse("--apply")

    fee = Transaction.objects.get(description="Fee: Corner Shop")
    assert fee.subcategory is not None
    assert (fee.is_fee, fee.subcategory.name, fee.source) == (True, "Bank fees", Source.PARSER)
    assert "Fee: Corner Shop: awaiting review → Finance / Bank fees (Parser)" in output
