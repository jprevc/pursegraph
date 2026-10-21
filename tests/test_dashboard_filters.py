import html
import re
from datetime import date

import pytest

from ledger.models import Account, Category, Transaction

from .conftest import EUR, drill_rows, make_account, view_chart, view_table

pytestmark = pytest.mark.django_db

TODAY = date(2026, 10, 15)


@pytest.fixture(autouse=True)
def today(monkeypatch):
    monkeypatch.setattr("dashboard.periods.today", lambda: TODAY)


def spent(page):
    return {b["name"]: b["value"] for b in view_chart(page, "spending")["bars"]}


def test_a_member_filter_narrows_spending_to_that_members_own_accounts(logged_in_client, household):
    ana = household["ana"].pk

    page = logged_in_client.get("/spending/", {"period": "2026-09", "member": ana}).content.decode()

    assert spent(page) == {"Food": 80, "Shopping": 70, "Awaiting review": 12.3}


def account_id(name):
    return Account.objects.get(name=name).pk


def test_the_joint_member_filter_shows_the_joint_accounts(logged_in_client, household):
    page = logged_in_client.get(
        "/spending/", {"period": "2026-09", "member": "joint"}
    ).content.decode()

    assert spent(page) == {"Food": 60}


def test_an_account_filter_narrows_to_the_chosen_accounts(logged_in_client, household):
    page = logged_in_client.get(
        "/spending/",
        {"period": "2026-09", "account": [account_id("Marko's N26"), account_id("Joint Revolut")]},
    ).content.decode()

    assert spent(page) == {"Food": 100}


def test_member_and_account_filters_combine(logged_in_client, household):
    page = logged_in_client.get(
        "/spending/",
        {"period": "2026-09", "member": "joint", "account": account_id("Marko's N26")},
    ).content.decode()

    assert "No spending in this period." in page


def test_unknown_filters_are_ignored(logged_in_client, household):
    page = logged_in_client.get(
        "/spending/", {"period": "2026-09", "member": "nobody", "account": ["999", "x"]}
    ).content.decode()

    assert spent(page) == {"Food": 180, "Shopping": 70, "Awaiting review": 12.3}


def test_the_drill_down_respects_the_filters(logged_in_client, household):
    food = Category.objects.get(name="Food").pk
    url = "/spending/transactions/"

    assert drill_rows(
        logged_in_client, url, {"period": "2026-09", "category": food, "member": "joint"}
    ) == ["Spar"]
    assert drill_rows(
        logged_in_client,
        url,
        {"period": "2026-09", "category": food, "account": account_id("Marko's N26")},
    ) == ["Gostilna"]


def test_per_member_ignores_the_member_filter_but_not_the_account_filter(
    logged_in_client, household
):
    marko = household["marko"].pk

    page = logged_in_client.get(
        "/per-member/", {"period": "2026-09", "member": marko}
    ).content.decode()
    assert view_table(page) == [
        ["ana", f"162,30{EUR}"],
        ["marko", f"40,00{EUR}"],
        ["Joint", f"60,00{EUR}"],
    ]
    assert drill_rows(
        logged_in_client,
        "/per-member/transactions/",
        {"period": "2026-09", "member": marko, "key": "joint"},
    ) == ["Spar"]

    page = logged_in_client.get(
        "/per-member/",
        {"period": "2026-09", "member": marko, "account": account_id("Joint Revolut")},
    ).content.decode()
    assert view_table(page) == [["Joint", f"60,00{EUR}"]]


def pair(description, other):
    """Links two Transfer sides, as pairing at import does."""
    side, counterpart = (
        Transaction.objects.get(description=description),
        Transaction.objects.get(description=other),
    )
    side.counterpart, counterpart.counterpart = counterpart, side
    side.save()
    counterpart.save()


@pytest.fixture
def paired(household):
    pair("To Joint Revolut", "From Ana's Sparkasse")
    return household


def test_under_a_member_filter_cashflow_shows_transfers_to_and_from_other_members(
    logged_in_client, paired
):
    ana = paired["ana"].pk

    page = logged_in_client.get("/cashflow/", {"period": "2026-09", "member": ana}).content.decode()
    # The net is what Ana's Account balance moved by: 2045.00 in, 162.30 spent, 500.00 to the joint Account.
    assert "To/from other Members" in page
    assert view_table(page) == [
        ["Sep 2026", f"2.045,00{EUR}", f"162,30{EUR}", f"−500,00{EUR}", f"+1.382,70{EUR}"]
    ]
    assert view_chart(page, "cashflow")["others"] == [-500]

    page = logged_in_client.get(
        "/cashflow/", {"period": "2026-09", "member": "joint"}
    ).content.decode()
    assert view_table(page) == [
        ["Sep 2026", f"0,00{EUR}", f"60,00{EUR}", f"+500,00{EUR}", f"+440,00{EUR}"]
    ]


def test_without_a_member_filter_cashflow_has_no_other_members(logged_in_client, paired):
    page = logged_in_client.get("/cashflow/", {"period": "2026-09"}).content.decode()

    assert "To/from other Members" not in page
    assert view_table(page) == [["Sep 2026", f"3.550,00{EUR}", f"262,30{EUR}", f"+3.287,70{EUR}"]]


def test_a_transfers_other_side_is_its_counterpart_or_else_the_account_of_its_iban(
    logged_in_client, paired
):
    ana, marko = paired["ana"], paired["marko"]
    markos = Account.objects.get(name="Marko's N26")
    anas = Account.objects.get(name="Ana's Sparkasse")
    anas.ibans.create(iban="SI56191000000123438")
    make_account("Ana's savings", "other", ana, ibans=["SI56020000000000001"])
    for account, amount, description, iban in [
        (markos, "-50.00", "To Ana", "SI56191000000123438"),  # one-sided, to Ana's IBAN
        (markos, "-70.00", "To savings, somewhere", ""),  # one-sided, other side unknown
        (anas, "-30.00", "To my savings", "SI56020000000000001"),  # between Ana's own Accounts
    ]:
        Transaction.objects.create(
            account=account, date=date(2026, 9, 10), amount=amount, description=description,
            counterparty_iban=iban, is_transfer=True, source="manual",
        )  # fmt: skip
    url = "/cashflow/transactions/"
    params = {"period": "2026-09", "key": "2026-09:others"}

    assert drill_rows(logged_in_client, url, {**params, "member": marko.pk}) == ["To Ana"]
    assert drill_rows(logged_in_client, url, {**params, "member": ana.pk}) == ["To Joint Revolut"]
    page = logged_in_client.get(
        "/cashflow/", {"period": "2026-09", "member": marko.pk}
    ).content.decode()
    assert view_table(page) == [
        ["Sep 2026", f"1.505,00{EUR}", f"40,00{EUR}", f"−50,00{EUR}", f"+1.415,00{EUR}"]
    ]


def test_a_months_drill_down_includes_transfers_to_other_members(logged_in_client, paired):
    assert drill_rows(
        logged_in_client,
        "/cashflow/transactions/",
        {"period": "2026-09", "key": "2026-09", "member": "joint"},
    ) == ["From Ana's Sparkasse", "Spar"]


def test_under_a_member_filter_the_sankey_has_a_node_for_other_members(logged_in_client, paired):
    page = logged_in_client.get(
        "/money-flow/", {"period": "2026-09", "member": paired["ana"].pk}
    ).content.decode()

    chart = view_chart(page, "money_flow")
    assert {"name": "others", "label": "To/from other Members", "key": "others"} in chart["nodes"]
    assert {"source": "household", "target": "others", "value": 500} in chart["links"]
    # Saved is what is left of 2045.00 in after 162.30 spent and 500.00 to other Members.
    assert {"source": "household", "target": "saved", "value": 1382.7} in chart["links"]
    assert "To/from other Members" in [row[0] for row in view_table(page)]

    page = logged_in_client.get(
        "/money-flow/", {"period": "2026-09", "member": "joint"}
    ).content.decode()
    assert {"source": "others", "target": "household", "value": 500} in view_chart(
        page, "money_flow"
    )["links"]
    assert drill_rows(
        logged_in_client,
        "/money-flow/transactions/",
        {"period": "2026-09", "key": "others", "member": "joint"},
    ) == ["From Ana's Sparkasse"]


def test_without_a_member_filter_the_sankey_has_no_other_members(logged_in_client, paired):
    page = logged_in_client.get("/money-flow/", {"period": "2026-09"}).content.decode()

    assert "To/from other Members" not in page


def test_category_trends_leave_transfers_out_under_a_member_filter(logged_in_client, paired):
    page = logged_in_client.get(
        "/trends/", {"period": "2026-09", "member": "joint"}
    ).content.decode()

    assert view_table(page) == [["Food", f"60,00{EUR}", f"60,00{EUR}"]]


def selected_member(page):
    select = re.search(r'<select name="member"[^>]*>(.*?)</select>', page, re.S)
    assert select, "no Member filter"
    options = re.findall(r'<option value="([^"]*)"( selected)?>([^<]*)</option>', select[1])
    return [label for _value, _selected, label in options], [
        label for _value, selected, label in options if selected
    ]


def chosen_accounts(page):
    return [
        html.unescape(name)
        for name in re.findall(
            r'<input type="checkbox" name="account" value="\d+" checked>\s*([^<]*?)\s*</label>',
            page,
        )
    ]


def test_the_filter_bar_shows_the_members_and_accounts_chosen(logged_in_client, household):
    page = logged_in_client.get(
        "/cashflow/",
        {"period": "2026-09", "member": "joint", "account": account_id("Joint Revolut")},
    ).content.decode()

    assert selected_member(page) == (["All Members", "ana", "marko", "Joint"], ["Joint"])
    assert chosen_accounts(page) == ["Joint Revolut"]
    assert len(re.findall(r'<input type="checkbox" name="account"', page)) == 3

    page = logged_in_client.get("/cashflow/").content.decode()
    assert selected_member(page)[1] == ["All Members"]
    assert chosen_accounts(page) == []


def test_a_member_who_owns_no_account_alone_is_not_offered_and_filtering_to_them_is_ignored(
    logged_in_client, household, django_user_model
):
    nina = django_user_model.objects.create_user(username="nina", password="x")
    Account.objects.get(name="Joint Revolut").owners.add(nina)

    page = logged_in_client.get(
        "/spending/", {"period": "2026-09", "member": nina.pk}
    ).content.decode()

    assert selected_member(page) == (["All Members", "ana", "marko", "Joint"], ["All Members"])
    unfiltered = logged_in_client.get("/spending/", {"period": "2026-09"}).content.decode()
    assert spent(page) == spent(unfiltered)


def test_the_filters_carry_to_the_drill_down_and_the_period_selector(logged_in_client, household):
    joint = account_id("Joint Revolut")

    page = logged_in_client.get(
        "/spending/", {"period": "2026-09", "member": "joint", "account": joint}
    ).content.decode()

    assert view_chart(page, "spending")["drill"] == (
        f"/spending/transactions/?period=2026-09&member=joint&account={joint}&category="
    )
    assert f'href="/spending/?period=2026-08&amp;member=joint&amp;account={joint}"' in page


def nav_links(page):
    """Where the sidebar's dashboard view links go."""
    return dict(
        (html.unescape(label), html.unescape(href))
        for href, label in re.findall(
            r'<a class="nav[^"]*" href="([^"]*)"[^>]*hx-get[^>]*>([^<]*)</a>', page
        )
    )


def test_the_filters_and_a_chosen_period_carry_across_views(logged_in_client, household):
    page = logged_in_client.get(
        "/cashflow/", {"period": "2026-Q3", "member": "joint"}
    ).content.decode()
    assert nav_links(page)["Category trends"] == "/trends/?period=2026-Q3&member=joint"

    # Without a period chosen, each view keeps its own default one.
    page = logged_in_client.get("/cashflow/", {"member": "joint"}).content.decode()
    assert nav_links(page)["Category trends"] == "/trends/?member=joint"

    # Swapped in by HTMX, the view brings the sidebar's links along.
    page = logged_in_client.get(
        "/cashflow/", {"period": "2026-Q3", "member": "joint"}, headers={"HX-Request": "true"}
    ).content.decode()
    assert 'hx-swap-oob="true"' in page
    assert nav_links(page)["Money flow"] == "/money-flow/?period=2026-Q3&member=joint"


def test_per_member_keeps_the_member_filter_for_other_views(logged_in_client, household):
    page = logged_in_client.get(
        "/per-member/", {"period": "2026-09", "member": "joint"}
    ).content.decode()

    assert "ignores the Member filter" in page
    assert '<input type="hidden" name="member" value="joint">' in page
    assert nav_links(page)["Cashflow"] == "/cashflow/?period=2026-09&member=joint"


def page_links(page):
    """Where every sidebar link goes, the dashboard views' and the other pages'."""
    return dict(
        (html.unescape(label).strip(), html.unescape(href))
        for href, label in re.findall(r'<a class="nav[^"]*" href="([^"]*)"[^>]*>([^<]*)', page)
    )


def test_the_period_and_filters_survive_a_visit_to_another_page(logged_in_client, household):
    joint = account_id("Joint Revolut")
    page = logged_in_client.get(
        "/cashflow/", {"period": "2026-Q3", "member": "joint", "account": joint}
    ).content.decode()

    transactions = page_links(page)["Transactions"]
    page = logged_in_client.get(transactions).content.decode()

    assert (
        page_links(page)["Money flow"]
        == f"/money-flow/?period=2026-Q3&member=joint&account={joint}"
    )
    # The dashboard's Account filter doesn't narrow the Transactions page.
    everything = logged_in_client.get("/transactions/").content.decode()
    assert page.count('<tr id="transaction-') == everything.count('<tr id="transaction-')
    # Filtering the Transactions page keeps them too.
    carried = re.search(r'<input type="hidden" name="dashboard" value="([^"]*)">', page)
    assert carried
    page = logged_in_client.get(
        "/transactions/", {"q": "salary", "dashboard": html.unescape(carried[1])}
    ).content.decode()
    assert page_links(page)["Cashflow"] == f"/cashflow/?period=2026-Q3&member=joint&account={joint}"
    page = logged_in_client.get(page_links(page)["Rules"]).content.decode()
    assert page_links(page)["Cashflow"] == f"/cashflow/?period=2026-Q3&member=joint&account={joint}"
