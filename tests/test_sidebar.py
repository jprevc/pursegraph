import html
import re
from datetime import date

import pytest

from .conftest import review_queue_count

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def today(monkeypatch):
    monkeypatch.setattr("dashboard.periods.today", lambda: date(2026, 9, 28))


def text(fragment):
    """What `fragment` reads as, leaving out a count badge."""
    fragment = re.sub(r'<span class="badge[^>]*>[^<]*</span>', "", fragment)
    return html.unescape(re.sub(r"<[^>]+>", "", fragment)).strip()


def sidebar(page):
    aside = re.search(r'<aside class="sidebar"[^>]*>(.*?)</aside>', page, re.S)
    assert aside, "no sidebar"
    return aside[1]


def nav_items(fragment):
    """The navigation items in `fragment`, by label: where each goes and whether it is the current page."""
    return {
        text(label): (html.unescape(href), "aria-current" in attrs)
        for href, attrs, label in re.findall(
            r'<a class="nav" href="([^"]*)"([^>]*)>(.*?)</a>', fragment, re.S
        )
    }


def manage(page):
    group = re.search(r'<details class="manage"([^>]*)>(.*?)</details>', sidebar(page), re.S)
    assert group, "no Manage group"
    return group


def test_the_sidebar_offers_the_four_destinations_then_manage(logged_in_client, household):
    page = logged_in_client.get("/cashflow/").content.decode()

    destinations = sidebar(page).split('<details class="manage"')[0]
    assert list(nav_items(destinations)) == ["Dashboard", "Transactions", "Review queue", "Import"]
    assert list(nav_items(manage(page)[2])) == ["Rules"]
    assert ">Pursegraph<" not in sidebar(page)  # the wordmark is set as "Purse" and "graph"
    assert "Purse<span>graph</span>" in sidebar(page)


def test_admins_find_the_admin_pages_under_manage(admin_client, household):
    page = admin_client.get("/transactions/").content.decode()

    assert list(nav_items(manage(page)[2])) == [
        "Rules",
        "Categories",
        "LLM suggestions",
        "Accounts",
        "Members",
    ]


@pytest.mark.parametrize(
    "url, current",
    [
        ("/", "Dashboard"),
        ("/cashflow/", "Dashboard"),
        ("/money-flow/", "Dashboard"),
        ("/transactions/", "Transactions"),
        ("/review/", "Review queue"),
        ("/import/", "Import"),
        ("/rules/", "Rules"),
        ("/rules/new/", "Rules"),
        ("/accounts/new/", "Accounts"),
        ("/members/new/", "Members"),
    ],
)
def test_only_the_current_page_is_marked_current(admin_client, household, url, current):
    items = nav_items(sidebar(admin_client.get(url).content.decode()))

    assert [label for label, (_href, on) in items.items() if on] == [current]


@pytest.mark.parametrize("url", ["/", "/transactions/", "/review/", "/import/"])
def test_manage_is_closed_away_from_its_pages(admin_client, household, url):
    assert " open" not in manage(admin_client.get(url).content.decode())[1]


@pytest.mark.parametrize("url", ["/rules/", "/categories/", "/suggestions/", "/members/"])
def test_manage_is_open_on_its_pages(admin_client, household, url):
    assert " open" in manage(admin_client.get(url).content.decode())[1]


def test_the_review_queue_badge_is_hidden_when_the_queue_is_empty(logged_in_client):
    page = logged_in_client.get("/transactions/").content.decode()

    badges = re.findall(r'<span class="badge review-count"([^>]*)>', page)
    assert badges and all(" hidden" in b for b in badges)


def test_the_review_queue_badge_counts_on_the_sidebar_and_the_phone_tab(
    logged_in_client, household
):
    page = logged_in_client.get("/transactions/").content.decode()

    badges = re.findall(r'<span class="badge review-count"([^>]*)>(\d+)</span>', page)
    assert [(" hidden" in attrs, n) for attrs, n in badges] == [(False, "2"), (False, "2")]
    assert review_queue_count(page) == 2


def test_the_shell_has_no_this_month_figures(logged_in_client, household):
    page = logged_in_client.get("/transactions/").content.decode()

    assert "This month" not in page
    assert "this-month" not in page


def test_the_account_button_opens_the_theme_switch_and_log_out(admin_client, household):
    foot = re.search(
        r'<div class="sidebar-foot">(.*)', sidebar(admin_client.get("/").content.decode()), re.S
    )
    assert foot

    button = re.search(
        r'<button class="account"[^>]*popovertarget="account"[^>]*>(.*?)</button>', foot[1], re.S
    )
    assert button and "bor" in text(button[1]) and "Admin" in text(button[1])
    popover = re.search(
        r'<div id="account" class="account-pop" popover>(.*?)</div>\s*</div>', foot[1], re.S
    )
    assert popover
    assert 'name="theme"' in popover[1]
    assert re.search(r'<form method="post" action="/logout/">.*Log out.*</form>', popover[1], re.S)


def test_a_members_account_button_names_their_role(logged_in_client, household):
    button = re.search(
        r'<button class="account".*?</button>',
        sidebar(logged_in_client.get("/").content.decode()),
        re.S,
    )

    assert button and "Member" in text(button[0])


def theme_switches(page):
    return re.findall(r"<fieldset class=\"theme-switch\"([^>]*)>(.*?)</fieldset>", page, re.S)


def test_the_theme_switch_is_a_hidden_radio_group_of_light_system_and_dark(logged_in_client):
    switches = theme_switches(logged_in_client.get("/transactions/").content.decode())

    # One in the account popover, one in the phone More sheet, with names of their own.
    assert len(switches) == 2
    names = []
    for attrs, switch in switches:
        assert " hidden" in attrs  # until theme.js runs
        radios = re.findall(r'<input type="radio" name="([^"]*)" value="([^"]*)"', switch)
        assert [value for _name, value in radios] == ["light", "system", "dark"]
        names.append(radios[0][0])
        assert [text(label) for label in re.findall(r"<label>(.*?)</label>", switch, re.S)] == [
            "Light",
            "System",
            "Dark",
        ]
    assert names == ["theme", "theme-sheet"]


def test_the_saved_theme_applies_before_the_stylesheet_loads(logged_in_client):
    page = logged_in_client.get("/").content.decode()

    head = page.split("</head>")[0]
    assert '<html lang="en" data-theme="system">' in page
    assert head.index('localStorage.getItem("theme")') < head.index("pursegraph.css")
    assert "theme.js" in head


def test_login_honours_the_saved_theme_without_a_switch(client):
    page = client.get("/login/").content.decode()

    assert 'localStorage.getItem("theme")' in page
    assert not theme_switches(page)


def test_the_favicon_is_the_mark(client):
    assert re.search(
        r'<link rel="icon" href="/static/mark.svg" type="image/svg\+xml">',
        client.get("/login/").content.decode(),
    )


def tab_bar(page):
    bar = re.search(r'<nav class="tabbar"[^>]*>(.*?)</nav>', page, re.S)
    assert bar, "no tab bar"
    return bar[1]


def test_the_phone_tab_bar_has_dashboard_transactions_review_and_more(logged_in_client, household):
    page = logged_in_client.get("/review/").content.decode()

    bar = tab_bar(page)
    tabs = {
        text(label): "aria-current" in attrs
        for attrs, label in re.findall(r"<a([^>]*)>(.*?)</a>", bar, re.S)
    }
    assert tabs == {"Dashboard": False, "Transactions": False, "Review": True}
    assert re.search(r'<button type="button" popovertarget="more"[^>]*>.*More</button>', bar, re.S)


def test_the_more_sheet_holds_import_manage_the_theme_and_log_out(admin_client, household):
    page = admin_client.get("/").content.decode()

    sheet = re.search(
        r'<div id="more" class="sheet" popover role="dialog"[^>]*>(.*?)</form>', page, re.S
    )
    assert sheet
    assert list(nav_items(sheet[1])) == [
        "Import",
        "Rules",
        "Categories",
        "LLM suggestions",
        "Accounts",
        "Members",
    ]
    assert 'name="theme-sheet"' in sheet[1]
    assert "Log out" in sheet[1]


def test_more_is_current_on_the_pages_it_holds(logged_in_client, household):
    bar = tab_bar(logged_in_client.get("/import/").content.decode())

    assert re.search(r'<button type="button" popovertarget="more" aria-current="page"', bar)


def view_tabs(page):
    """The Dashboard's links to its views, by label: where each goes."""
    tabs = re.search(r'<nav class="tabs"[^>]*>(.*?)</nav>', page, re.S)
    assert tabs, "no view tabs"
    return {
        text(label): (html.unescape(href), "aria-current" in attrs)
        for href, attrs, label in re.findall(r'<a href="([^"]*)"([^>]*)>(.*?)</a>', tabs[1], re.S)
    }


def test_the_dashboard_offers_every_view_swapped_via_htmx(logged_in_client, household):
    page = logged_in_client.get("/cashflow/").content.decode()

    assert view_tabs(page) == {
        "Spending by Category": ("/spending/", False),
        "Cashflow": ("/cashflow/", True),
        "Category trends": ("/trends/", False),
        "Per Member": ("/per-member/", False),
        "Money flow": ("/money-flow/", False),
    }
    assert re.search(r'<a href="/trends/" hx-get="/trends/" hx-target="#view"', page)


def test_the_landing_page_is_spending(logged_in_client, household):
    assert view_tabs(logged_in_client.get("/").content.decode())["Spending by Category"][1]


@pytest.mark.parametrize("url", ["/cashflow/", "/trends/", "/per-member/", "/money-flow/"])
def test_an_empty_installation_asks_for_the_first_statement_on_every_view(logged_in_client, url):
    assert "Import your first Statement" in logged_in_client.get(url).content.decode()


@pytest.mark.parametrize("url", ["/cashflow/", "/trends/", "/per-member/", "/money-flow/"])
def test_every_view_is_swapped_in_alone_via_htmx(logged_in_client, household, url):
    swapped = logged_in_client.get(url, headers={"HX-Request": "true"}).content.decode()

    assert '<div class="shell">' not in swapped
    assert 'class="view-bar"' in swapped


@pytest.mark.parametrize("url", ["/cashflow/", "/import/"])
def test_the_sidebar_swaps_transactions_into_the_main_area_via_htmx(
    logged_in_client, household, url
):
    page = logged_in_client.get(url).content.decode()

    assert re.search(
        r'<a class="nav" href="/transactions/" hx-get="/transactions/" hx-target="main"'
        r' hx-push-url="true"',
        sidebar(page),
    )


def test_the_sidebar_opens_transactions_on_all_time(logged_in_client, household):
    page = logged_in_client.get("/cashflow/", {"period": "2026-Q3"}).content.decode()

    href, _on = nav_items(sidebar(page))["Transactions"]
    assert href == "/transactions/?dashboard=period%3D2026-Q3"  # carried for the way back only


def test_transactions_are_swapped_in_alone_via_htmx(logged_in_client, household):
    swapped = logged_in_client.get(
        "/transactions/", headers={"HX-Request": "true"}
    ).content.decode()

    assert '<div class="shell">' not in swapped
    assert "<h2>Transactions</h2>" in swapped
    assert "<title>Transactions · Pursegraph</title>" in swapped
    assert "{#" not in swapped  # no template comment leaks
    # The navigation comes along, with Transactions current.
    assert '<div id="nav" hx-swap-oob="true">' in swapped
    items = nav_items(sidebar(swapped))
    assert [label for label, (_href, on) in items.items() if on] == ["Transactions"]


def test_restoring_transactions_from_history_gets_the_whole_page(logged_in_client, household):
    restored = logged_in_client.get(
        "/transactions/", headers={"HX-Request": "true", "HX-History-Restore-Request": "true"}
    ).content.decode()

    assert '<div class="shell">' in restored


def test_a_skip_link_leads_to_the_main_area(logged_in_client, household):
    page = logged_in_client.get("/").content.decode()

    assert re.search(r'<a class="skip" href="#main">Skip to content</a>', page)
    assert '<main id="main" tabindex="-1">' in page


@pytest.mark.parametrize("url", ["/", "/review/"])
def test_no_template_comment_leaks_into_a_page_with_the_sidebar(logged_in_client, household, url):
    assert "{#" not in logged_in_client.get(url).content.decode()
