"""Transfers: recognised at import by IBAN, paired across Accounts in either import order."""

import re
from pathlib import Path

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile

from ledger.models import Transaction
from tests.conftest import (
    make_account,
    outcome_shown,
    review_queue_count,
    subcategory_id,
    transaction_id,
)
from tests.test_duplicates import revolut_csv

pytestmark = pytest.mark.django_db

SPARKASSE = (Path(__file__).parent / "fixtures" / "sparkasse.txt").read_text()
SPARKASSE_IBAN = "SI56340001234567864"
# The Sparkasse fixture pays 1500.00 to this IBAN on 10 Sep 2026, as "Ana Novak".
REVOLUT_IBAN = "LT633250001234567890"


@pytest.fixture(autouse=True)
def pdf_text(monkeypatch):
    """An uploaded "PDF" is the fixture's extracted text itself."""
    monkeypatch.setattr("ledger.parsers.pdf_text.extract_text", lambda content: content.decode())


@pytest.fixture
def sparkasse(member):
    return make_account("Ana's Sparkasse", "sparkasse_si", member, [SPARKASSE_IBAN])


@pytest.fixture
def revolut(member):
    return make_account("Ana's Revolut", "revolut", member, [REVOLUT_IBAN])


def import_sparkasse(client):
    return client.post(
        "/import/", {"file": SimpleUploadedFile("izpisek.pdf", SPARKASSE.encode())}
    ).content.decode()


def import_revolut(client, account, rows, filename="revolut.csv"):
    return client.post(
        "/import/",
        {
            "file": SimpleUploadedFile(filename, revolut_csv("100", rows)),
            "account": str(account.pk),
        },
    ).content.decode()


def counterpart_of(description):
    """The description of the paired other side of the Transaction described `description`, if any."""
    counterpart = Transaction.objects.get(description=description).counterpart
    return counterpart and counterpart.description


def transactions_page(client):
    return client.get("/transactions/").content.decode()


def test_a_payment_to_a_household_iban_is_a_one_sided_transfer(logged_in_client, sparkasse, member):
    make_account("Ana's savings", "other", member, [REVOLUT_IBAN])

    summary = import_sparkasse(logged_in_client)

    assert "1 Transfer recognised: 0 paired, 1 one-sided" in summary
    page = transactions_page(logged_in_client)
    assert outcome_shown(page, "Ana Novak") == "Transfer"
    assert outcome_shown(page, "DARS d.d.") == "Awaiting review"


def payment_from_ana(day="2026-09-11"):
    """The Revolut side of the Sparkasse fixture's 1500.00 to Ana's Revolut, with no IBAN on it."""
    return [(day, "Payment from Ana Novak", "1500")]


def test_the_other_side_imported_later_is_paired(logged_in_client, sparkasse, revolut):
    import_sparkasse(logged_in_client)

    summary = import_revolut(logged_in_client, revolut, payment_from_ana())

    assert "1 Transfer recognised: 1 paired, 0 one-sided" in summary
    page = transactions_page(logged_in_client)
    assert outcome_shown(page, "Payment from Ana Novak") == "Transfer"
    assert outcome_shown(page, "Ana Novak") == "Transfer"
    assert ">paired<" in page


def test_a_categorized_side_imported_first_is_converted_when_its_counterpart_arrives(
    logged_in_client, sparkasse, revolut
):
    logged_in_client.post(
        "/rules/new/",
        {
            "description_contains": "payment from",
            "outcome": subcategory_id("Income", "Other income"),
        },
    )
    import_revolut(logged_in_client, revolut, payment_from_ana())
    assert outcome_shown(transactions_page(logged_in_client), "Payment from Ana Novak") == (
        "Income → Other income"
    )

    summary = import_sparkasse(logged_in_client)

    assert "1 Transfer recognised: 1 paired, 0 one-sided" in summary
    assert "1 categorized Transaction converted to a Transfer" in summary
    assert (
        outcome_shown(transactions_page(logged_in_client), "Payment from Ana Novak") == "Transfer"
    )


def review_queue(client):
    return client.get("/review/").content.decode()


def pairing_options(page, description):
    """The candidate counterparts offered in the outcome dropdown of the row described `description`."""
    row = re.search(
        rf"<tr[^>]*>(?:(?!</tr>).)*>{re.escape(description)}<(?:(?!</tr>).)*</tr>", page, re.S
    )
    assert row, f"no row for {description!r}"
    return re.findall(r'<option value="pair-\d+">Pair with ([^<]*)</option>', row[0])


def set_outcome(client, description, outcome, **headers):
    return client.post(
        f"/transactions/{transaction_id(description)}/outcome/", {"outcome": outcome}, **headers
    )


@pytest.fixture
def tie(logged_in_client, sparkasse, revolut):
    """The Sparkasse side of 10 Sep, with two Revolut candidates a day either side of it."""
    import_sparkasse(logged_in_client)
    return import_revolut(
        logged_in_client,
        revolut,
        [
            ("2026-09-09", "Top-up by card", "1500"),
            ("2026-09-11", "Payment from Ana Novak", "1500"),
        ],
    )


def test_a_tie_between_candidates_goes_to_the_review_queue_with_the_candidates(
    logged_in_client, tie
):
    assert "1 Transfer with several possible counterparts waits in the Review queue" in tie
    page = review_queue(logged_in_client)
    assert outcome_shown(page, "Ana Novak") == "Pick the other side"
    assert pairing_options(page, "Ana Novak") == [
        "9 Sep 2026 · Ana&#x27;s Revolut · Top-up by card",
        "11 Sep 2026 · Ana&#x27;s Revolut · Payment from Ana Novak",
    ]
    assert pairing_options(page, "Top-up by card") == []
    # The side, both still unresolved candidates, and the 11 other Sparkasse rows.
    assert review_queue_count(page) == 14


def test_ambiguous_sides_are_listed_oldest_first_with_the_rest_of_the_queue(logged_in_client, tie):
    page = review_queue(logged_in_client)

    positions = [page.index(f">{d}<") for d in ("MARKO K", "Top-up by card", "Ana Novak")]
    assert positions == sorted(positions)


def test_picking_a_candidate_pairs_it_and_leaves_the_other_alone(logged_in_client, tie):
    response = set_outcome(
        logged_in_client,
        "Ana Novak",
        f"pair-{transaction_id('Payment from Ana Novak')}",
        HTTP_HX_REQUEST="true",
    )

    assert outcome_shown(response.content.decode(), "Ana Novak") == "Transfer"
    page = review_queue(logged_in_client)
    assert ">Ana Novak<" not in page
    assert ">Payment from Ana Novak<" not in page
    assert outcome_shown(page, "Top-up by card") == "Awaiting review"
    assert counterpart_of("Ana Novak") == "Payment from Ana Novak"


def test_an_ambiguous_side_can_be_kept_one_sided(logged_in_client, tie):
    set_outcome(logged_in_client, "Ana Novak", "transfer")

    assert ">Ana Novak<" not in review_queue(logged_in_client)
    assert outcome_shown(transactions_page(logged_in_client), "Ana Novak") == "Transfer"
    assert counterpart_of("Ana Novak") is None


def test_an_ambiguous_side_can_be_categorized_instead(logged_in_client, tie):
    set_outcome(logged_in_client, "Ana Novak", subcategory_id("Other", "Payments to people"))

    assert ">Ana Novak<" not in review_queue(logged_in_client)
    page = transactions_page(logged_in_client)
    assert outcome_shown(page, "Ana Novak") == "Other → Payments to people"


def test_only_a_listed_candidate_can_be_picked(logged_in_client, tie):
    response = set_outcome(
        logged_in_client, "Ana Novak", f"pair-{transaction_id('Pozitivne obresti')}"
    )

    assert response.status_code == 400
    assert outcome_shown(review_queue(logged_in_client), "Ana Novak") == "Pick the other side"


def test_only_an_ambiguous_side_offers_a_pick(logged_in_client, tie):
    response = set_outcome(
        logged_in_client, "Top-up by card", f"pair-{transaction_id('Ana Novak')}"
    )

    assert response.status_code == 400


def test_the_closest_date_wins(logged_in_client, sparkasse, revolut):
    import_sparkasse(logged_in_client)

    import_revolut(
        logged_in_client,
        revolut,
        [
            ("2026-09-08", "Top-up by card", "1500"),
            ("2026-09-11", "Payment from Ana Novak", "1500"),
        ],
    )

    page = transactions_page(logged_in_client)
    assert outcome_shown(page, "Payment from Ana Novak") == "Transfer"
    assert outcome_shown(page, "Top-up by card") == "Awaiting review"


def test_a_counterpart_more_than_three_days_away_is_not_paired(
    logged_in_client, sparkasse, revolut
):
    import_sparkasse(logged_in_client)

    summary = import_revolut(logged_in_client, revolut, payment_from_ana("2026-09-14"))

    assert "0 Transfers recognised: 0 paired, 0 one-sided" in summary
    assert outcome_shown(transactions_page(logged_in_client), "Payment from Ana Novak") == (
        "Awaiting review"
    )


def test_a_manually_categorized_transaction_is_never_converted(
    logged_in_client, sparkasse, revolut
):
    import_revolut(logged_in_client, revolut, payment_from_ana())
    gifts = subcategory_id("Income", "Gifts received")
    logged_in_client.post(
        f"/transactions/{transaction_id('Payment from Ana Novak')}/outcome/", {"outcome": gifts}
    )

    summary = import_sparkasse(logged_in_client)

    assert "1 Transfer recognised: 0 paired, 1 one-sided" in summary
    page = transactions_page(logged_in_client)
    assert outcome_shown(page, "Payment from Ana Novak") == "Income → Gifts received"


def test_a_side_marked_as_a_transfer_by_hand_is_paired_and_stays_manual(
    logged_in_client, sparkasse, revolut
):
    import_revolut(logged_in_client, revolut, payment_from_ana())
    logged_in_client.post(
        f"/transactions/{transaction_id('Payment from Ana Novak')}/outcome/",
        {"outcome": "transfer"},
    )

    summary = import_sparkasse(logged_in_client)

    assert "1 Transfer recognised: 1 paired, 0 one-sided" in summary
    assert counterpart_of("Payment from Ana Novak") == "Ana Novak"
    assert Transaction.objects.get(description="Payment from Ana Novak").source == "manual"


def test_unmarking_one_side_by_hand_leaves_the_other_one_sided(
    logged_in_client, sparkasse, revolut
):
    import_sparkasse(logged_in_client)
    import_revolut(logged_in_client, revolut, payment_from_ana())

    logged_in_client.post(
        f"/transactions/{transaction_id('Payment from Ana Novak')}/outcome/",
        {"outcome": subcategory_id("Income", "Gifts received")},
        HTTP_HX_REQUEST="true",
    )

    page = transactions_page(logged_in_client)
    assert outcome_shown(page, "Payment from Ana Novak") == "Income → Gifts received"
    assert outcome_shown(page, "Ana Novak") == "Transfer"
    assert counterpart_of("Payment from Ana Novak") is None
    assert counterpart_of("Ana Novak") is None


def test_deleting_the_statement_of_one_side_leaves_the_other_one_sided(
    logged_in_client, sparkasse, revolut
):
    import_sparkasse(logged_in_client)
    import_revolut(logged_in_client, revolut, payment_from_ana())

    revolut_statement = revolut.statements.get()
    logged_in_client.post(f"/statements/{revolut_statement.pk}/delete/")

    assert outcome_shown(transactions_page(logged_in_client), "Ana Novak") == "Transfer"
    assert counterpart_of("Ana Novak") is None


def test_a_transfer_marked_by_a_rule_is_paired(logged_in_client, sparkasse, member):
    # With its IBAN unknown, the Sparkasse side is no Transfer, and the Revolut side only by a Rule.
    revolut = make_account("Ana's Revolut", "revolut", member)
    import_sparkasse(logged_in_client)
    logged_in_client.post(
        "/rules/new/", {"description_contains": "payment from", "outcome": "transfer"}
    )

    summary = import_revolut(logged_in_client, revolut, payment_from_ana())

    assert "1 Transfer recognised: 1 paired, 0 one-sided" in summary
    assert "converted" not in summary  # the Sparkasse side was unresolved, not categorized
    assert Transaction.objects.get(description="Payment from Ana Novak").source == "rule"
    assert counterpart_of("Payment from Ana Novak") == "Ana Novak"


@pytest.fixture
def savings_moves(logged_in_client, member):
    """Two Revolut Accounts with no IBANs, whose "Savings" rows a Rule marks as Transfers."""
    logged_in_client.post("/rules/new/", {"description_contains": "savings", "outcome": "transfer"})
    return make_account("Ana's Revolut", "revolut", member), make_account(
        "Bor's Revolut", "revolut", member
    )


def test_the_closest_pair_wins_whichever_side_comes_first(logged_in_client, savings_moves):
    ana, bor = savings_moves
    import_revolut(
        logged_in_client,
        ana,
        [("2026-09-01", "Savings early", "-50"), ("2026-09-03", "Savings late", "-50")],
    )

    import_revolut(logged_in_client, bor, [("2026-09-03", "Savings in", "50")])

    assert counterpart_of("Savings in") == "Savings late"
    assert counterpart_of("Savings early") is None


def test_two_sides_equally_close_to_one_candidate_go_to_the_review_queue(logged_in_client, member):
    ana = make_account("Ana's Revolut", "revolut", member)
    logged_in_client.post(
        "/rules/new/",
        {"description_contains": "savings", "account": ana.pk, "outcome": "transfer"},
    )
    import_revolut(
        logged_in_client,
        ana,
        [("2026-09-01", "Savings early", "-50"), ("2026-09-05", "Savings late", "-50")],
    )

    summary = import_revolut(
        logged_in_client,
        make_account("Bor's Revolut", "revolut", member),
        [("2026-09-03", "From Ana", "50")],
    )

    assert "2 Transfers with several possible counterparts wait in the Review queue" in summary
    page = review_queue(logged_in_client)
    assert outcome_shown(page, "Savings early") == "Pick the other side"
    assert outcome_shown(page, "Savings late") == "Pick the other side"
    assert pairing_options(page, "Savings early") == ["3 Sep 2026 · Bor&#x27;s Revolut · From Ana"]
    assert counterpart_of("From Ana") is None


def test_a_closer_counterpart_imported_later_settles_a_tie(logged_in_client, savings_moves, member):
    ana, bor = savings_moves
    import_revolut(logged_in_client, ana, [("2026-09-03", "Savings out", "-50")])
    import_revolut(
        logged_in_client,
        bor,
        [("2026-09-01", "From Ana early", "50"), ("2026-09-05", "From Ana late", "50")],
    )
    assert outcome_shown(review_queue(logged_in_client), "Savings out") == "Pick the other side"

    import_revolut(
        logged_in_client,
        make_account("Cene's Revolut", "revolut", member),
        [("2026-09-03", "From Ana", "50")],
    )

    assert ">Savings out<" not in review_queue(logged_in_client)
    assert counterpart_of("Savings out") == "From Ana"


def test_a_payment_to_a_household_iban_pairs_only_within_that_account(
    logged_in_client, sparkasse, member
):
    make_account("Ana's savings", "other", member, [REVOLUT_IBAN])
    import_sparkasse(logged_in_client)

    import_revolut(
        logged_in_client, make_account("Ana's Revolut", "revolut", member), payment_from_ana()
    )

    assert outcome_shown(transactions_page(logged_in_client), "Payment from Ana Novak") == (
        "Awaiting review"
    )
    assert counterpart_of("Ana Novak") is None


def test_a_payment_to_another_members_account_is_a_transfer(
    logged_in_client, sparkasse, django_user_model
):
    bor = django_user_model.objects.create_user(username="bor", password="x")
    make_account("Bor's Revolut", "revolut", bor, [REVOLUT_IBAN])

    summary = import_sparkasse(logged_in_client)

    assert "1 Transfer recognised: 0 paired, 1 one-sided" in summary


def test_duplicates_of_a_paired_side_are_not_counted_again(logged_in_client, sparkasse, revolut):
    import_sparkasse(logged_in_client)
    import_revolut(logged_in_client, revolut, payment_from_ana())

    summary = import_revolut(
        logged_in_client,
        revolut,
        [*payment_from_ana(), ("2026-09-12", "Bakery", "-3.20")],
        filename="overlap.csv",
    )

    assert "1 Duplicate skipped" in summary
    assert "0 Transfers recognised: 0 paired, 0 one-sided" in summary
    assert counterpart_of("Ana Novak") == "Payment from Ana Novak"
