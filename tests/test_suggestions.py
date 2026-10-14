import re
from decimal import Decimal

import pytest

from ledger.models import Setting, Source, Subcategory, Transaction
from ledger.suggestions import (
    NoSuggestion,
    Query,
    Suggestion,
    SuggestionsUnavailable,
    backoff,
    run_once,
)
from tests.conftest import outcome_shown, review_queue_count, subcategory_id, transaction_id
from tests.test_import import upload
from tests.test_rules import make_rule, make_transaction

pytestmark = pytest.mark.django_db


class FakeSuggester:
    """Answers with scripted (Category, Subcategory, confidence) per description, and records every Query."""

    def __init__(self, answers=None, default=("Other", "Miscellaneous", 0.5)):
        self.answers = answers or {}
        self.default = default
        self.queries: list[Query] = []

    def suggest(self, query: Query) -> Suggestion:
        self.queries.append(query)
        category, name, confidence = self.answers.get(query.description, self.default)
        subcategory = next(
            s for s in query.subcategories if (s.category.name, s.name) == (category, name)
        )
        return Suggestion(subcategory, confidence)

    def asked(self):
        return [query.description for query in self.queries]


class DownSuggester:
    def suggest(self, query):
        raise SuggestionsUnavailable("connection refused")


def transactions_page(client):
    return client.get("/transactions/").content.decode()


def review_page(client):
    return client.get("/review/").content.decode()


def test_a_confident_suggestion_is_accepted(logged_in_client):
    upload(logged_in_client)

    run_once(FakeSuggester({"Mercator Žalec": ("Food", "Groceries", 0.97)}))

    assert (
        outcome_shown(transactions_page(logged_in_client), "Mercator Žalec") == "Food → Groceries"
    )
    mercator = Transaction.objects.get(description="Mercator Žalec")
    assert mercator.source == Source.LLM
    assert ">Mercator Žalec<" not in review_page(logged_in_client)


def test_a_suggestion_below_the_threshold_waits_preselected_in_the_review_queue(logged_in_client):
    upload(logged_in_client)

    run_once(FakeSuggester({"Mercator Žalec": ("Food", "Groceries", 0.62)}))

    page = review_page(logged_in_client)
    assert outcome_shown(page, "Mercator Žalec") == "Food → Groceries"
    assert "62%" in page
    assert review_queue_count(page) == 6
    mercator = Transaction.objects.get(description="Mercator Žalec")
    assert (mercator.subcategory, mercator.source) == (None, "")
    assert mercator.suggested_subcategory_id == subcategory_id("Food", "Groceries")
    assert mercator.confidence == pytest.approx(0.62)


@pytest.mark.parametrize(("confidence", "accepted"), [(0.90, True), (0.8999, False)])
def test_the_default_threshold_is_090(logged_in_client, confidence, accepted):
    upload(logged_in_client)

    run_once(FakeSuggester({"Corner Shop": ("Food", "Groceries", confidence)}))

    assert Transaction.objects.get(description="Corner Shop").source == (
        Source.LLM if accepted else ""
    )


def test_the_threshold_comes_from_the_settings(logged_in_client):
    Setting.put(Setting.AUTO_ACCEPT_THRESHOLD, "0.50")
    upload(logged_in_client)

    run_once(FakeSuggester({"Corner Shop": ("Food", "Groceries", 0.55)}))

    assert outcome_shown(transactions_page(logged_in_client), "Corner Shop") == "Food → Groceries"


def test_only_unresolved_transactions_without_a_suggestion_are_asked_about(logged_in_client):
    make_rule(
        logged_in_client, subcategory_id("Food", "Groceries"), description_contains="mercator"
    )
    upload(logged_in_client)
    logged_in_client.post(
        f"/transactions/{transaction_id('To Janez Kranjc')}/outcome/", {"outcome": "transfer"}
    )

    first = FakeSuggester()
    run_once(first)
    again = FakeSuggester()
    run_once(again)

    assert sorted(first.asked()) == sorted(
        ["Hiša kave", "Payment from Ana Novak", "Corner Shop", "Čevljar"]
    )
    assert again.asked() == []


def test_a_decision_made_while_the_llm_was_asked_is_kept(logged_in_client):
    upload(logged_in_client)
    corner_shop = transaction_id("Corner Shop")

    class DecidingMeanwhile(FakeSuggester):
        def suggest(self, query):
            if query.description == "Corner Shop":
                logged_in_client.post(
                    f"/transactions/{corner_shop}/outcome/", {"outcome": "transfer"}
                )
            return super().suggest(query)

    run_once(DecidingMeanwhile(default=("Food", "Groceries", 0.99)))

    corner = Transaction.objects.get(pk=corner_shop)
    assert (corner.is_transfer, corner.source) == (True, Source.MANUAL)
    assert corner.suggested_subcategory is None


def test_the_query_describes_the_transaction(logged_in_client):
    upload(logged_in_client)
    suggester = FakeSuggester()

    run_once(suggester)

    query = next(q for q in suggester.queries if q.description == "Corner Shop")
    assert (query.direction, query.amount) == ("out", Decimal("50.02"))
    assert "Card Payment" in query.detail
    assert len(query.subcategories) == Subcategory.objects.count()
    refund = next(q for q in suggester.queries if q.description == "Čevljar")
    assert (refund.direction, refund.amount) == ("in", Decimal("25.00"))


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
    suggester = FakeSuggester()

    run_once(suggester)

    (query,) = suggester.queries
    assert [(e.description, e.subcategory.name) for e in query.examples] == [("Spar", "Groceries")]


def test_unavailable_suggestions_show_in_the_sidebar_until_they_recover(logged_in_client):
    upload(logged_in_client)

    run_once(DownSuggester())

    page = review_page(logged_in_client)
    assert "Suggestions unavailable" in page
    assert review_queue_count(page) == 6
    assert not Transaction.objects.filter(suggested_subcategory__isnull=False).exists()

    run_once(FakeSuggester())

    assert "Suggestions unavailable" not in review_page(logged_in_client)
    assert Transaction.objects.filter(suggested_subcategory__isnull=False).count() == 6


def test_an_unusable_answer_leaves_that_transaction_to_review_and_goes_on(logged_in_client):
    upload(logged_in_client)

    class UnusableFirst(FakeSuggester):
        def suggest(self, query):
            if query.description == "Hiša kave":
                self.queries.append(query)
                raise NoSuggestion("not one of the Subcategories")
            return super().suggest(query)

    first = UnusableFirst()
    run_once(first)
    again = FakeSuggester()
    run_once(again)

    assert len(first.asked()) == 6
    assert again.asked() == []  # not asked again
    page = review_page(logged_in_client)
    assert "Suggestions unavailable" not in page
    assert outcome_shown(page, "Hiša kave") == "Awaiting review"


def test_a_merchant_counts_once_whatever_its_case(logged_in_client):
    groceries = Subcategory.objects.get(name="Groceries")
    make_transaction("SPAR", subcategory=groceries, source=Source.MANUAL)
    make_transaction("Spar", subcategory=groceries, source=Source.MANUAL)
    make_transaction("Hiša kave")
    suggester = FakeSuggester()

    run_once(suggester)

    (query,) = suggester.queries
    assert len(query.examples) == 1


def test_deleting_a_suggested_subcategory_asks_again(admin_client):
    make_transaction("Hiša kave")
    run_once(FakeSuggester({"Hiša kave": ("Food", "Restaurants & cafés", 0.5)}))

    admin_client.post(f"/subcategories/{subcategory_id('Food', 'Restaurants & cafés')}/delete/")
    again = FakeSuggester()
    run_once(again)

    assert again.asked() == ["Hiša kave"]


def test_the_suggestions_shown_can_be_accepted_in_bulk(logged_in_client):
    upload(logged_in_client)
    run_once(
        FakeSuggester(
            {
                "Mercator Žalec": ("Food", "Groceries", 0.6),
                "Hiša kave": ("Food", "Restaurants & cafés", 0.7),
            }
        )
    )
    page = review_page(logged_in_client)
    shown = re.findall(r'name="accept" value="([^"]+)"', page)
    assert len(shown) == 6
    # Decided by hand after the page was shown: bulk accept leaves it alone.
    logged_in_client.post(
        f"/transactions/{transaction_id('Hiša kave')}/outcome/", {"outcome": "transfer"}
    )

    response = logged_in_client.post("/review/accept/", {"accept": shown})

    assert response.status_code == 302
    assert "Nothing to review" in review_page(logged_in_client)
    page = transactions_page(logged_in_client)
    assert outcome_shown(page, "Mercator Žalec") == "Food → Groceries"
    assert outcome_shown(page, "Hiša kave") == "Transfer"
    assert Transaction.objects.get(description="Mercator Žalec").source == Source.MANUAL


def test_bulk_accept_takes_the_suggestion_that_was_shown(logged_in_client):
    upload(logged_in_client)
    run_once(FakeSuggester({"Corner Shop": ("Food", "Groceries", 0.6)}))
    corner_shop = transaction_id("Corner Shop")

    logged_in_client.post(
        "/review/accept/", {"accept": [f"{corner_shop}:{subcategory_id('Food', 'Other')}"]}
    )

    assert outcome_shown(transactions_page(logged_in_client), "Corner Shop") == "Food → Other"


def test_the_import_summary_counts_what_waits_for_suggestions_or_review(logged_in_client):
    make_rule(
        logged_in_client, subcategory_id("Food", "Groceries"), description_contains="mercator"
    )

    summary = upload(logged_in_client).content.decode()

    assert "5 Transactions waiting for suggestions or review" in summary


def test_backoff_doubles_up_to_a_limit():
    delays = [backoff(attempt) for attempt in range(1, 10)]
    assert delays[:3] == [5, 10, 20]
    assert delays[-1] == 300
    assert delays == sorted(delays)
