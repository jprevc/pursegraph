import re

import pytest

from ledger.models import Setting, Source, Subcategory, Transaction
from ledger.suggestions import run_once
from tests.conftest import outcome_shown, subcategory_id, transaction_id
from tests.test_rules import make_transaction
from tests.test_suggestions import FakeSuggester

pytestmark = pytest.mark.django_db

ANSWERS = {
    "Corner Shop": ("Food", "Groceries", 0.85),
    "Hiša kave": ("Food", "Restaurants & cafés", 0.75),
    "Čevljar": ("Shopping", "Clothing & shoes", 0.40),
}


def suggest(*descriptions):
    for description in descriptions:
        make_transaction(description)
    run_once(FakeSuggester(ANSWERS))


def settings_page(client):
    return client.get("/suggestions/", follow=True).content.decode()


def lower_threshold(client, threshold):
    """Saves a lower threshold and returns the page it leads to, with any offer."""
    return client.post("/suggestions/", {"threshold": threshold}, follow=True).content.decode()


def accept_offer(client, page):
    """Accepts the offer on `page`, as its button would."""
    return client.post(
        "/suggestions/accept/", {"accept": re.findall(r'name="accept" value="(\d+)"', page)}
    )


def test_an_admin_edits_the_threshold(admin_client):
    assert 'value="0.90"' in settings_page(admin_client)

    response = admin_client.post("/suggestions/", {"threshold": "0.80"})

    assert response.status_code == 302
    assert Setting.get(Setting.AUTO_ACCEPT_THRESHOLD) == "0.80"
    assert 'value="0.80"' in settings_page(admin_client)


@pytest.mark.parametrize("threshold", ["1.5", "-0.1", "high", ""])
def test_the_threshold_is_a_probability(admin_client, threshold):
    response = admin_client.post("/suggestions/", {"threshold": threshold})

    assert response.status_code == 200
    assert Setting.get(Setting.AUTO_ACCEPT_THRESHOLD) == "0.90"


def test_lowering_the_threshold_offers_the_suggestions_that_now_clear_it(admin_client):
    suggest("Corner Shop", "Hiša kave", "Čevljar")

    page = lower_threshold(admin_client, "0.70")

    assert "2 queued Transactions now clear the threshold" in page
    assert Transaction.objects.unresolved().count() == 3  # nothing accepted yet

    response = accept_offer(admin_client, page)

    assert response.status_code == 302
    corner, hisa, cevljar = (
        Transaction.objects.get(description=d) for d in ("Corner Shop", "Hiša kave", "Čevljar")
    )
    assert (corner.subcategory_id, corner.source) == (
        subcategory_id("Food", "Groceries"),
        Source.LLM,
    )
    assert (hisa.subcategory_id, hisa.source) == (
        subcategory_id("Food", "Restaurants & cafés"),
        Source.LLM,
    )
    assert (cevljar.subcategory, cevljar.source) == (None, "")
    assert "now clear" not in settings_page(admin_client)


def test_the_offer_comes_only_with_lowering(admin_client):
    Setting.put(Setting.AUTO_ACCEPT_THRESHOLD, "0.95")
    suggest("Corner Shop")
    Setting.put(Setting.AUTO_ACCEPT_THRESHOLD, "0.70")

    assert "now clears" not in settings_page(admin_client)
    assert "now clears" not in lower_threshold(admin_client, "0.75")  # raised
    assert "now clears" not in lower_threshold(admin_client, "0.75")  # unchanged
    assert "now clears" in lower_threshold(admin_client, "0.60")


def test_accepting_takes_only_the_transactions_offered(admin_client):
    suggest("Corner Shop", "Hiša kave")
    page = lower_threshold(admin_client, "0.80")
    lower_threshold(admin_client, "0.70")  # in another tab

    accept_offer(admin_client, page)

    assert Transaction.objects.get(description="Corner Shop").source == Source.LLM
    assert Transaction.objects.get(description="Hiša kave").is_unresolved


def test_accepting_respects_a_threshold_raised_meanwhile(admin_client):
    suggest("Corner Shop", "Hiša kave")
    page = lower_threshold(admin_client, "0.70")
    Setting.put(Setting.AUTO_ACCEPT_THRESHOLD, "0.80")

    accept_offer(admin_client, page)

    assert Transaction.objects.get(description="Corner Shop").source == Source.LLM
    assert Transaction.objects.get(description="Hiša kave").is_unresolved


def test_declining_the_offer_leaves_the_review_queue_as_it_is(admin_client):
    suggest("Corner Shop")

    admin_client.post("/suggestions/", {"threshold": "0.70"})

    assert Transaction.objects.get(description="Corner Shop").is_unresolved
    review = admin_client.get("/review/").content.decode()
    assert outcome_shown(review, "Corner Shop") == "Food → Groceries"


def test_accepting_leaves_transactions_decided_meanwhile_alone(admin_client, logged_in_client):
    suggest("Corner Shop")
    page = lower_threshold(admin_client, "0.70")
    logged_in_client.post(
        f"/transactions/{transaction_id('Corner Shop')}/outcome/", {"outcome": "transfer"}
    )

    accept_offer(admin_client, page)

    corner = Transaction.objects.get(description="Corner Shop")
    assert (corner.is_transfer, corner.source) == (True, Source.MANUAL)


def test_raising_the_threshold_keeps_existing_llm_outcomes(admin_client):
    Setting.put(Setting.AUTO_ACCEPT_THRESHOLD, "0.80")
    suggest("Corner Shop")

    admin_client.post("/suggestions/", {"threshold": "0.95"})

    corner = Transaction.objects.get(description="Corner Shop")
    assert (corner.subcategory_id, corner.source) == (
        subcategory_id("Food", "Groceries"),
        Source.LLM,
    )


def test_re_suggesting_asks_again_about_the_queued_transactions_only(admin_client):
    Setting.put(Setting.AUTO_ACCEPT_THRESHOLD, "0.80")
    suggest("Corner Shop", "Hiša kave", "Čevljar")

    response = admin_client.post("/suggestions/resuggest/")

    assert response.status_code == 302
    hisa = Transaction.objects.get(description="Hiša kave")
    assert (hisa.suggested_subcategory, hisa.confidence) == (None, None)
    again = FakeSuggester()
    run_once(again)
    assert sorted(again.asked()) == ["Hiša kave", "Čevljar"]
    corner = Transaction.objects.get(description="Corner Shop")
    assert (corner.subcategory_id, corner.source) == (
        subcategory_id("Food", "Groceries"),
        Source.LLM,
    )


def test_re_suggesting_also_asks_again_after_an_unusable_answer(admin_client):
    make_transaction("Hiša kave")
    Transaction.objects.update(confidence=0)

    admin_client.post("/suggestions/resuggest/")
    again = FakeSuggester()
    run_once(again)

    assert again.asked() == ["Hiša kave"]


def test_non_admins_are_forbidden(logged_in_client):
    suggest("Corner Shop")

    for url, data in [
        ("/suggestions/", None),
        ("/suggestions/", {"threshold": "0.10"}),
        ("/suggestions/accept/", {"accept": [transaction_id("Corner Shop")]}),
        ("/suggestions/resuggest/", {}),
    ]:
        response = logged_in_client.get(url) if data is None else logged_in_client.post(url, data)
        assert response.status_code == 403, url
    assert Setting.get(Setting.AUTO_ACCEPT_THRESHOLD) == "0.90"
    corner = Transaction.objects.get(description="Corner Shop")
    assert corner.is_unresolved
    assert corner.confidence is not None


def test_only_admins_see_the_suggestions_link(logged_in_client, admin_client):
    assert b'href="/suggestions/"' in admin_client.get("/").content
    assert b'href="/suggestions/"' not in logged_in_client.get("/").content


def test_raising_the_threshold_applies_to_a_batch_already_running(admin_client):
    for description in ("Corner Shop", "Hiša kave"):
        make_transaction(description)

    class RaisedMeanwhile(FakeSuggester):
        def suggest(self, query):
            if query.description == "Corner Shop":
                admin_client.post("/suggestions/", {"threshold": "0.99"})
            return super().suggest(query)

    run_once(RaisedMeanwhile(default=("Food", "Groceries", 0.95)))

    assert Transaction.objects.unresolved().count() == 2


def test_a_subcategory_deleted_during_a_batch_is_no_longer_offered(admin_client):
    for description in ("Corner Shop", "Hiša kave"):
        make_transaction(description)
    cafes = subcategory_id("Food", "Restaurants & cafés")

    class DeletedMeanwhile(FakeSuggester):
        def suggest(self, query):
            if not self.queries:
                admin_client.post(f"/subcategories/{cafes}/delete/")
            return super().suggest(query)

    first = DeletedMeanwhile(
        {"Hiša kave": ("Food", "Groceries", 0.5)}, default=("Food", "Restaurants & cafés", 0.5)
    )
    run_once(first)
    assert first.asked() == ["Corner Shop", "Hiša kave"]
    assert cafes not in [s.pk for s in first.queries[1].subcategories]

    again = FakeSuggester()
    run_once(again)

    assert again.asked() == [
        "Corner Shop"
    ]  # its answer was the deleted one: asked again, not unusable


def test_an_llm_outcome_in_a_deleted_subcategory_moves_to_the_catch_all(admin_client):
    suggest("Hiša kave")
    Transaction.objects.filter(description="Hiša kave").update(
        subcategory=subcategory_id("Food", "Restaurants & cafés"), source=Source.LLM
    )

    admin_client.post(f"/subcategories/{subcategory_id('Food', 'Restaurants & cafés')}/delete/")

    hisa = Transaction.objects.get(description="Hiša kave")
    assert hisa.subcategory == Subcategory.objects.get(category__name="Food", is_catch_all=True)
    assert hisa.source == Source.LLM
