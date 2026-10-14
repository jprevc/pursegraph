import pytest

from ledger.models import Setting, Source, Transaction
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
    return client.get("/suggestions/").content.decode()


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

    admin_client.post("/suggestions/", {"threshold": "0.70"})

    assert "2 queued Transactions now clear the threshold" in settings_page(admin_client)
    assert Transaction.objects.unresolved().count() == 3  # nothing accepted yet

    response = admin_client.post("/suggestions/accept/")

    assert response.status_code == 302
    corner, hisa, cevljar = (
        Transaction.objects.get(description=d) for d in ("Corner Shop", "Hiša kave", "Čevljar")
    )
    assert (corner.subcategory_id, corner.source) == (subcategory_id("Food", "Groceries"), "llm")
    assert (hisa.subcategory_id, hisa.source) == (
        subcategory_id("Food", "Restaurants & cafés"),
        Source.LLM,
    )
    assert (cevljar.subcategory, cevljar.source) == (None, "")
    assert "now clear the threshold" not in settings_page(admin_client)


def test_declining_the_offer_leaves_the_review_queue_as_it_is(admin_client):
    suggest("Corner Shop")

    admin_client.post("/suggestions/", {"threshold": "0.70"})

    assert Transaction.objects.get(description="Corner Shop").is_unresolved
    review = admin_client.get("/review/").content.decode()
    assert outcome_shown(review, "Corner Shop") == "Food → Groceries"


def test_accepting_leaves_transactions_decided_meanwhile_alone(admin_client, logged_in_client):
    suggest("Corner Shop")
    admin_client.post("/suggestions/", {"threshold": "0.70"})
    logged_in_client.post(
        f"/transactions/{transaction_id('Corner Shop')}/outcome/", {"outcome": "transfer"}
    )

    admin_client.post("/suggestions/accept/")

    corner = Transaction.objects.get(description="Corner Shop")
    assert (corner.is_transfer, corner.source) == (True, Source.MANUAL)


def test_raising_the_threshold_keeps_existing_llm_outcomes(admin_client):
    Setting.put(Setting.AUTO_ACCEPT_THRESHOLD, "0.80")
    suggest("Corner Shop")

    admin_client.post("/suggestions/", {"threshold": "0.95"})

    corner = Transaction.objects.get(description="Corner Shop")
    assert (corner.subcategory_id, corner.source) == (subcategory_id("Food", "Groceries"), "llm")


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
    assert (corner.subcategory_id, corner.source) == (subcategory_id("Food", "Groceries"), "llm")


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
        ("/suggestions/accept/", {}),
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
