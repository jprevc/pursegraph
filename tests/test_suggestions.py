import json

import pytest
from django.test import Client

from ledger import categorizers
from ledger.models import Setting, Source, Subcategory, Transaction
from tests.conftest import (
    group_caption,
    outcome_shown,
    page_text,
    review_queue_count,
    subcategory_id,
    transaction_id,
)
from tests.test_import import upload
from tests.test_rules import make_rule, make_transaction

pytestmark = pytest.mark.django_db


class FakeCategorizer:
    """A Categorizer on the Categorizer API: `run` fetches a batch of the waiting Transactions and answers each with
    a scripted (Category, Subcategory, confidence) per description, or None for no suggestion. It records every
    Transaction it was handed."""

    def __init__(self, answers=None, default=("Other", "Miscellaneous", 0.5)):
        self.answers = answers or {}
        self.default = default
        self.client = Client(headers={"Authorization": f"Bearer {self.secret()}"})
        self.fetched: list[dict] = []
        self.subcategories: list[dict] = []

    @staticmethod
    def secret():
        _token, secret = categorizers.create("Fake Categorizer", None)
        return secret

    def run(self):
        waiting = self.client.get("/api/categorizer/v1/transactions/").json()
        self.subcategories = waiting["subcategories"]
        for transaction in waiting["transactions"]:
            self.fetched.append(transaction)
            self.meanwhile(transaction)
            answer = self.answers.get(transaction["description"], self.default)
            if answer is None:
                body = {"subcategory": None}
            else:
                category, name, confidence = answer
                body = {"subcategory": subcategory_id(category, name), "confidence": confidence}
            sent = self.client.post(
                f"/api/categorizer/v1/transactions/{transaction['id']}/suggestion/",
                json.dumps(body),
                content_type="application/json",
            )
            assert sent.status_code == 200, sent.content
        return self

    def meanwhile(self, transaction):
        """What happens between fetching `transaction` and sending its Suggestion."""

    def asked(self):
        return [transaction["description"] for transaction in self.fetched]


def transactions_page(client):
    return client.get("/transactions/").content.decode()


def review_page(client):
    return client.get("/review/").content.decode()


def test_a_confident_suggestion_is_accepted(logged_in_client):
    upload(logged_in_client)

    FakeCategorizer({"Mercator Žalec": ("Food", "Groceries", 0.97)}).run()

    assert (
        outcome_shown(transactions_page(logged_in_client), "Mercator Žalec") == "Food → Groceries"
    )
    mercator = Transaction.objects.get(description="Mercator Žalec")
    assert mercator.source == Source.LLM
    assert ">Mercator Žalec<" not in review_page(logged_in_client)


def test_a_suggestion_below_the_threshold_waits_preselected_in_the_review_queue(logged_in_client):
    upload(logged_in_client)

    FakeCategorizer({"Mercator Žalec": ("Food", "Groceries", 0.62)}).run()

    page = review_page(logged_in_client)
    assert group_caption(page, "Mercator Žalec") == "Food › Groceries · 62\u00a0% sure"
    assert review_queue_count(page) == 6
    mercator = Transaction.objects.get(description="Mercator Žalec")
    assert (mercator.subcategory, mercator.source) == (None, "")
    assert mercator.suggested_subcategory_id == subcategory_id("Food", "Groceries")
    assert mercator.confidence == pytest.approx(0.62)


@pytest.mark.parametrize(("confidence", "accepted"), [(0.90, True), (0.8999, False)])
def test_the_default_threshold_is_090(logged_in_client, confidence, accepted):
    upload(logged_in_client)

    FakeCategorizer({"Corner Shop": ("Food", "Groceries", confidence)}).run()

    assert Transaction.objects.get(description="Corner Shop").source == (
        Source.LLM if accepted else ""
    )


def test_the_threshold_comes_from_the_settings(logged_in_client):
    Setting.put(Setting.AUTO_ACCEPT_THRESHOLD, "0.50")
    upload(logged_in_client)

    FakeCategorizer({"Corner Shop": ("Food", "Groceries", 0.55)}).run()

    assert outcome_shown(transactions_page(logged_in_client), "Corner Shop") == "Food → Groceries"


def test_only_unresolved_transactions_without_a_suggestion_are_asked_about(logged_in_client):
    make_rule(
        logged_in_client, subcategory_id("Food", "Groceries"), description_contains="mercator"
    )
    upload(logged_in_client)
    logged_in_client.post(
        f"/transactions/{transaction_id('To Janez Kranjc')}/outcome/", {"outcome": "transfer"}
    )

    first = FakeCategorizer().run()
    again = FakeCategorizer().run()

    assert sorted(first.asked()) == sorted(
        ["Hiša kave", "Payment from Ana Novak", "Corner Shop", "Čevljar"]
    )
    assert again.asked() == []


def test_a_decision_made_while_the_llm_was_asked_is_kept(logged_in_client):
    upload(logged_in_client)
    corner_shop = transaction_id("Corner Shop")

    class DecidingMeanwhile(FakeCategorizer):
        def meanwhile(self, transaction):
            if transaction["description"] == "Corner Shop":
                logged_in_client.post(
                    f"/transactions/{corner_shop}/outcome/", {"outcome": "transfer"}
                )

    DecidingMeanwhile(default=("Food", "Groceries", 0.99)).run()

    corner = Transaction.objects.get(pk=corner_shop)
    assert (corner.is_transfer, corner.source) == (True, Source.MANUAL)
    assert corner.suggested_subcategory is None


def test_a_categorizer_is_told_what_each_transaction_is(logged_in_client):
    upload(logged_in_client)

    categorizer = FakeCategorizer().run()

    corner = next(t for t in categorizer.fetched if t["description"] == "Corner Shop")
    assert (corner["direction"], corner["amount"]) == ("out", "50.02")
    assert "Card Payment" in corner["detail"]
    assert len(categorizer.subcategories) == Subcategory.objects.count()
    refund = next(t for t in categorizer.fetched if t["description"] == "Čevljar")
    assert (refund["direction"], refund["amount"]) == ("in", "25.00")


def test_examples_are_the_latest_manual_outcome_of_each_other_merchant(logged_in_client):
    groceries = Subcategory.objects.get(name="Groceries")
    restaurants = Subcategory.objects.get(name="Restaurants & cafés")
    older = make_transaction("Spar", subcategory=restaurants, source=Source.MANUAL)
    older.date = "2026-01-01"
    older.save()
    make_transaction("Spar", subcategory=groceries, source=Source.MANUAL)
    make_transaction("Hiša kave", subcategory=restaurants, source=Source.MANUAL)
    make_transaction("Tuš", subcategory=groceries, source=Source.RULE)
    make_transaction("To Mojca", is_transfer=True, source=Source.MANUAL)
    make_transaction("Hiša kave")  # unresolved, the one asked about
    (transaction,) = FakeCategorizer().run().fetched
    assert [(e["description"], e["subcategory"]) for e in transaction["examples"]] == [
        ("Spar", groceries.pk)
    ]


def test_no_suggestion_leaves_that_transaction_to_review_and_goes_on(logged_in_client):
    upload(logged_in_client)

    first = FakeCategorizer({"Hiša kave": None}).run()
    again = FakeCategorizer().run()

    assert len(first.asked()) == 6
    assert again.asked() == []  # not asked again
    assert group_caption(review_page(logged_in_client), "Hiša kave") == "No suggestion"


def test_a_merchant_counts_once_whatever_its_case(logged_in_client):
    groceries = Subcategory.objects.get(name="Groceries")
    make_transaction("SPAR", subcategory=groceries, source=Source.MANUAL)
    make_transaction("Spar", subcategory=groceries, source=Source.MANUAL)
    make_transaction("Hiša kave")
    (transaction,) = FakeCategorizer().run().fetched
    assert len(transaction["examples"]) == 1


def test_deleting_a_suggested_subcategory_asks_again(admin_client):
    make_transaction("Hiša kave")
    FakeCategorizer({"Hiša kave": ("Food", "Restaurants & cafés", 0.5)}).run()

    admin_client.post(f"/subcategories/{subcategory_id('Food', 'Restaurants & cafés')}/delete/")
    again = FakeCategorizer().run()

    assert again.asked() == ["Hiša kave"]


def test_the_import_summary_counts_what_waits_for_suggestions_or_review(logged_in_client):
    make_rule(
        logged_in_client, subcategory_id("Food", "Groceries"), description_contains="mercator"
    )

    summary = upload(logged_in_client).content.decode()

    assert "5 wait for suggestions and review" in page_text(summary)
