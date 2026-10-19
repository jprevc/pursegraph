import re
from decimal import Decimal

import pytest

from ledger.models import Account, Category, Rule, Source, Transaction
from tests.conftest import make_account, outcome_shown, subcategory_id, transaction_id
from tests.test_import import upload

pytestmark = pytest.mark.django_db


def make_rule(client, outcome, **conditions):
    """Creates a Rule through the Rules page and returns the response."""
    data = {"description_contains": "", "counterparty_iban": "", "direction": "", "account": ""}
    return client.post("/rules/new/", {**data, **conditions, "outcome": outcome})


def rule_order(client):
    """The Rules page's Rules, top first, by their description-contains condition."""
    page = client.get("/rules/").content.decode()
    return re.findall(r'<td class="contains">([^<]*)</td>', page)


def rule_id(description_contains):
    return Rule.objects.get(description_contains=description_contains).pk


def groceries():
    return subcategory_id("Food", "Groceries")


def make_transaction(description, amount="-10.00", *, counterparty_iban="", **outcome):
    account = Account.objects.first() or make_account("Cash", "other")
    return Transaction.objects.create(
        account=account,
        date="2026-06-01",
        amount=Decimal(amount),
        description=description,
        counterparty_iban=counterparty_iban,
        **outcome,
    )


def test_rules_categorize_matching_rows_at_import(logged_in_client):
    make_rule(logged_in_client, groceries(), description_contains="mercator")

    summary = upload(logged_in_client).content.decode()

    assert "1 Transaction categorized by Rules" in summary
    page = logged_in_client.get("/transactions/").content.decode()
    assert outcome_shown(page, "Mercator Žalec") == "Food → Groceries"
    mercator = Transaction.objects.get(description="Mercator Žalec")
    assert mercator.source == Source.RULE
    assert mercator.rule_id == rule_id("mercator")


def test_description_contains_ignores_case_and_accents(logged_in_client):
    make_rule(logged_in_client, groceries(), description_contains="MERCATOR ZALEC")
    make_rule(logged_in_client, subcategory_id("Leisure", "Other"), description_contains="hisa")

    summary = upload(logged_in_client).content.decode()

    assert "2 Transactions categorized by Rules" in summary
    page = logged_in_client.get("/transactions/").content.decode()
    assert outcome_shown(page, "Mercator Žalec") == "Food → Groceries"
    assert outcome_shown(page, "Hiša kave") == "Leisure → Other"


def test_the_first_matching_rule_wins(logged_in_client):
    make_rule(logged_in_client, groceries(), description_contains="corner")
    make_rule(logged_in_client, "transfer", description_contains="shop")  # goes to the top

    upload(logged_in_client)

    page = logged_in_client.get("/transactions/").content.decode()
    assert outcome_shown(page, "Corner Shop") == "Transfer"


def test_reordering_changes_which_rule_wins(logged_in_client):
    make_rule(logged_in_client, groceries(), description_contains="corner")
    make_rule(logged_in_client, "transfer", description_contains="shop")
    assert rule_order(logged_in_client) == ["shop", "corner"]

    response = logged_in_client.post(
        "/rules/reorder/", {"rule": [rule_id("corner"), rule_id("shop")]}
    )

    assert response.status_code == 302
    assert rule_order(logged_in_client) == ["corner", "shop"]
    upload(logged_in_client)
    page = logged_in_client.get("/transactions/").content.decode()
    assert outcome_shown(page, "Corner Shop") == "Food → Groceries"


def test_moving_a_rule_down_without_dragging(logged_in_client):
    make_rule(logged_in_client, groceries(), description_contains="corner")
    make_rule(logged_in_client, "transfer", description_contains="shop")

    logged_in_client.post(f"/rules/{rule_id('shop')}/move/", {"direction": "down"})

    assert rule_order(logged_in_client) == ["corner", "shop"]


def test_every_condition_must_hold(logged_in_client, member):
    other = make_account("Other Revolut", "revolut", member)
    make_rule(logged_in_client, groceries(), description_contains="o", direction="in")
    make_rule(logged_in_client, "transfer", description_contains="o", account=other.pk)

    upload(logged_in_client)

    page = logged_in_client.get("/transactions/").content.decode()
    assert outcome_shown(page, "Payment from Ana Novak") == "Food → Groceries"  # in
    assert outcome_shown(page, "Corner Shop") == "Awaiting review"  # out, and another Account


def test_rules_leave_parser_outcomes_alone_at_import(logged_in_client):
    make_rule(logged_in_client, groceries(), description_contains="corner")

    upload(logged_in_client)

    page = logged_in_client.get("/transactions/").content.decode()
    assert outcome_shown(page, "Fee: Corner Shop") == "Finance → Bank fees"
    assert outcome_shown(page, "Corner Shop") == "Food → Groceries"


def test_counterparty_iban_rule_matches_with_spaces_ignored(logged_in_client):
    make_rule(logged_in_client, "transfer", counterparty_iban="si56 3400 0123 4567 864")
    match = make_transaction("Rent", counterparty_iban="SI56340001234567864")
    other = make_transaction("Rent", counterparty_iban="SI56340001234567000")

    logged_in_client.post(f"/rules/{Rule.objects.get().pk}/apply/")

    match.refresh_from_db()
    other.refresh_from_db()
    assert match.is_transfer and match.source == Source.RULE
    assert not other.is_transfer and other.source == ""


def test_a_rule_needs_a_condition(logged_in_client):
    response = make_rule(logged_in_client, groceries())

    assert response.status_code == 200
    assert "Give the Rule at least one condition." in response.content.decode()
    assert not Rule.objects.exists()


def test_the_rules_page_lists_rules_for_any_member(logged_in_client):
    make_rule(logged_in_client, groceries(), description_contains="mercator", direction="out")

    page = logged_in_client.get("/rules/").content.decode()

    assert "mercator" in page
    assert "Food → Groceries" in page
    assert 'href="/rules/"' in page  # in the sidebar


def test_a_rule_can_be_edited(logged_in_client):
    make_rule(logged_in_client, groceries(), description_contains="mercator")
    pk = rule_id("mercator")

    form = logged_in_client.get(f"/rules/{pk}/edit/").content.decode()
    assert 'value="mercator"' in form
    logged_in_client.post(
        f"/rules/{pk}/edit/",
        {"description_contains": "spar", "direction": "", "account": "", "outcome": "transfer"},
    )

    rule = Rule.objects.get(pk=pk)
    assert rule.description_contains == "spar"
    assert rule.subcategory is None


def test_a_rule_can_be_deleted(logged_in_client):
    make_rule(logged_in_client, groceries(), description_contains="mercator")
    upload(logged_in_client)
    mercator = Transaction.objects.get(description="Mercator Žalec")

    logged_in_client.post(f"/rules/{rule_id('mercator')}/delete/")

    assert not Rule.objects.exists()
    mercator.refresh_from_db()
    assert mercator.subcategory_id == groceries()  # the outcome stays
    assert mercator.rule is None


def test_make_a_rule_is_offered_after_a_correction(logged_in_client):
    upload(logged_in_client)
    pk = transaction_id("Corner Shop")

    row = logged_in_client.post(
        f"/transactions/{pk}/outcome/", {"outcome": groceries()}, HTTP_HX_REQUEST="true"
    ).content.decode()

    assert f'href="/rules/new/?transaction={pk}"' in row


def test_make_a_rule_prefills_description_and_outcome(logged_in_client):
    upload(logged_in_client)
    pk = transaction_id("Corner Shop")
    logged_in_client.post(f"/transactions/{pk}/outcome/", {"outcome": groceries()})

    form = logged_in_client.get(f"/rules/new/?transaction={pk}").content.decode()

    assert re.search(r'name="description_contains"[^>]*value="Corner Shop"', form)
    assert re.search(rf'<option value="{groceries()}" selected>', form)


def test_make_a_rule_prefills_the_iban_when_there_is_one(logged_in_client):
    t = make_transaction("SEPA payment 123", counterparty_iban="SI56340001234567864")
    t.set_outcome(None, source=Source.MANUAL)

    form = logged_in_client.get(f"/rules/new/?transaction={t.pk}").content.decode()

    assert re.search(r'name="counterparty_iban"[^>]*value="SI56340001234567864"', form)
    assert not re.search(r'name="description_contains"[^>]*value="', form)
    assert '<option value="transfer" selected>' in form


def test_a_new_rule_goes_to_the_top(logged_in_client):
    make_rule(logged_in_client, groceries(), description_contains="first")
    make_rule(logged_in_client, groceries(), description_contains="second")
    make_rule(logged_in_client, groceries(), description_contains="third")

    assert rule_order(logged_in_client) == ["third", "second", "first"]


def test_saving_a_rule_offers_to_apply_it_to_existing_transactions(logged_in_client):
    upload(logged_in_client)

    response = make_rule(logged_in_client, groceries(), description_contains="o")

    pk = Rule.objects.get().pk
    assert response.status_code == 302
    assert response.url == f"/rules/{pk}/apply/"
    offer = logged_in_client.get(response.url).content.decode()
    # Corner Shop, Payment from Ana Novak, To Janez Kranjc, Mercator; not the fees (parser)
    assert "4 existing Transactions match" in offer
    page = logged_in_client.get("/transactions/").content.decode()
    assert outcome_shown(page, "Corner Shop") == "Awaiting review"  # nothing applied yet


def test_saving_a_rule_nothing_matches_goes_back_to_the_rules(logged_in_client):
    response = make_rule(logged_in_client, groceries(), description_contains="nothing like it")

    assert response.url == "/rules/"


def test_applying_overwrites_only_unresolved_llm_and_rule_outcomes(logged_in_client):
    other = subcategory_id("Other", "Miscellaneous")
    kept = {
        source: make_transaction(f"Shop {source}", subcategory_id=other, source=source)
        for source in (Source.MANUAL, Source.IBAN, Source.PAIRING, Source.PARSER)
    }
    overwritten = [
        make_transaction("Shop unresolved"),
        make_transaction("Shop llm", subcategory_id=other, source=Source.LLM),
        make_transaction("Shop rule", subcategory_id=other, source=Source.RULE),
    ]
    make_rule(logged_in_client, groceries(), description_contains="shop")

    response = logged_in_client.post(f"/rules/{rule_id('shop')}/apply/")

    assert response.status_code == 302
    rule = Rule.objects.get()
    for t in overwritten:
        t.refresh_from_db()
        assert (t.subcategory_id, t.source, t.rule) == (groceries(), Source.RULE, rule)
    for source, t in kept.items():
        t.refresh_from_db()
        assert (t.subcategory_id, t.source, t.rule) == (other, source, None)


def test_applying_a_transfer_rule(logged_in_client):
    t = make_transaction("Savings", subcategory_id=groceries(), source=Source.LLM)
    make_rule(logged_in_client, "transfer", description_contains="savings")

    logged_in_client.post(f"/rules/{rule_id('savings')}/apply/")

    t.refresh_from_db()
    assert t.is_transfer and t.subcategory is None


def test_a_manual_change_clears_the_rule_link(logged_in_client):
    make_rule(logged_in_client, groceries(), description_contains="mercator")
    upload(logged_in_client)
    pk = transaction_id("Mercator Žalec")

    logged_in_client.post(f"/transactions/{pk}/outcome/", {"outcome": groceries()})

    t = Transaction.objects.get(pk=pk)
    assert t.source == Source.MANUAL
    assert t.rule is None


def test_deleting_a_subcategory_moves_its_rules_to_the_catch_all(logged_in_client, admin_client):
    make_rule(logged_in_client, groceries(), description_contains="mercator")

    admin_client.post(f"/subcategories/{groceries()}/delete/")

    assert Rule.objects.get().subcategory_id == subcategory_id("Food", "Other")


def test_make_a_rule_trims_a_long_description_to_fit(logged_in_client):
    t = make_transaction("x" * 300)
    t.set_outcome(None, source=Source.MANUAL)

    form = logged_in_client.get(f"/rules/new/?transaction={t.pk}").content.decode()

    assert re.search(r'name="description_contains"[^>]*value="x{200}"', form)


def test_a_category_with_rules_is_not_deleted(logged_in_client, admin_client):
    make_rule(logged_in_client, subcategory_id("Children", "Other"), description_contains="toys")

    response = admin_client.post(
        f"/categories/{Category.objects.get(name='Children').pk}/delete/", follow=True
    )

    assert "Rules still categorize into Children" in response.content.decode()
    assert Category.objects.filter(name="Children").exists()


def test_applying_a_subcategory_rule_unpairs_a_transfer(logged_in_client):
    a = make_transaction("Savings", is_transfer=True, source=Source.LLM)
    b = make_transaction("From checking", "10.00", is_transfer=True, source=Source.LLM)
    a.counterpart = b
    a.save()
    b.counterpart = a
    b.save()
    make_rule(logged_in_client, groceries(), description_contains="savings")

    logged_in_client.post(f"/rules/{rule_id('savings')}/apply/")

    a.refresh_from_db()
    b.refresh_from_db()
    assert a.subcategory_id == groceries() and a.counterpart is None
    assert b.counterpart is None


def test_applying_a_transfer_rule_pairs_the_other_side(logged_in_client):
    out = make_transaction("To savings")
    into = Transaction.objects.create(
        account=make_account("Savings", "other"),
        date="2026-06-02",
        amount=Decimal("10.00"),
        description="From checking",
    )
    make_rule(logged_in_client, "transfer", description_contains="to savings")

    logged_in_client.post(f"/rules/{rule_id('to savings')}/apply/")

    out.refresh_from_db()
    into.refresh_from_db()
    assert out.is_transfer and into.is_transfer
    assert out.counterpart == into and into.counterpart == out


def test_applying_a_transfer_rule_never_pairs_with_a_manual_outcome(logged_in_client):
    out = make_transaction("To savings")
    into = Transaction.objects.create(
        account=make_account("Savings", "other"),
        date="2026-06-02",
        amount=Decimal("10.00"),
        description="From checking",
        subcategory_id=groceries(),
        source=Source.MANUAL,
    )
    make_rule(logged_in_client, "transfer", description_contains="to savings")

    logged_in_client.post(f"/rules/{rule_id('to savings')}/apply/")

    out.refresh_from_db()
    into.refresh_from_db()
    assert out.is_transfer and out.counterpart is None
    assert (into.subcategory_id, into.source, into.counterpart) == (
        groceries(),
        Source.MANUAL,
        None,
    )


def test_applying_a_transfer_rule_reports_the_counterparts_pairing_converted(logged_in_client):
    make_transaction("To savings")
    Transaction.objects.create(
        account=make_account("Savings", "other"),
        date="2026-06-02",
        amount=Decimal("10.00"),
        description="From checking",
        subcategory_id=groceries(),
        source=Source.LLM,
    )
    make_rule(logged_in_client, "transfer", description_contains="to savings")

    response = logged_in_client.post(f"/rules/{rule_id('to savings')}/apply/", follow=True)

    page = response.content.decode()
    assert "1 Transaction categorized by the Rule." in page
    assert "1 categorized Transaction converted to a Transfer" in page


def test_applying_a_transfer_rule_reports_a_tie_left_for_review(logged_in_client):
    make_transaction("To savings")
    for name in ("Savings", "Holiday fund"):
        Transaction.objects.create(
            account=make_account(name, "other"),
            date="2026-06-02",
            amount=Decimal("10.00"),
            description="From checking",
        )
    make_rule(logged_in_client, "transfer", description_contains="to savings")

    response = logged_in_client.post(f"/rules/{rule_id('to savings')}/apply/", follow=True)

    page = response.content.decode()
    assert "1 Transaction categorized by the Rule." in page
    assert "1 Transfer with several possible counterparts waits in the Review queue" in page
    assert "converted" not in page


@pytest.mark.parametrize("outcome", ["transfer", "groceries"])
def test_applying_a_rule_pairing_changes_nothing_reports_only_the_rule(logged_in_client, outcome):
    make_transaction("To savings")
    Transaction.objects.create(
        account=make_account("Savings", "other"),
        date="2026-06-02",
        amount=Decimal("10.00"),
        description="From checking",  # unresolved, so pairing doesn't convert a Category
    )
    make_rule(
        logged_in_client,
        groceries() if outcome == "groceries" else outcome,
        description_contains="to savings",
    )

    response = logged_in_client.post(f"/rules/{rule_id('to savings')}/apply/", follow=True)

    messages = [str(m) for m in response.context["messages"]]
    assert messages == ["1 Transaction categorized by the Rule."]


@pytest.mark.parametrize(("outcome", "noted"), [("transfer", True), ("groceries", False)])
def test_only_a_transfer_rule_warns_that_pairing_may_convert_counterparts(
    logged_in_client, outcome, noted
):
    make_transaction("To savings")
    make_rule(
        logged_in_client,
        groceries() if outcome == "groceries" else outcome,
        description_contains="to savings",
    )

    offer = logged_in_client.get(f"/rules/{rule_id('to savings')}/apply/").content.decode()

    assert ("may also convert a counterpart" in offer) == noted
