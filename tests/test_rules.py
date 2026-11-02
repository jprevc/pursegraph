import json
import re
from decimal import Decimal

import pytest

from ledger.models import Account, Category, Rule, Source, Transaction
from tests.conftest import make_account, outcome_shown, page_text, subcategory_id, transaction_id
from tests.test_import import upload

pytestmark = pytest.mark.django_db


def make_rule(client, outcome, **conditions):
    """Creates a Rule through the Rules page and returns the response."""
    data = {"description_contains": "", "counterparty_iban": "", "direction": "", "account": ""}
    return client.post("/rules/new/", {**data, **conditions, "outcome": outcome})


def apply_rule(client, rule, follow=False, **posted):
    """Saves `rule` again on its Rule page with "Save and change N", which applies it to the existing Transactions."""
    data = {
        "description_contains": rule.description_contains,
        "counterparty_iban": rule.counterparty_iban,
        "direction": rule.direction,
        "account": rule.account_id or "",
        "outcome": rule.subcategory_id or "transfer",
        "apply": "1",
    }
    return client.post(f"/rules/{rule.pk}/edit/", {**data, **posted}, follow=follow)


def rule_order(client):
    """The Rules page's Rules, top first, by their description-contains condition."""
    page = client.get("/rules/").content.decode()
    return re.findall(r'<span class="r-name">“([^<]*)”</span>', page)


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

    assert "1 categorized by Rules" in page_text(summary)
    page = logged_in_client.get("/transactions/").content.decode()
    assert outcome_shown(page, "Mercator Žalec") == "Food → Groceries"
    mercator = Transaction.objects.get(description="Mercator Žalec")
    assert mercator.source == Source.RULE
    assert mercator.rule_id == rule_id("mercator")


def test_description_contains_ignores_case_and_accents(logged_in_client):
    make_rule(logged_in_client, groceries(), description_contains="MERCATOR ZALEC")
    make_rule(logged_in_client, subcategory_id("Leisure", "Other"), description_contains="hisa")

    summary = upload(logged_in_client).content.decode()

    assert "2 categorized by Rules" in page_text(summary)
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

    apply_rule(logged_in_client, Rule.objects.get())

    match.refresh_from_db()
    other.refresh_from_db()
    assert match.is_transfer and match.source == Source.RULE
    assert not other.is_transfer and other.source == ""


def test_a_rule_needs_a_condition(logged_in_client):
    response = make_rule(logged_in_client, groceries())

    assert response.status_code == 200
    assert "Give the Rule at least one condition." in response.content.decode()
    assert not Rule.objects.exists()


def test_the_rules_page_lists_rules_for_any_member(logged_in_client, household):
    make_rule(logged_in_client, groceries(), description_contains="mercator", direction="out")

    page = logged_in_client.get("/rules/").content.decode()

    assert "“mercator”" in page
    assert "Food › Groceries" in page_text(page)
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


def test_saving_a_rule_without_applying_changes_nothing_yet(logged_in_client):
    upload(logged_in_client)

    response = make_rule(logged_in_client, groceries(), description_contains="o")

    pk = Rule.objects.get().pk
    assert response.status_code == 302
    assert response.url == f"/rules/?rule={pk}"
    page = logged_in_client.get("/transactions/").content.decode()
    assert outcome_shown(page, "Corner Shop") == "Awaiting review"


def test_saving_and_changing_applies_the_rule_and_says_so(logged_in_client):
    upload(logged_in_client)
    make_rule(logged_in_client, groceries(), description_contains="o")

    response = apply_rule(logged_in_client, Rule.objects.get(), follow=True)

    # Corner Shop, Payment from Ana Novak, To Janez Kranjc, Mercator; not the fees (parser)
    assert "4 Transactions categorized by the Rule." in page_text(response.content.decode())
    page = logged_in_client.get("/transactions/").content.decode()
    assert outcome_shown(page, "Corner Shop") == "Food → Groceries"


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

    response = apply_rule(logged_in_client, Rule.objects.get(description_contains="shop"))

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

    apply_rule(logged_in_client, Rule.objects.get(description_contains="savings"))

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

    apply_rule(logged_in_client, Rule.objects.get(description_contains="savings"))

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

    apply_rule(logged_in_client, Rule.objects.get(description_contains="to savings"))

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

    apply_rule(logged_in_client, Rule.objects.get(description_contains="to savings"))

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

    response = apply_rule(
        logged_in_client, Rule.objects.get(description_contains="to savings"), follow=True
    )

    assert [str(m) for m in response.context["messages"]][-1] == (
        "1 Transaction categorized by the Rule. 1 categorized Transaction converted to a Transfer."
    )


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

    response = apply_rule(
        logged_in_client, Rule.objects.get(description_contains="to savings"), follow=True
    )

    page = response.content.decode()
    assert "1 Transaction categorized by the Rule." in page
    assert "1 Transfer with several possible counterparts waits in the Review queue" in page
    assert "converted" not in page


@pytest.mark.parametrize("outcome", ["transfer", "groceries"])
def test_applying_a_rule_whose_pairing_changes_nothing_reports_only_the_rule(
    logged_in_client, outcome
):
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

    response = apply_rule(
        logged_in_client, Rule.objects.get(description_contains="to savings"), follow=True
    )

    messages = [str(m) for m in response.context["messages"]]
    assert messages[-1] == "1 Transaction categorized by the Rule."


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

    page = logged_in_client.get(f"/rules/{rule_id('to savings')}/edit/").content.decode()

    assert ("may also convert a counterpart" in page) == noted


@pytest.mark.parametrize(
    ("description", "prefilled"),
    [
        ("HOFER 2201 LJUBLJANA", "HOFER"),
        ("PAYPAL *STEAMGAMES", "STEAMGAMES"),
        ("PAYPAL*STEAMGAMES", "STEAMGAMES"),
        ("Lekarna Ljubljana 12", "Lekarna"),
        ("Corner Shop", "Corner Shop"),
    ],
)
def test_make_a_rule_prefills_the_merchant_word(logged_in_client, description, prefilled):
    t = make_transaction(description)
    t.set_outcome(None, source=Source.MANUAL)

    form = logged_in_client.get(f"/rules/new/?transaction={t.pk}").content.decode()

    assert re.search(rf'name="description_contains"[^>]*value="{re.escape(prefilled)}"', form)


def hx(client, method, url, data=None, target="rules"):
    """An HTMX request, as the Rules page sends it."""
    return getattr(client, method)(url, data or {}, HTTP_HX_REQUEST="true", HTTP_HX_TARGET=target)


def announced(response):
    return json.loads(response["HX-Trigger"])["announce"]


def test_the_rules_page_shows_the_selected_rules_matches(logged_in_client):
    mine = make_transaction("SPAR Bežigrad", subcategory_id=groceries(), source=Source.RULE)
    make_transaction("SPAR by hand", subcategory_id=groceries(), source=Source.MANUAL)
    make_rule(logged_in_client, groceries(), description_contains="spar", direction="out")
    mine.rule = Rule.objects.get()
    mine.save()

    page = page_text(logged_in_client.get(f"/rules/?rule={mine.rule.pk}").content.decode())

    assert "The first Rule a Transaction matches at import decides it" in page
    assert "1. “spar” → Food › Groceries" in page
    assert "contains spar" in page and "money out" in page
    assert "Categorized 1 Transaction" in page
    assert "Categorized by this Rule · 1" in page
    assert "Also matches, decided otherwise · 1" in page


def test_the_effect_line_names_the_rules_above_that_take_its_matches(logged_in_client):
    make_transaction("SPAR Bežigrad")
    make_rule(logged_in_client, groceries(), description_contains="s")
    make_rule(logged_in_client, groceries(), description_contains="spar")  # goes to the top

    page = page_text(logged_in_client.get(f"/rules/?rule={rule_id('s')}").content.decode())

    assert "Categorized 0 Transactions" in page
    assert "1 of its matches goes to Rule 1 (“spar”) above." in page


def test_selecting_a_rule_swaps_in_its_detail_alone(logged_in_client):
    make_rule(logged_in_client, groceries(), description_contains="corner")
    make_rule(logged_in_client, groceries(), description_contains="shop")

    response = hx(
        logged_in_client, "get", f"/rules/?rule={rule_id('corner')}", target="rule-detail"
    )

    page = response.content.decode()
    assert "<title>" in page
    assert "2. “corner”" in page_text(page)
    assert 'role="listbox"' not in page


def test_moving_a_rule_is_announced_and_keeps_it_selected(logged_in_client):
    make_rule(logged_in_client, groceries(), description_contains="corner")
    make_rule(logged_in_client, "transfer", description_contains="shop")

    response = hx(
        logged_in_client, "post", f"/rules/{rule_id('shop')}/move/", {"direction": "down"}
    )

    assert announced(response) == "Moved “shop” to 2nd."
    assert "2. “shop”" in page_text(response.content.decode())
    assert rule_order(logged_in_client) == ["corner", "shop"]


def test_dragging_a_rule_is_announced(logged_in_client):
    make_rule(logged_in_client, groceries(), description_contains="corner")
    make_rule(logged_in_client, "transfer", description_contains="shop")

    response = hx(
        logged_in_client,
        "post",
        "/rules/reorder/",
        {"rule": [rule_id("corner"), rule_id("shop")], "moved": rule_id("shop")},
    )

    assert announced(response) == "Moved “shop” to 2nd."
    assert rule_order(logged_in_client) == ["corner", "shop"]


def test_deleting_a_rule_confirms_inline_and_keeps_the_outcomes(logged_in_client):
    make_rule(logged_in_client, groceries(), description_contains="mercator")
    upload(logged_in_client)
    pk = rule_id("mercator")

    confirm = hx(logged_in_client, "get", f"/rules/{pk}/delete/", target="confirm-slot")
    assert (
        "Delete “mercator”? Its 1 Transaction keeps its outcome; future imports won't use it."
        in page_text(confirm.content.decode())
    )
    response = hx(logged_in_client, "post", f"/rules/{pk}/delete/")

    assert announced(response) == "Deleted “mercator”."
    assert not Rule.objects.exists()
    assert Transaction.objects.get(description="Mercator Žalec").subcategory_id == groceries()


def test_deleting_without_js_confirms_on_the_rules_page(logged_in_client):
    make_rule(logged_in_client, groceries(), description_contains="mercator")

    page = logged_in_client.get(f"/rules/{rule_id('mercator')}/delete/").content.decode()

    assert "Delete “mercator”? Future imports won't use it." in page_text(page)
    assert "Delete Rule" in page


def test_the_rule_page_previews_what_saving_changes(logged_in_client):
    upload(logged_in_client)

    response = hx(
        logged_in_client,
        "get",
        "/rules/preview/",
        {"description_contains": "o", "direction": "", "account": "", "outcome": groceries()},
        target="preview",
    )

    page = page_text(response.content.decode())
    assert "Will change · 4" in page
    assert "Save and change 4" in page


def test_the_rule_page_warns_of_rules_it_takes_over_from(logged_in_client):
    make_rule(logged_in_client, groceries(), description_contains="corner")
    make_transaction("Corner Shop")
    apply_rule(logged_in_client, Rule.objects.get())

    response = hx(
        logged_in_client,
        "get",
        "/rules/preview/",
        {"description_contains": "shop", "outcome": "transfer"},
        target="preview",
    )

    assert "Takes 1 over from Rule 1 (“corner”)" in page_text(response.content.decode())


def test_make_a_rule_pins_the_transaction_just_saved(logged_in_client):
    t = make_transaction("HOFER 2201 LJUBLJANA", subcategory_id=groceries(), source=Source.MANUAL)

    page = logged_in_client.get(f"/rules/new/?transaction={t.pk}").content.decode()

    assert "<h1" in page and "Make a Rule" in page_text(page)
    assert "the one you just saved" in page_text(page)
    assert re.search(r'<button[^>]*aria-pressed="true"[^>]*>HOFER</button>', page)
    assert re.search(r'<button[^>]*aria-pressed="false"[^>]*>2201</button>', page)


def test_previewing_without_js_saves_nothing(logged_in_client):
    response = make_rule(logged_in_client, groceries(), description_contains="shop", preview="1")

    assert response.status_code == 200
    assert not Rule.objects.exists()


def test_a_rules_detail_lists_what_it_categorized_even_after_its_conditions_changed(
    logged_in_client,
):
    make_rule(logged_in_client, groceries(), description_contains="corner")
    make_transaction("Corner Shop")
    apply_rule(logged_in_client, Rule.objects.get())
    rule = Rule.objects.get()
    apply_rule(logged_in_client, rule, description_contains="nowhere", apply="")

    page = page_text(logged_in_client.get(f"/rules/?rule={rule.pk}").content.decode())

    assert "Categorized 1 Transaction" in page
    assert "Categorized by this Rule · 1" in page


def test_saving_waits_for_an_outcome(logged_in_client):
    make_transaction("Corner Shop")

    response = hx(
        logged_in_client,
        "get",
        "/rules/preview/",
        {"description_contains": "corner", "outcome": ""},
        target="preview",
    )

    assert re.search(
        r'<button type="submit" class="primary"[^>]*disabled', response.content.decode()
    )
