import html
import json
import re
from datetime import date

import pytest

from ledger.models import Account, Category, Subcategory, Transaction
from tests.conftest import EUR, transaction_id
from tests.test_import import upload

pytestmark = pytest.mark.django_db

ALL = [
    "Hiša kave",
    "Payment from Ana Novak",
    "Corner Shop",
    "Fee: Corner Shop",
    "To Janez Kranjc",
    "Fee: To Janez Kranjc",
    "Čevljar",
    "Mercator Žalec",
]


def shown(client, **params):
    page = client.get("/transactions/", params).content.decode()
    return [description for description in ALL if f">{description}<" in page]


def test_search_matches_the_description_ignoring_case_and_accents(logged_in_client):
    upload(logged_in_client)

    assert shown(logged_in_client, q="corner") == ["Corner Shop", "Fee: Corner Shop"]
    assert shown(logged_in_client, q="cevljar") == ["Čevljar"]
    assert shown(logged_in_client, q="ŽALEC") == ["Mercator Žalec"]


def test_search_matches_the_counterparty(logged_in_client):
    upload(logged_in_client)
    Transaction.objects.filter(description="Hiša kave").update(counterparty_name="Kavarna d.o.o.")

    assert shown(logged_in_client, q="kavarna") == ["Hiša kave"]


def test_filter_by_account(logged_in_client):
    upload(logged_in_client)
    other = Account.objects.create(name="Bor's N26", bank="n26")
    Transaction.objects.filter(description="Čevljar").update(account=other)

    assert shown(logged_in_client, account=other.pk) == ["Čevljar"]


def test_filter_by_outcome(logged_in_client):
    upload(logged_in_client)
    logged_in_client.post(
        f"/transactions/{transaction_id('To Janez Kranjc')}/outcome/", {"outcome": "transfer"}
    )
    groceries = Subcategory.objects.get(category__name="Food", name="Groceries")
    logged_in_client.post(
        f"/transactions/{transaction_id('Mercator Žalec')}/outcome/", {"outcome": groceries.pk}
    )
    food = Category.objects.get(name="Food")

    assert shown(logged_in_client, outcome="unresolved") == [
        "Hiša kave",
        "Payment from Ana Novak",
        "Corner Shop",
        "Čevljar",
    ]
    assert shown(logged_in_client, outcome="transfer") == ["To Janez Kranjc"]
    assert shown(logged_in_client, outcome=f"category-{food.pk}") == ["Mercator Žalec"]
    assert shown(logged_in_client, outcome=f"subcategory-{groceries.pk}") == ["Mercator Žalec"]


def test_filters_combine_and_stay_filled_in(logged_in_client):
    upload(logged_in_client)

    page = logged_in_client.get(
        "/transactions/", {"q": "corner", "outcome": "unresolved"}
    ).content.decode()

    assert ">Corner Shop<" in page
    assert ">Fee: Corner Shop<" not in page
    assert 'value="corner"' in page
    assert re.search(r'id="f-outcome-unresolved"[^>]*aria-pressed="true"', page)


def test_no_matches_says_so(logged_in_client):
    upload(logged_in_client)

    page = logged_in_client.get("/transactions/", {"q": "nothing like this"}).content.decode()

    assert "No Transactions match." in page
    assert "Import your first Statement" not in page


def test_long_lists_are_paged_25_at_a_time_newest_first(logged_in_client):
    account = Account.objects.create(name="Joint N26", bank="n26")
    Transaction.objects.bulk_create(
        Transaction(
            account=account, date=date(2026, 1, 1 + i % 28), amount=-1, description=f"Row {i:03}"
        )
        for i in range(120)
    )

    first = logged_in_client.get("/transactions/").content.decode()
    third = logged_in_client.get("/transactions/", {"page": 3, "q": "row"}).content.decode()
    last = logged_in_client.get("/transactions/", {"page": 5}).content.decode()

    assert first.count('<tr id="transaction-') == 25
    assert ">Row 027<" in first  # 28 Jan
    assert "1–25 of 120" in first
    # First, last and the current page ±1, with "…" between; the filters stay.
    assert page_numbers(third) == ["1", "2", "3", "4", "5"]
    assert 'aria-current="page" href="/transactions/?q=row&amp;page=3"' in third
    assert "51–75 of 120" in third
    assert last.count('<tr id="transaction-') == 20
    assert re.search(r'aria-disabled="true">.*Older', last)


def page_numbers(page):
    pager = re.search(r'<span class="nums">(.*?)</span>\s*<span class="range', page, re.S)
    assert pager
    return re.findall(r">(\d+|…)</", pager[1])


def test_the_pager_elides_the_pages_far_from_the_current_one(logged_in_client):
    account = Account.objects.create(name="Joint N26", bank="n26")
    Transaction.objects.bulk_create(
        Transaction(account=account, date=date(2026, 1, 1), amount=-1, description=f"Row {i}")
        for i in range(300)
    )

    page = logged_in_client.get("/transactions/", {"page": 6}).content.decode()

    assert page_numbers(page) == ["1", "…", "5", "6", "7", "…", "12"]


def test_the_summary_counts_and_totals_and_names_the_filters(logged_in_client, household):
    page = logged_in_client.get(
        "/transactions/", {"period": "2026-09", "outcome": "unresolved"}
    ).content.decode()

    summary = text(found(r'<p id="summary".*?</p>', page))
    assert summary == (
        f"2 Transactions · 12,30{EUR} out · 45,00{EUR} in · September 2026, Awaiting review Clear filters"
    )
    assert "<title>Transactions · September 2026 · Awaiting review · Pursegraph</title>" in page


def test_money_out_and_in_leave_transfers_aside(logged_in_client, household):
    page = logged_in_client.get("/transactions/", {"period": "2026-09"}).content.decode()

    summary = text(found(r'<p id="summary".*?</p>', page))
    # 12 Transactions; the 500,00 € Transfer moved either way counts in neither.
    assert summary.startswith(f"12 Transactions · 292,30{EUR} out · 3.580,00{EUR} in")


def found(pattern, page, group=0):
    """What `pattern` finds in `page` (`.` matching newlines too), or its `group`."""
    match = re.search(pattern, page, re.S)
    assert match, f"nothing matches {pattern!r}"
    return match[group]


def text(fragment):
    return re.sub(r"[ \t\n]+", " ", html.unescape(re.sub(r"<[^>]+>", " ", fragment))).strip()


def test_each_facet_option_shows_its_count_with_the_others_held(logged_in_client, household):
    page = logged_in_client.get(
        "/transactions/", {"period": "2026-09", "member": household["marko"].pk}
    ).content.decode()

    assert option(page, "f-period-2026-09") == ("September 2026", "3", "true")
    assert option(page, "f-period-2026-08") == ("August 2026", "1", "false")
    assert option(page, "f-member-any") == ("Everyone", "12", "false")
    assert option(page, "f-outcome-transfer") == ("Transfer", "0", "false")


def option(page, id):
    """A facet option's label, count and whether it is pressed."""
    button = re.search(
        rf'<button[^>]*id="{id}"[^>]*aria-pressed="(\w+)">(.*?)</button>', page, re.S
    )
    assert button, f"no option {id}"
    label = text(found(r'<span class="t">(.*?)</span>', button[2], 1))
    return label, text(found(r'<span class="n fig">(.*?)</span>', button[2], 1)), button[1]


def test_a_chosen_category_opens_its_subcategories_and_picking_it_again_clears_it(
    logged_in_client, household
):
    food = Category.objects.get(name="Food")
    groceries = Subcategory.objects.get(category=food, name="Groceries")

    closed = logged_in_client.get("/transactions/").content.decode()
    opened = logged_in_client.get(
        "/transactions/", {"outcome": f"category-{food.pk}"}
    ).content.decode()

    assert f'id="f-outcome-subcategory-{groceries.pk}"' not in closed
    assert option(opened, f"f-outcome-subcategory-{groceries.pk}") == ("Groceries", "4", "false")
    chosen = found(rf'<button[^>]*id="f-outcome-category-{food.pk}"[^>]*>', opened)
    assert 'name="outcome"' not in chosen


def test_a_facet_swap_announces_the_count_and_pushes_a_tidy_address(logged_in_client, household):
    response = logged_in_client.get(
        "/transactions/",
        {"period": "2026-09", "dir": "", "min": "", "q": ""},
        HTTP_HX_REQUEST="true",
        HTTP_HX_TARGET="results",
    )

    assert response["HX-Push-Url"] == "/transactions/?period=2026-09"
    assert json.loads(response["HX-Trigger"]) == {"announce": "12 Transactions"}
    assert '<div class="tabbar"' not in response.content.decode()


def test_the_pager_announces_the_page(logged_in_client):
    account = Account.objects.create(name="Joint N26", bank="n26")
    Transaction.objects.bulk_create(
        Transaction(account=account, date=date(2026, 1, 1), amount=-1, description=f"Row {i}")
        for i in range(60)
    )

    response = logged_in_client.get(
        "/transactions/",
        {"page": 2},
        HTTP_HX_REQUEST="true",
        HTTP_HX_TARGET="results",
        HTTP_X_PAGER="true",
    )

    assert response["HX-Push-Url"] == "/transactions/?page=2"
    assert json.loads(response["HX-Trigger"]) == {"announce": "Page 2 of 3, 26–50 of 60"}


def test_decided_just_now_is_named_and_cleared_with_the_filters(logged_in_client, household):
    pks = list(Transaction.objects.filter(date__month=9).values_list("pk", flat=True)[:3])

    page = logged_in_client.get(
        "/transactions/", {"decided": ",".join(map(str, pks)), "dashboard": "period=2026-09"}
    ).content.decode()

    summary = text(found(r'<p id="summary".*?</p>', page))
    assert summary.endswith("· Decided just now · 3 Clear filters")
    assert 'class="clear" href="/transactions/?dashboard=period%3D2026-09"' in page


def test_a_drill_downs_link_opens_transactions_with_a_breadcrumb_back(logged_in_client, household):
    food = Category.objects.get(name="Food")
    drill = logged_in_client.get(
        "/spending/transactions/", {"period": "2026-09", "category": food.pk}
    ).content.decode()
    link = re.search(r'<a class="all" href="([^"]+)"[^>]*>([^<]*)</a>', drill)

    assert link and html.unescape(link[2]) == "All 3 in Transactions ›"
    page = logged_in_client.get(html.unescape(link[1])).content.decode()
    crumbs = found(r'<nav class="crumbs".*?</nav>', page)
    assert text(crumbs) == "Dashboard › Spending · Food · September 2026"
    assert 'href="/spending/?period=2026-09"' in crumbs
    assert page.count('<tr id="transaction-') == 3


def test_the_breadcrumb_goes_once_the_period_member_or_outcome_changes(logged_in_client, household):
    food = Category.objects.get(name="Food")
    base = {
        "period": "2026-09",
        "outcome": f"category-{food.pk}",
        "from": "spending",
        "mark": food.pk,
    }

    def crumbed(**changes):
        page = logged_in_client.get("/transactions/", {**base, **changes}).content.decode()
        return '<nav class="crumbs"' in page

    assert crumbed()
    assert crumbed(dir="out")
    page = logged_in_client.get("/transactions/", base).content.decode()
    period_form = found(r'<form class="facet".*?</form>', page)
    assert 'name="from"' not in period_form
    assert 'name="from"' in found(r'<form class="facet amount".*?</form>', page)


def test_a_rows_source_caption_gives_its_specific_reason_as_a_title(logged_in_client):
    account = Account.objects.create(name="Joint N26", bank="n26")
    groceries = Subcategory.objects.get(category__name="Food", name="Groceries")
    Transaction.objects.create(
        account=account,
        date=date(2026, 1, 1),
        amount=-1,
        description="Hofer",
        subcategory=groceries,
        source="manual",
    )

    page = logged_in_client.get("/transactions/").content.decode()

    assert '<span class="cap" title="A Member chose it.">by hand</span>' in page
