import html
import json
import re
from datetime import date

import pytest

from ledger.models import Source, Subcategory, Transaction
from tests.conftest import make_account, review_queue_count, transaction_id
from tests.test_import import upload

pytestmark = pytest.mark.django_db

HX = {"HTTP_HX_REQUEST": "true"}


def sub(category, name):
    return Subcategory.objects.get(category__name=category, name=name)


@pytest.fixture
def queue(member):
    """Three Bolt.eu rides across two Accounts with a suggestion, a café without one, and Bolt.eu decided by hand
    last time as something else."""
    revolut = make_account("Ana's Revolut", "revolut", member)
    n26 = make_account("Joint N26", "n26", member)
    transport = sub("Transport", "Public transport & car sharing")
    rides = [
        Transaction.objects.create(
            account=account,
            date=day,
            amount=amount,
            description="Bolt.eu",
            counterparty_name="Bolt Operations OÜ",
            suggested_subcategory=transport,
            confidence=0.78,
        )
        for account, day, amount in [
            (revolut, date(2026, 9, 24), "-11.02"),
            (n26, date(2026, 9, 26), "-8.40"),
            (revolut, date(2026, 10, 2), "-14.90"),
        ]
    ]
    Transaction.objects.create(
        account=revolut, date=date(2026, 9, 30), amount="-7.80", description="Kavarna Zvezda"
    )
    Transaction.objects.create(
        account=revolut,
        date=date(2026, 8, 14),
        amount="-12.00",
        description="Bolt.eu",
        subcategory=sub("Leisure", "Hobbies & sport"),
        source=Source.MANUAL,
    )
    return [t.pk for t in rides]


def page(client, **params):
    return html.unescape(client.get("/review/", params).content.decode())


def groups_listed(content):
    return [
        " ".join(re.sub(r"<[^>]+>", " ", g).split())
        for g in re.findall(
            r'<span class="g-desc">(.*?)</span>\s*<span class="g-amt', content, re.S
        )
    ]


def words(content):
    """The text a page shows, tags left out."""
    return " ".join(re.sub(r"<[^>]+>", " ", content).split())


def detail_heading(content):
    found = re.search(r'<h2 id="group-heading"[^>]*>([^<]*)</h2>', content)
    return found[1] if found else None


def decide(client, pks, outcome, **headers):
    return client.post("/review/decide/", {"transaction": pks, "outcome": outcome}, **headers)


def announced(response):
    return json.loads(response["HX-Trigger"])["announce"]


def test_the_queue_lists_groups_of_one_description_newest_first(logged_in_client, queue):
    content = page(logged_in_client)

    assert groups_listed(content) == ["Bolt.eu ×3", "Kavarna Zvezda"]
    assert "4 Transactions in 2 groups still need an outcome" in content
    assert "<title>Review queue (4) · Pursegraph</title>" in content
    assert "Transport › Public transport & car sharing" in content
    assert "78 % sure" in content
    assert "No suggestion" in content
    # The newest group is open.
    assert detail_heading(content) == "Bolt.eu"


def test_a_group_shows_its_transactions_and_what_was_used_last_time(logged_in_client, queue):
    content = page(logged_in_client, group=queue[0])

    assert detail_heading(content) == "Bolt.eu"
    assert "Bolt Operations OÜ" in content
    assert "3 Transactions with this description" in content
    assert content.count('<span class="pill">') == 3
    assert "Joint N26" in content
    assert "Leisure › Hobbies & sport 14 Aug 2026 · by hand" in words(content)
    assert "The suggestion differs from what was used last time." in content
    assert "Accept for all 3" in content
    # Used last time comes first among the other outcomes, as it differs.
    assert content.index("Used last time") < content.index(">Category<")
    # Most used leaves out the outcome already offered as used last time.
    assert "Most used" not in content


def test_a_new_description_says_it_is_seen_for_the_first_time(logged_in_client, queue):
    content = page(logged_in_client, group=transaction_id("Kavarna Zvezda"))

    assert detail_heading(content) == "Kavarna Zvezda"
    assert "First time this description is seen." in content
    assert "Choose an outcome" in content
    assert "Accept" not in content.split('class="decide')[1]


def test_accept_decides_the_whole_group(logged_in_client, queue):
    transport = sub("Transport", "Public transport & car sharing")

    response = decide(logged_in_client, queue, transport.pk, **HX)

    assert response.status_code == 200
    rides = Transaction.objects.filter(pk__in=queue)
    assert {(t.subcategory, t.source) for t in rides} == {(transport, Source.MANUAL)}
    assert announced(response) == (
        "Saved 3 × Bolt.eu as Transport › Public transport & car sharing. 1 left to review."
    )
    content = html.unescape(response.content.decode())
    assert "Saved all 3 as Transport › Public transport & car sharing" in content
    assert ">Undo</button>" in content
    assert 'Make a Rule for "Bolt.eu"' in content
    assert f'href="/transactions/?decided={",".join(map(str, queue))}"' in content
    assert "Next: Kavarna Zvezda" in content
    assert groups_listed(content) == ["Kavarna Zvezda"]
    assert review_queue_count(content) == 1
    assert "<title>Review queue (1) · Pursegraph</title>" in content


def test_a_single_transaction_saved_is_not_counted(logged_in_client, queue):
    response = decide(logged_in_client, [transaction_id("Kavarna Zvezda")], "transfer", **HX)

    assert announced(response) == "Saved Kavarna Zvezda as Transfer. 3 left to review."
    content = response.content.decode()
    assert "Saved as Transfer" in content
    assert "See them in Transactions" not in content


def test_a_transaction_decided_since_is_left_alone(logged_in_client, queue):
    groceries = sub("Food", "Groceries")
    Transaction.objects.get(pk=queue[0]).set_outcome(groceries, source=Source.MANUAL)

    decide(logged_in_client, queue, "transfer", **HX)

    assert Transaction.objects.get(pk=queue[0]).subcategory == groceries
    assert Transaction.objects.filter(pk__in=queue[1:], is_transfer=True).count() == 2


def test_a_group_decided_elsewhere_meanwhile_is_not_said_to_be_saved(logged_in_client, queue):
    for pk in queue:
        Transaction.objects.get(pk=pk).set_outcome(None, source=Source.MANUAL)

    response = decide(logged_in_client, queue, sub("Food", "Groceries").pk, **HX)

    assert announced(response) == "Bolt.eu was already decided. 1 left to review."
    assert Transaction.objects.filter(pk__in=queue, is_transfer=True).count() == 3
    assert detail_heading(html.unescape(response.content.decode())) == "Kavarna Zvezda"


def test_show_resolved_says_what_it_changed(logged_in_client, queue):
    shown = logged_in_client.get("/review/", {"at": queue[0], "resolved": 1}, **HX)
    hidden = logged_in_client.get("/review/", {"at": queue[0]}, **HX)

    assert announced(shown) == "Resolved groups shown."
    assert announced(hidden) == "Resolved groups hidden."


def test_an_unknown_outcome_changes_nothing(logged_in_client, queue):
    response = decide(logged_in_client, queue, "nonsense", **HX)

    assert response.status_code == 400
    assert Transaction.objects.in_review_queue().count() == 4


def test_without_htmx_a_decision_goes_back_to_the_group(logged_in_client, queue):
    response = decide(logged_in_client, queue, "transfer")

    assert response.status_code == 302
    assert response["Location"] == f"/review/?group={queue[-1]}"
    content = page(logged_in_client, group=queue[-1])
    assert "Saved all 3 as Transfer" in content


def test_undo_puts_the_whole_group_back(logged_in_client, queue):
    decide(logged_in_client, queue, "transfer", **HX)

    response = logged_in_client.post("/review/undo/", {"transaction": queue}, **HX)

    assert response.status_code == 200
    assert Transaction.objects.in_review_queue().count() == 4
    assert announced(response) == "Undone. Bolt.eu is back in the Review queue. 4 left to review."
    content = html.unescape(response.content.decode())
    assert groups_listed(content) == ["Bolt.eu ×3", "Kavarna Zvezda"]
    assert detail_heading(content) == "Bolt.eu"


def test_undo_is_refused_without_a_decision(logged_in_client, queue):
    response = logged_in_client.post("/review/undo/", {"transaction": queue}, **HX)

    assert response.status_code == 400


def test_show_resolved_keeps_the_groups_decided_just_now(logged_in_client, queue):
    page(logged_in_client)  # arriving starts a review
    decide(logged_in_client, queue, "transfer", **HX)

    hidden = page(logged_in_client, at=queue[-1])
    shown = page(logged_in_client, at=queue[-1], resolved=1)

    assert groups_listed(hidden) == ["Kavarna Zvezda"]
    assert "Show resolved (1)" in words(hidden)
    assert groups_listed(shown) == ["Bolt.eu ×3", "Kavarna Zvezda"]
    assert re.search(r'<li class="decided">.*?Bolt\.eu.*?Transfer', shown, re.S)
    # Arriving again starts a new review.
    assert "Show resolved (1)" not in words(page(logged_in_client))


@pytest.fixture
def covered(member, monkeypatch):
    """Ana's Revolut has a Statement for September 2026, which is over."""
    from ledger.models import Statement

    monkeypatch.setattr("dashboard.periods.today", lambda: date(2026, 10, 17))
    account = make_account("Ana's Revolut", "revolut", member)
    Statement.objects.create(
        account=account,
        format="csv",
        period_start=date(2026, 9, 1),
        period_end=date(2026, 9, 30),
        opening_balance=0,
        closing_balance=0,
        imported_by=member,
        sha256="0" * 64,
    )
    return Transaction.objects.create(
        account=account, date=date(2026, 9, 9), amount="-5", description="Spar"
    )


def test_deciding_the_last_group_clears_the_queue_and_names_the_month_completed(
    logged_in_client, covered
):
    page(logged_in_client)

    response = decide(logged_in_client, [covered.pk], sub("Food", "Groceries").pk, **HX)

    content = html.unescape(response.content.decode())
    assert "Queue clear · See September on the Dashboard" in content
    assert 'href="/?period=2026-09"' in content
    assert announced(response).endswith("Nothing left to review.")

    clear = page(logged_in_client, at=covered.pk)
    assert "Queue clear" in clear
    assert (
        "Every Transaction has an outcome, 1 of them decided just now. "
        "September 2026 is now complete."
    ) in clear
    assert "See September on the Dashboard" in clear
    assert "October so far" in clear


def test_an_empty_queue_on_arrival_is_clear_without_decided_just_now(logged_in_client, covered):
    covered.set_outcome(None, source=Source.MANUAL)

    content = page(logged_in_client)

    assert "Queue clear" in content
    assert "Every Transaction has an outcome." in content
    assert "decided just now" not in content
    assert "<title>Review queue · Pursegraph</title>" in content


def test_see_them_in_transactions_lists_the_transactions_decided(logged_in_client, queue):
    decide(logged_in_client, queue, "transfer", **HX)

    content = html.unescape(
        logged_in_client.get(
            "/transactions/", {"decided": ",".join(map(str, queue))}
        ).content.decode()
    )

    assert content.count('class="desc">Bolt.eu<') == 3
    assert "Kavarna Zvezda" not in content
    assert "Decided just now · 3" in content
    assert '<input type="hidden" name="decided"' in content


def test_there_is_no_queue_wide_bulk_accept(logged_in_client, queue):
    assert logged_in_client.post("/review/accept/", {"accept": []}).status_code == 404


def test_the_sidebar_shows_the_review_queue_count(logged_in_client):
    assert review_queue_count(logged_in_client.get("/").content.decode()) == 0
    upload(logged_in_client)
    assert review_queue_count(logged_in_client.get("/").content.decode()) == 6

    logged_in_client.post(
        f"/transactions/{transaction_id('Corner Shop')}/outcome/", {"outcome": "transfer"}
    )

    assert review_queue_count(logged_in_client.get("/transactions/").content.decode()) == 5
