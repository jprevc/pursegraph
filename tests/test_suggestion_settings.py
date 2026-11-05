import re
from datetime import UTC, date, datetime

import pytest
from django.contrib.auth import get_user_model
from django.utils import timezone

from ledger import categorizers
from ledger.models import Account, Setting, Source, Statement, Subcategory, Transaction
from tests.conftest import group_caption, page_text, subcategory_id, transaction_id
from tests.test_categorizer_api import WAITING, create_token
from tests.test_rules import make_transaction
from tests.test_suggestions import FakeCategorizer

pytestmark = pytest.mark.django_db

ANSWERS = {
    "Corner Shop": ("Food", "Groceries", 0.85),
    "Hiša kave": ("Food", "Restaurants & cafés", 0.75),
    "Čevljar": ("Shopping", "Clothing & shoes", 0.40),
}


def suggest(*descriptions):
    for description in descriptions:
        make_transaction(description)
    FakeCategorizer(ANSWERS).run()


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
    assert 'name="threshold" value="90"' in settings_page(admin_client)

    response = admin_client.post("/suggestions/", {"threshold": "80"})

    assert response.status_code == 302
    assert Setting.get(Setting.AUTO_ACCEPT_THRESHOLD) == "0.80"
    assert 'name="threshold" value="80"' in settings_page(admin_client)


@pytest.mark.parametrize("threshold", ["105", "45", "72", "high", ""])
def test_the_threshold_is_a_percentage_in_steps_of_5(admin_client, threshold):
    response = admin_client.post("/suggestions/", {"threshold": threshold})

    assert response.status_code == 200
    assert Setting.get(Setting.AUTO_ACCEPT_THRESHOLD) == "0.90"


def test_lowering_the_threshold_offers_the_suggestions_that_now_clear_it(admin_client):
    suggest("Corner Shop", "Hiša kave", "Čevljar")

    page = lower_threshold(admin_client, "70")

    assert (
        "2 Transactions in the Review queue are now at least 70 % sure. Accept them now, or leave them in the "
        "queue with the suggestion first." in page_text(page)
    )
    assert Transaction.objects.unresolved().count() == 3  # nothing accepted yet

    response = accept_offer(admin_client, page)

    assert response.status_code == 302
    corner, hisa, cevljar = (
        Transaction.objects.get(description=d) for d in ("Corner Shop", "Hiša kave", "Čevljar")
    )
    assert (corner.subcategory_id, corner.source) == (
        subcategory_id("Food", "Groceries"),
        Source.CATEGORIZER,
    )
    assert (hisa.subcategory_id, hisa.source) == (
        subcategory_id("Food", "Restaurants & cafés"),
        Source.CATEGORIZER,
    )
    assert (cevljar.subcategory, cevljar.source) == (None, "")
    assert "now at least" not in settings_page(admin_client)


def test_the_offer_comes_only_with_lowering(admin_client):
    Setting.put(Setting.AUTO_ACCEPT_THRESHOLD, "0.95")
    suggest("Corner Shop")
    Setting.put(Setting.AUTO_ACCEPT_THRESHOLD, "0.70")

    assert "now at least" not in settings_page(admin_client)
    assert "now at least" not in lower_threshold(admin_client, "75")  # raised
    assert "now at least" not in lower_threshold(admin_client, "75")  # unchanged
    assert "now at least" in lower_threshold(admin_client, "60")


def test_accepting_takes_only_the_transactions_offered(admin_client):
    suggest("Corner Shop", "Hiša kave")
    page = lower_threshold(admin_client, "80")
    lower_threshold(admin_client, "70")  # in another tab

    accept_offer(admin_client, page)

    assert Transaction.objects.get(description="Corner Shop").source == Source.CATEGORIZER
    assert Transaction.objects.get(description="Hiša kave").is_unresolved


def test_accepting_respects_a_threshold_raised_meanwhile(admin_client):
    suggest("Corner Shop", "Hiša kave")
    page = lower_threshold(admin_client, "70")
    Setting.put(Setting.AUTO_ACCEPT_THRESHOLD, "0.80")

    accept_offer(admin_client, page)

    assert Transaction.objects.get(description="Corner Shop").source == Source.CATEGORIZER
    assert Transaction.objects.get(description="Hiša kave").is_unresolved


def test_declining_the_offer_leaves_the_review_queue_as_it_is(admin_client):
    suggest("Corner Shop")

    admin_client.post("/suggestions/", {"threshold": "70"})

    assert Transaction.objects.get(description="Corner Shop").is_unresolved
    review = admin_client.get("/review/").content.decode()
    assert group_caption(review, "Corner Shop").startswith("Food › Groceries ·")


def test_accepting_leaves_transactions_decided_meanwhile_alone(admin_client, logged_in_client):
    suggest("Corner Shop")
    page = lower_threshold(admin_client, "70")
    logged_in_client.post(
        f"/transactions/{transaction_id('Corner Shop')}/outcome/", {"outcome": "transfer"}
    )

    accept_offer(admin_client, page)

    corner = Transaction.objects.get(description="Corner Shop")
    assert (corner.is_transfer, corner.source) == (True, Source.MANUAL)


def test_raising_the_threshold_keeps_existing_categorizer_outcomes(admin_client):
    Setting.put(Setting.AUTO_ACCEPT_THRESHOLD, "0.80")
    suggest("Corner Shop")

    admin_client.post("/suggestions/", {"threshold": "95"})

    corner = Transaction.objects.get(description="Corner Shop")
    assert (corner.subcategory_id, corner.source) == (
        subcategory_id("Food", "Groceries"),
        Source.CATEGORIZER,
    )


def test_re_suggesting_asks_again_about_the_queued_transactions_only(admin_client):
    Setting.put(Setting.AUTO_ACCEPT_THRESHOLD, "0.80")
    suggest("Corner Shop", "Hiša kave", "Čevljar")

    response = admin_client.post("/suggestions/resuggest/")

    assert response.status_code == 302
    hisa = Transaction.objects.get(description="Hiša kave")
    assert (hisa.suggested_subcategory, hisa.confidence) == (None, None)
    again = FakeCategorizer().run()
    assert sorted(again.asked()) == ["Hiša kave", "Čevljar"]
    corner = Transaction.objects.get(description="Corner Shop")
    assert (corner.subcategory_id, corner.source) == (
        subcategory_id("Food", "Groceries"),
        Source.CATEGORIZER,
    )


def test_re_suggesting_also_asks_again_after_no_suggestion(admin_client, connected):
    make_transaction("Hiša kave")
    Transaction.objects.update(confidence=0)

    admin_client.post("/suggestions/resuggest/")
    again = FakeCategorizer().run()

    assert again.asked() == ["Hiša kave"]


def test_non_admins_are_forbidden(logged_in_client):
    suggest("Corner Shop")

    for url, data in [
        ("/suggestions/", None),
        ("/suggestions/", {"threshold": "10"}),
        ("/suggestions/accept/", {"accept": [transaction_id("Corner Shop")]}),
        ("/suggestions/resuggest/", {}),
    ]:
        response = logged_in_client.get(url) if data is None else logged_in_client.post(url, data)
        assert response.status_code == 403, url
    assert Setting.get(Setting.AUTO_ACCEPT_THRESHOLD) == "0.90"
    corner = Transaction.objects.get(description="Corner Shop")
    assert corner.is_unresolved
    assert corner.confidence is not None


def test_only_admins_see_the_suggestions_link(logged_in_client, admin_client, household):
    assert b'href="/suggestions/"' in admin_client.get("/").content
    assert b'href="/suggestions/"' not in logged_in_client.get("/").content


def test_raising_the_threshold_after_a_fetch_applies_to_its_suggestions(admin_client):
    for description in ("Corner Shop", "Hiša kave"):
        make_transaction(description)

    class RaisedMeanwhile(FakeCategorizer):
        def meanwhile(self, transaction):
            if transaction["description"] == "Corner Shop":
                admin_client.post("/suggestions/", {"threshold": "100"})

    RaisedMeanwhile(default=("Food", "Groceries", 0.95)).run()

    assert Transaction.objects.unresolved().count() == 2


def test_a_categorizer_outcome_in_a_deleted_subcategory_moves_to_the_catch_all(admin_client):
    suggest("Hiša kave")
    Transaction.objects.filter(description="Hiša kave").update(
        subcategory=subcategory_id("Food", "Restaurants & cafés"), source=Source.CATEGORIZER
    )

    admin_client.post(f"/subcategories/{subcategory_id('Food', 'Restaurants & cafés')}/delete/")

    hisa = Transaction.objects.get(description="Hiša kave")
    assert hisa.subcategory == Subcategory.objects.get(category__name="Food", is_catch_all=True)
    assert hisa.source == Source.CATEGORIZER


# The status strip, the chart and Ask again (docs/design/admin.md)


@pytest.fixture
def at_1402(monkeypatch):
    """The clock at 14:02 in Ljubljana on 27 October 2026."""
    monkeypatch.setattr(timezone, "now", lambda: datetime(2026, 10, 27, 13, 2, tzinfo=UTC))


def strip(client):
    """The status strip's text."""
    page = settings_page(client)
    return page_text(
        page[
            page.index('<section class="panel suggestions-strip"') : page.index("suggestions-chart")
        ]
    )


def on_a_statement_imported(when, *descriptions):
    """Puts the Transactions described on a Statement imported at `when`."""
    statement = Statement.objects.create(
        account=Account.objects.get(),
        format=Statement.Format.CSV,
        period_start=date(2026, 6, 1),
        period_end=date(2026, 6, 30),
        opening_balance=0,
        closing_balance=0,
        imported_by=get_user_model().objects.get(),
        sha256=str(when),
        file="statement.csv",
    )
    Statement.objects.filter(pk=statement.pk).update(imported_at=when)
    statement.transactions.add(*Transaction.objects.filter(description__in=descriptions))


def test_the_strip_says_how_long_the_oldest_transaction_has_waited(admin_client, at_1402):
    for description in ("Corner Shop", "Hiša kave", "Kiosk"):
        make_transaction(description)
    on_a_statement_imported(datetime(2026, 10, 25, 8, 30, tzinfo=UTC), "Corner Shop")
    on_a_statement_imported(datetime(2026, 10, 27, 12, 0, tzinfo=UTC), "Hiša kave", "Corner Shop")
    on_a_statement_imported(datetime(2026, 10, 20, 9, 0, tzinfo=UTC), "Kiosk")
    Transaction.objects.filter(description="Kiosk").update(confidence=0)  # answered: not waiting

    assert strip(admin_client).startswith("Waiting for a suggestion 2 since 25 Oct 2026 09:30")


def test_with_nothing_waiting_the_strip_says_so(admin_client):
    assert strip(admin_client).startswith("Waiting for a suggestion 0 nothing waits")


def test_the_strip_says_when_the_last_suggestion_arrived_and_from_which_token(
    admin_client, client, at_1402
):
    assert "Last suggestion none yet" in strip(admin_client)
    make_transaction("Corner Shop")
    secret = create_token(admin_client, "Qwen on the NAS")
    create_token(admin_client, "Cloud")

    client.post(
        f"{WAITING}{transaction_id('Corner Shop')}/suggestion/",
        '{"subcategory": null}',
        content_type="application/json",
        headers={"Authorization": f"Bearer {secret}"},
    )

    assert "Last suggestion 14:02 from Qwen on the NAS" in strip(admin_client)
    assert "Check now" not in settings_page(admin_client)


def test_the_strip_counts_the_suggestions(admin_client, at_1402):
    suggest("Corner Shop", "Hiša kave", "Čevljar")  # all below 90 %, so all queued
    Transaction.objects.update(date=date(2026, 10, 5))
    make_transaction("Kiosk")  # not asked yet
    Transaction.objects.filter(description="Corner Shop").update(
        subcategory=subcategory_id("Food", "Groceries"), source=Source.CATEGORIZER
    )

    text = strip(admin_client)

    assert "With a suggestion 2 By Categorizers this month 1" in text


def test_the_chart_lists_how_sure_the_queued_suggestions_are(admin_client):
    suggest("Corner Shop", "Hiša kave", "Čevljar")

    page = settings_page(admin_client)

    assert (
        'aria-label="How sure the 3 queued suggestions are: 40 to 45 %: 1, 75 to 80 %: 1, 85 to 90 %: 1"'
        in page
    )
    assert "Auto-accept · 90 %" in page_text(page)


def test_ask_again_is_confirmed_inline(admin_client):
    suggest("Corner Shop", "Hiša kave")

    page = page_text(settings_page(admin_client))
    confirm = page_text(
        admin_client.get("/suggestions/resuggest/", HTTP_HX_REQUEST="true").content.decode()
    )

    assert "Ask again about 2 suggestions" in page
    assert confirm.startswith(
        "Ask the Categorizers again about the 2 suggestions in the Review queue? They're cleared and come back as "
        "the Categorizers answer. Outcomes already set stay."
    )
    assert Transaction.objects.filter(confidence__isnull=False).count() == 2


def ask_again_card(client):
    """The Ask again card's HTML on the Suggestions page."""
    page = settings_page(client)
    return page[
        page.index('aria-labelledby="again-heading"') : page.index(
            "</section>", page.index("again-heading")
        )
    ]


def revoke_every_token():
    for token in categorizers.active():
        categorizers.revoke(token.pk)


def is_disabled(card):
    """Whether the card's Ask again is a disabled button, labelled without a count, tied to its reason."""
    return bool(
        re.search(
            r'<button[^>]*disabled aria-describedby="again-reason">.*Ask again</button>', card
        )
        and 'id="again-reason"' in card
    )


def test_with_no_categorizer_connected_ask_again_is_disabled_even_with_suggestions(admin_client):
    suggest("Corner Shop", "Hiša kave")
    revoke_every_token()

    card = ask_again_card(admin_client)

    assert is_disabled(card)
    assert "Ask again about" not in page_text(card)
    assert "No Categorizer is connected. Connect one on the Categorizers page" in page_text(card)
    assert 'href="/categorizers/"' in card


def test_with_no_categorizer_connected_asking_again_clears_nothing(admin_client):
    suggest("Corner Shop", "Hiša kave")
    revoke_every_token()

    confirm = admin_client.get("/suggestions/resuggest/", HTTP_HX_REQUEST="true")
    page = admin_client.get("/suggestions/resuggest/")
    response = admin_client.post("/suggestions/resuggest/")

    assert confirm.content == b""
    assert page.status_code == response.status_code == 302
    assert Transaction.objects.filter(confidence__isnull=False).count() == 2


def test_with_the_review_queue_empty_ask_again_is_disabled(admin_client, connected):
    card = ask_again_card(admin_client)

    assert is_disabled(card)
    assert "The Review queue is empty, so there's nothing to ask about again." in page_text(card)


@pytest.mark.parametrize(
    "descriptions, reason",
    [
        (["Corner Shop"], "None of the 1 Transaction in the Review queue has a suggestion yet."),
        (
            ["Corner Shop", "Hiša kave"],
            "None of the 2 Transactions in the Review queue has a suggestion yet.",
        ),
    ],
)
def test_with_no_suggestion_in_the_review_queue_yet_ask_again_is_disabled(
    admin_client, connected, descriptions, reason
):
    for description in descriptions:
        make_transaction(description)

    card = ask_again_card(admin_client)

    assert is_disabled(card)
    assert reason in page_text(card)


def test_ask_again_says_when_to_use_it(admin_client):
    assert (
        "Changed a Categorizer's model or prompt? Ask again throws away the suggestions waiting in the Review "
        "queue, and the Categorizers suggest those Transactions afresh. Transactions already categorized aren't "
        "touched." in page_text(ask_again_card(admin_client))
    )
