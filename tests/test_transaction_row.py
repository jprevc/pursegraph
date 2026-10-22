import html
import json

import pytest

from ledger.models import Rule, Source, Subcategory, Transaction
from ledger.outcomes import most_used_outcomes
from tests.conftest import outcome_shown, subcategory_id, transaction_id
from tests.test_import import upload

pytestmark = pytest.mark.django_db


def test_most_used_outcomes_are_the_households_five_most_used_subcategories(household):
    # Groceries 4, Salary 3, Shopping › Other 2, then Restaurants & Interest 1 each, in the Categories' order;
    # Transfers and Transactions awaiting review don't count.
    assert [str(s) for s in most_used_outcomes()] == [
        "Food → Groceries",
        "Income → Salary",
        "Shopping → Other",
        "Food → Restaurants & cafés",
        "Income → Interest",
    ]


def test_with_nothing_categorized_nothing_is_most_used(db):
    assert most_used_outcomes() == []


def save(client, description, outcome, **data):
    return client.post(
        f"/transactions/{transaction_id(description)}/outcome/",
        {"outcome": outcome, **data},
        HTTP_HX_REQUEST="true",
    )


def test_a_save_shows_the_outcome_as_text_with_a_saved_line_and_undo(logged_in_client):
    upload(logged_in_client)

    response = save(logged_in_client, "Corner Shop", subcategory_id("Food", "Groceries"))

    row = response.content.decode()
    assert outcome_shown(row, "Corner Shop") == "Food → Groceries"
    assert "by hand" in row
    assert "Saved as Food › Groceries" in html.unescape(row)
    assert ">Undo</button>" in row
    assert f'href="/rules/new/?transaction={transaction_id("Corner Shop")}"' in row
    assert (
        json.loads(response["HX-Trigger"])["announce"] == "Saved Corner Shop as Food › Groceries."
    )


def test_a_row_is_changed_only_through_change_never_by_a_select_on_change(logged_in_client):
    upload(logged_in_client)

    page = logged_in_client.get("/transactions/").content.decode()

    assert 'hx-trigger="change' not in page
    assert "Change</button>" in page


def undo(client, description):
    return client.post(f"/transactions/{transaction_id(description)}/undo/", HTTP_HX_REQUEST="true")


def test_undo_puts_back_the_outcome_a_save_replaced_with_its_source(logged_in_client):
    upload(logged_in_client)
    save(logged_in_client, "Fee: Corner Shop", subcategory_id("Food", "Groceries"))

    response = undo(logged_in_client, "Fee: Corner Shop")

    row = response.content.decode()
    assert outcome_shown(row, "Fee: Corner Shop") == "Finance → Bank fees"
    assert "by import" in row
    assert "Saved as" not in row
    assert json.loads(response["HX-Trigger"])["announce"] == (
        "Undone. Fee: Corner Shop is back to Finance › Bank fees."
    )


def test_undo_links_a_transaction_to_the_rule_that_had_set_it_again(logged_in_client, household):
    groceries = Subcategory.objects.get(category__name="Food", name="Groceries")
    rule = Rule.objects.create(description_contains="Mercator", subcategory=groceries)
    Transaction.objects.filter(description="Mercator").update(source=Source.RULE, rule=rule)
    save(logged_in_client, "Mercator", "transfer")

    undo(logged_in_client, "Mercator")

    mercator = Transaction.objects.get(description="Mercator")
    assert (mercator.subcategory, mercator.source, mercator.rule) == (groceries, Source.RULE, rule)


def test_undo_pairs_a_transfer_with_its_other_side_again(logged_in_client, household):
    out = Transaction.objects.get(description="To Joint Revolut")
    into = Transaction.objects.get(description="From Ana's Sparkasse")
    Transaction.objects.filter(pk=out.pk).update(counterpart=into)
    Transaction.objects.filter(pk=into.pk).update(counterpart=out)
    save(logged_in_client, "To Joint Revolut", subcategory_id("Food", "Groceries"))
    assert Transaction.objects.get(pk=into.pk).counterpart is None

    undo(logged_in_client, "To Joint Revolut")

    out.refresh_from_db()
    into.refresh_from_db()
    assert (out.is_transfer, out.counterpart, into.counterpart) == (True, into, out)


def test_undo_is_refused_once_used_or_without_a_save(logged_in_client):
    upload(logged_in_client)

    assert undo(logged_in_client, "Corner Shop").status_code == 400
    save(logged_in_client, "Corner Shop", "transfer")
    assert undo(logged_in_client, "Corner Shop").status_code == 200
    assert undo(logged_in_client, "Corner Shop").status_code == 400
    page = logged_in_client.get("/transactions/").content.decode()
    assert outcome_shown(page, "Corner Shop") == "Awaiting review"


def test_undo_is_refused_once_the_rule_that_had_set_it_is_deleted(logged_in_client, household):
    groceries = Subcategory.objects.get(category__name="Food", name="Groceries")
    rule = Rule.objects.create(description_contains="Mercator", subcategory=groceries)
    Transaction.objects.filter(description="Mercator").update(source=Source.RULE, rule=rule)
    save(logged_in_client, "Mercator", "transfer")
    rule.delete()

    assert undo(logged_in_client, "Mercator").status_code == 400
    assert Transaction.objects.get(description="Mercator").is_transfer


def test_the_source_caption_carries_the_specific_reason_as_its_title(db):
    from datetime import date

    from ledger.models import Account

    account = Account.objects.create(name="Joint N26", bank="n26")
    savings = Account.objects.create(name="Savings", bank="n26")
    groceries = Subcategory.objects.get(category__name="Food", name="Groceries")
    rule = Rule.objects.create(description_contains="HOFER", subcategory=groceries)

    def made(**outcome):
        return Transaction.objects.create(
            account=account, date=date(2026, 9, 8), amount=-5, description="x", **outcome
        )

    by_rule = made(subcategory=groceries, source=Source.RULE, rule=rule)
    by_lost_rule = made(subcategory=groceries, source=Source.RULE)
    by_llm = made(
        subcategory=groceries, source=Source.LLM, suggested_subcategory=groceries, confidence=0.92
    )
    by_iban = made(is_transfer=True, source=Source.IBAN, counterparty_iban="SI56 1234")
    other_side = Transaction.objects.create(
        account=savings, date=date(2026, 9, 9), amount=5, description="y", is_transfer=True
    )
    paired = made(is_transfer=True, source=Source.PAIRING, counterpart=other_side)

    assert by_rule.source_reason == "Matched the Rule “HOFER” → Food › Groceries"
    assert by_lost_rule.source_reason == "A Rule matched it; the Rule has since been deleted."
    assert by_llm.source_reason == "The local model suggested it, 92 % sure."
    assert by_iban.source_reason == "Its counterparty IBAN, SI56 1234, is one of the Household's."
    assert paired.source_reason == "Paired with the other side in Savings on 9 Sep 2026."
    assert made(subcategory=groceries, source=Source.MANUAL).source_reason == "A Member chose it."
    assert made().source_reason == ""
