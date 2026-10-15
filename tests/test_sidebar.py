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

    assert "<aside>" not in swapped
    assert 'class="view-bar"' in swapped
