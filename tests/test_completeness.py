"""Period completeness (docs/design/period-completeness.md): the Dashboard reads Coverage, for the Accounts the
filters include, to say how complete a period's numbers are."""

import html
import re
from datetime import date
from itertools import count

import pytest

from ledger.models import Account, Category, Statement

from .conftest import EUR, make_account, view_chart

pytestmark = pytest.mark.django_db

TODAY = date(2026, 10, 17)
_sha = count()


@pytest.fixture(autouse=True)
def today(monkeypatch):
    monkeypatch.setattr("dashboard.periods.today", lambda: TODAY)


def statement(account, start, end, member):
    return Statement.objects.create(
        account=account,
        format=Statement.Format.CSV,
        period_start=start,
        period_end=end,
        opening_balance=0,
        closing_balance=0,
        imported_by=member,
        sha256=f"{next(_sha):064x}",
        file=f"test/{account.pk}-{start}.csv",
    )


@pytest.fixture
def covered(household):
    """Ana's Sparkasse is covered from 1 Jan 2026 up to today, the Joint Revolut from 1 Feb, and Marko's N26 from
    1 Jan to 30 Sep, without July."""
    ana = household["ana"]
    accounts = {a.name: a for a in Account.objects.all()}
    statement(accounts["Ana's Sparkasse"], date(2026, 1, 1), TODAY, ana)
    statement(accounts["Joint Revolut"], date(2026, 2, 1), TODAY, ana)
    statement(accounts["Marko's N26"], date(2026, 1, 1), date(2026, 6, 30), ana)
    statement(accounts["Marko's N26"], date(2026, 8, 1), date(2026, 9, 30), ana)
    return {**household, **accounts}


def found(pattern, text):
    """The first group of `pattern` in `text`, which must be there."""
    match = re.search(pattern, text, re.S)
    assert match, f"no {pattern!r}"
    return match[1]


def page(client, url, params=None):
    return client.get(url, params or {}).content.decode()


def previous_link(content):
    return re.search(r'<a class="step"[^>]*aria-label="Previous period"', content)


def test_the_stepper_stops_at_the_households_first_coverage_day_whatever_the_filters(
    logged_in_client, covered
):
    assert not previous_link(page(logged_in_client, "/spending/", {"period": "2026-01"}))
    assert not previous_link(page(logged_in_client, "/spending/", {"period": "2026-Q1"}))
    joint = covered["Joint Revolut"]
    assert previous_link(
        page(logged_in_client, "/spending/", {"period": "2026-02", "account": joint.pk})
    )


LAST_12 = {"period": "last12-2026-10"}


def test_each_month_of_a_chart_carries_its_state_and_why(logged_in_client, covered):
    chart = view_chart(page(logged_in_client, "/cashflow/", LAST_12), "cashflow")
    assert chart["months"][0] == "Nov 2025"
    assert chart["states"] == [
        *["not_tracked"] * 2,
        "partly_tracked",
        *["complete"] * 5,
        "partial",
        "complete",
        "complete",
        "partial",
    ]
    reasons = dict(zip(chart["months"], chart["reasons"], strict=True))
    assert reasons["Nov 2025"] == "No Statements yet"
    assert reasons["Jan 2026"] == "Joint Revolut is tracked from 1 Feb 2026"
    assert reasons["Jul 2026"] == "No Statements from Marko's N26 for 1–31 Jul"
    assert reasons["Oct 2026"] == "No Statements from Marko's N26 for 1–17 Oct"
    assert reasons["Aug 2026"] == ""


def test_only_the_accounts_the_filters_include_count(logged_in_client, covered):
    ana = covered["ana"].pk
    chart = view_chart(page(logged_in_client, "/cashflow/", {**LAST_12, "member": ana}), "cashflow")
    states = dict(zip(chart["months"], chart["states"], strict=True))
    assert (states["Jan 2026"], states["Jul 2026"], states["Oct 2026"]) == (
        "complete",
        "complete",
        "in_progress",
    )
    assert chart["reasons"][-1] == "So far, to 17 Oct"


def test_a_not_tracked_month_has_no_figures_rather_than_zeros(logged_in_client, covered):
    cashflow = view_chart(page(logged_in_client, "/cashflow/", LAST_12), "cashflow")
    assert cashflow["in"][:3] == [None, None, 0]
    assert cashflow["net"][:2] == [None, None]
    trends = view_chart(page(logged_in_client, "/trends/", LAST_12), "trends")
    assert all(line["data"][:2] == [None, None] for line in trends["lines"])
    assert trends["states"][:3] == ["not_tracked", "not_tracked", "partly_tracked"]


def header_line(content):
    """The words of the line between the view bar and the stat tiles, if any."""
    line = re.search(r'<p class="completeness">(.*?)</p>', content, re.S)
    return line and re.sub(r"[ \n]+", " ", html.unescape(re.sub(r"<[^>]+>", "", line[1]))).strip()


def test_the_header_line_names_the_gaps_and_who_is_tracked_from_when(logged_in_client, covered):
    content = page(logged_in_client, "/cashflow/", LAST_12)
    assert header_line(content) == (
        "Incomplete: no Statements yet from Marko's N26 for 1–31 Jul, 1–17 Oct"
        " · Joint Revolut is tracked from 1 Feb 2026"
        f" · 12,30{EUR} (1\u00a0%) still awaiting review"
    )
    line = found(r'<p class="completeness">(.*?)</p>', content)
    assert re.search(r'<a href="/import/[^"]*">Marko&#x27;s N26</a>', line)
    assert re.search(r'<a href="/review/[^"]*">12,30', line)


def test_the_header_line_says_how_much_still_awaits_review(logged_in_client, covered):
    content = page(logged_in_client, "/spending/", {"period": "2026-09"})
    assert header_line(content) == f"12,30{EUR} (5\u00a0%) still awaiting review"


def test_a_complete_or_merely_running_period_has_no_header_line(logged_in_client, covered):
    assert header_line(page(logged_in_client, "/spending/", {"period": "2026-08"})) is None
    ana = covered["ana"].pk
    running = page(logged_in_client, "/spending/", {"period": "2026-10", "member": ana})
    assert header_line(running) is None


def test_past_two_accounts_the_rest_of_the_gaps_collapse(logged_in_client, covered):
    for name in ("Ana's N26", "Marko's Revolut", "Joint N26"):
        account = make_account(name, "n26", covered["ana"])
        statement(account, date(2026, 1, 1), date(2026, 6, 30), covered["ana"])
    content = page(logged_in_client, "/spending/", {"period": "2026-07"})
    assert header_line(content) == (
        "Incomplete: no Statements yet from Ana's N26 for 1–31 Jul, Joint N26 for 1–31 Jul"
        " and 2 more, Marko's N26 for 1–31 Jul and Marko's Revolut for 1–31 Jul"
    )
    assert re.search(
        r'<button type="button" class="link" aria-expanded="false" data-more>', content
    )


def words(fragment):
    return re.sub(r"[ \n]+", " ", html.unescape(re.sub(r"<[^>]+>", " ", fragment))).strip()


def table_rows(content):
    """Each row of a view's table as the words of its cells, head row first."""
    table = found(r'<table class="view-table">(.*?)</table>', content)
    return [
        [words(cell) for cell in re.findall(r"<t[hd][^>]*>(.*?)</t[hd]>", row, re.S)]
        for row in re.findall(r"<tr[^>]*>(.*?)</tr>", table, re.S)
    ]


def test_a_tables_months_carry_their_state_in_words(logged_in_client, covered):
    rows = {row[0]: row[1:] for row in table_rows(page(logged_in_client, "/cashflow/", LAST_12))}
    assert rows["Nov 2025"] == ["—", "—", "—"]
    assert "Jan 2026 (partly tracked)" in rows
    assert "Jul 2026 (partial)" in rows
    assert "Oct 2026 (partial)" in rows
    assert rows["Aug 2026"] == [f"1.500,00{EUR}", f"999,00{EUR}", f"+501,00{EUR}"]

    ana = covered["ana"].pk
    filtered = table_rows(page(logged_in_client, "/cashflow/", {**LAST_12, "member": ana}))
    assert filtered[-2][0] == "Oct 2026 (so far)"


def test_category_trends_columns_carry_their_state(logged_in_client, covered):
    head, food, *_rest = table_rows(page(logged_in_client, "/trends/", LAST_12))
    assert head[1:4] == ["Nov", "Dec", "Jan (partly tracked)"]
    assert head[9] == "Jul (partial)"
    assert food[1:4] == ["—", "—", f"0,00{EUR}"]


def comparisons(content):
    return [words(c) for c in re.findall(r'<p class="compare">(.*?)</p>', content, re.S)]


def test_a_tile_does_not_compare_with_an_incomplete_period(logged_in_client, covered):
    def compared(period):
        return set(comparisons(page(logged_in_client, "/spending/", {"period": period})))

    assert compared("2026-07") == {"Not comparable: July is incomplete"}
    assert compared("2026-08") == {"Not comparable: July is incomplete"}
    assert compared("2026-01") == {"Not comparable: January is incomplete"}
    assert compared("2026-02") == {"Not comparable: January is incomplete"}
    assert compared("2026-Q3") == {"Not comparable: July is incomplete"}
    # The month that makes it incomplete, not the Not tracked ones before it.
    assert compared("last12-2026-10") == {"Not comparable: July is incomplete"}
    assert compared("2026-03") == {"Same as February"}


def test_the_drill_down_title_carries_the_periods_qualifier(logged_in_client, covered):
    food = Category.objects.get(name="Food").pk

    def title(period):
        content = page(
            logged_in_client, "/spending/transactions/", {"period": period, "category": food}
        )
        return words(found(r'<h2 id="drill-heading">(.*?)</h2>', content))

    assert title("2026-10") == "Food · October 2026 (partial)"
    assert title("2026-09") == "Food · September 2026"


def not_tracked_card(content):
    card = re.search(r'<section class="panel not-tracked"(.*?)</section>', content, re.S)
    return card and card[1]


def test_a_period_wholly_before_any_coverage_shows_the_not_tracked_card(logged_in_client, covered):
    content = page(logged_in_client, "/spending/", {"period": "2025-11"})
    card = not_tracked_card(content)
    assert "No Statements cover November 2025 yet" in words(card)
    assert (
        "Ana's Sparkasse, Joint Revolut and Marko's N26 are tracked from 1 Jan 2026."
        " Before that there are no numbers, not zeros."
    ) in words(card)
    assert re.search(
        r'<a class="button primary" href="/spending/\?period=2026-01"[^>]*>Go to January 2026', card
    )
    assert "Show all Members" not in card
    assert re.search(
        r'<a class="button ghost" href="/import/[^"]*">Import an earlier Statement', card
    )
    assert 'class="tiles"' not in content
    assert "data-chart" not in content


def test_the_not_tracked_card_names_only_the_accounts_the_filters_include(
    logged_in_client, covered
):
    joint = covered["Joint Revolut"].pk
    content = page(logged_in_client, "/cashflow/", {"period": "2026-01", "account": joint})
    card = not_tracked_card(content)
    assert "No Statements cover January 2026 yet" in words(card)
    assert "Joint Revolut is tracked from 1 Feb 2026." in words(card)
    assert "Go to February 2026" in card
    assert re.search(
        r'<a class="button" href="/cashflow/\?period=2026-01"[^>]*>Show all Members', card
    )


def test_the_not_tracked_card_has_a_coverage_timeline(logged_in_client, covered):
    card = not_tracked_card(page(logged_in_client, "/spending/", {"period": "2025-11"}))
    # Read out as a list: each included Account and its stretches with Statements, from the Household's first
    # Coverage month to the running month.
    timeline = found(r'<ul class="sr">(.*?)</ul>', card)
    assert [words(item) for item in re.findall(r"<li>(.*?)</li>", timeline, re.S)] == [
        "Ana's Sparkasse: has Statements Jan – Oct 2026",
        "Joint Revolut: has Statements Feb – Oct 2026",
        "Marko's N26: has Statements Jan – Jun 2026, Aug – Sep 2026",
    ]


def test_a_partly_covered_period_shows_its_view(logged_in_client, covered):
    content = page(logged_in_client, "/spending/", {"period": "2026-01"})
    assert not not_tracked_card(content)
    assert 'class="tiles"' in content
