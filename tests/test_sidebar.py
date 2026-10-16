import re
from datetime import date

import pytest

from .conftest import review_queue_count

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def today(monkeypatch):
    monkeypatch.setattr("dashboard.periods.today", lambda: date(2026, 9, 28))


def this_month(page):
    """The sidebar's money in, spent and net for this month."""
    figures = re.search(r'<dl class="this-month"[^>]*>(.*?)</dl>', page, re.S)
    assert figures, "no figures for this month"
    return dict(re.findall(r"<dt>([^<]*)</dt>\s*<dd[^>]*>([^<]*)</dd>", figures[1]))


def test_the_sidebar_shows_this_months_in_spent_and_net(logged_in_client, household):
    page = logged_in_client.get("/transactions/").content.decode()

    assert "This month" in page
    assert this_month(page) == {"In": "3550.00", "Spent": "262.30", "Net": "3287.70"}
    assert review_queue_count(page) == 2


def test_this_months_figures_are_zero_on_an_empty_installation(logged_in_client):
    page = logged_in_client.get("/").content.decode()

    assert this_month(page) == {"In": "0.00", "Spent": "0.00", "Net": "0.00"}


def test_the_sidebar_offers_every_view_swapped_via_htmx(logged_in_client, household):
    page = logged_in_client.get("/cashflow/").content.decode()

    for url, label in [
        ("/spending/", "Spending by Category"),
        ("/cashflow/", "Cashflow"),
        ("/trends/", "Category trends"),
        ("/per-member/", "Per Member"),
        ("/money-flow/", "Money flow"),
        ("/transactions/", "Transactions"),
    ]:
        assert re.search(rf'<a class="nav[^"]*" href="{url}"[^>]*>{label}</a>', page), label
    assert re.search(r'<a class="nav on" href="/cashflow/" hx-get="/cashflow/"', page)


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
        r'<a class="nav ?" href="/transactions/" hx-get="/transactions/" hx-target="main"'
        r' hx-push-url="true">Transactions</a>',
        page,
    )


def test_transactions_are_swapped_in_alone_via_htmx(logged_in_client, household):
    swapped = logged_in_client.get(
        "/transactions/", headers={"HX-Request": "true"}
    ).content.decode()

    assert '<div class="shell">' not in swapped
    assert "<h2>Transactions</h2>" in swapped
    assert "<title>Transactions · Pursegraph</title>" in swapped
    assert "{#" not in swapped  # no template comment leaks
    # The sidebar comes along: Transactions highlighted, and the views no longer swapped into a view that has
    # left the page.
    assert '<aside id="sidebar" hx-swap-oob="true">' in swapped
    assert re.search(r'<a class="nav on" href="/transactions/"', swapped)
    assert re.search(r'<a class="nav" href="/cashflow/">Cashflow</a>', swapped)


def test_restoring_transactions_from_history_gets_the_whole_page(logged_in_client, household):
    restored = logged_in_client.get(
        "/transactions/", headers={"HX-Request": "true", "HX-History-Restore-Request": "true"}
    ).content.decode()

    assert '<div class="shell">' in restored


def test_transactions_swapped_in_leave_no_other_sidebar_link_highlighted(admin_client, household):
    swapped = admin_client.get(
        "/transactions/", headers={"HX-Request": "true", "Referer": "http://testserver/import/"}
    ).content.decode()

    assert re.findall(r'<a class="nav on" href="([^"]*)"', swapped) == ["/transactions/"]
    assert re.search(r'<a class="nav ?" href="/import/">Import</a>', swapped)
