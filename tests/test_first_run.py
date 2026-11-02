"""First run (docs/design/empty-states.md): until the Household's first Statement, the Dashboard is Get started and
the shell offers only what works."""

import re

import pytest
from django.test import Client

from ledger.models import Account, Transaction
from tests.conftest import PASSWORD, page_text
from tests.test_import import upload
from tests.test_sidebar import manage, nav_items, sidebar, tab_bar, text

pytestmark = pytest.mark.django_db


def steps(page):
    """Get started's step cards, in order: each card's class and words."""
    return [
        (cls.strip(), page_text(body))
        for cls, body in re.findall(r'<li class="step([^"]*)">(.*?)</li>', page, re.S)
    ]


def progress(page):
    line = re.search(r'<p class="setup-progress"[^>]*>(.*?)</p>', page, re.S)
    assert line, "no progress line"
    return page_text(line[1])


def test_the_dashboard_is_get_started_until_the_first_statement(admin_client):
    page = admin_client.get("/").content.decode()

    assert '<h1 tabindex="-1">Set up the Household</h1>' in page
    assert (
        "Four steps to the first Dashboard. This page becomes the Dashboard after the first import."
        in page
    )
    assert "<title>Get started · Pursegraph</title>" in page
    assert progress(page) == "1 of 4 done"
    assert [s[0] for s in steps(page)] == ["done", "", "", "later"]
    assert steps(page)[0][1] == "Done: Pursegraph is installed and you are its first admin"
    assert steps(page)[1][1].startswith("2 Import a Statement Upload a bank Statement")
    assert "Any Member · usually their own bank Import" in steps(page)[1][1]
    assert steps(page)[2][1].endswith("Admins Invite")
    assert steps(page)[3][1].startswith("4 Sort the Review queue")
    assert "Available after the first import." in steps(page)[3][1]


@pytest.mark.parametrize(
    "url", ["/", "/spending/", "/cashflow/", "/trends/", "/per-member/", "/money-flow/"]
)
def test_every_dashboard_view_is_get_started_until_the_first_statement(logged_in_client, url):
    assert "Set up the Household" in logged_in_client.get(url).content.decode()


def test_the_step_actions_open_import_and_members(admin_client):
    page = admin_client.get("/").content.decode()

    assert re.search(r'<a class="button primary" href="/import/">.*?Import</a>', page, re.S)
    assert '<a class="button" href="/members/">Invite</a>' in page


def test_inviting_is_done_once_a_second_active_member_exists(admin_client, django_user_model):
    django_user_model.objects.create_user(username="luka", password=PASSWORD)

    page = admin_client.get("/").content.decode()

    assert progress(page) == "2 of 4 done"
    assert [s[0] for s in steps(page)] == ["done", "", "done", "later"]
    assert '<a class="button" href="/members/">Invite</a>' not in page


def test_a_deactivated_member_doesnt_count_as_invited(admin_client, django_user_model):
    django_user_model.objects.create_user(username="luka", password=PASSWORD, is_active=False)

    assert progress(admin_client.get("/").content.decode()) == "1 of 4 done"


def test_a_member_who_isnt_an_admin_doesnt_see_the_invite_step(logged_in_client):
    page = logged_in_client.get("/").content.decode()

    assert "Three steps to the first Dashboard." in page
    assert progress(page) == "1 of 3 done"
    assert "Invite the other Members" not in page
    assert [s[1].split(" ", 1)[1][:18] for s in steps(page)][1:] == [
        "Import a Statement",
        "Sort the Review qu",
    ]


def test_the_first_import_ends_setup_mode(logged_in_client):
    upload(logged_in_client)

    page = logged_in_client.get("/").content.decode()

    assert "Set up the Household" not in page
    assert list(nav_items(sidebar(page).split('<details class="manage"')[0])) == [
        "Dashboard",
        "Transactions",
        "Review queue",
        "Import",
    ]


def test_the_sidebar_in_setup_mode_offers_only_what_works(admin_client):
    page = admin_client.get("/import/").content.decode()

    destinations = sidebar(page).split('<details class="manage"')[0]
    assert list(nav_items(destinations)) == ["Get started", "Import"]
    assert list(nav_items(manage(page)[2])) == ["Categories", "Accounts", "Members"]
    assert "Transactions, the Review queue and Rules appear after the first import." in page_text(
        sidebar(page)
    )


def test_a_member_in_setup_mode_has_no_manage_group_but_the_note(logged_in_client):
    page = logged_in_client.get("/import/").content.decode()

    assert '<details class="manage"' not in sidebar(page)
    assert "Transactions, the Review queue and Rules appear after the first import." in page_text(
        sidebar(page)
    )


def test_get_started_is_the_current_item_on_the_dashboard(admin_client):
    items = nav_items(sidebar(admin_client.get("/").content.decode()))

    assert items["Get started"] == ("/", True)


def test_the_phone_tab_bar_in_setup_mode_has_get_started_import_and_more(admin_client):
    bar = tab_bar(admin_client.get("/").content.decode())

    tabs = [text(label) for label in re.findall(r"<a[^>]*>(.*?)</a>", bar, re.S)]
    assert tabs == ["Get started", "Import"]
    assert 'popovertarget="more"' in bar
    assert 'class="tabbar setup"' in admin_client.get("/").content.decode()


def test_the_more_sheet_in_setup_mode_holds_manage_without_import(admin_client):
    page = admin_client.get("/").content.decode()

    sheet = re.search(
        r'<div id="more" class="sheet" popover role="dialog"[^>]*>(.*?)</form>', page, re.S
    )
    assert sheet
    assert list(nav_items(sheet[1])) == ["Categories", "Accounts", "Members"]


@pytest.fixture
def luka_client(household, django_user_model):
    """Luka, a Member who owns no Account alone, so has no Bucket."""
    luka = django_user_model.objects.create_user(
        username="luka", first_name="Luka", password=PASSWORD
    )
    household["luka"] = luka
    client = Client()
    client.force_login(luka)
    return client


def first_steps(page):
    card = re.search(r'<section class="panel first-steps"[^>]*>(.*?)</section>', page, re.S)
    return card and card[1]


def test_a_member_without_a_bucket_sees_their_first_steps_above_the_tiles(luka_client):
    page = luka_client.get("/spending/", {"period": "2026-09"}).content.decode()

    card = first_steps(page)
    assert card
    assert page.index('class="panel first-steps"') < page.index('class="tiles')
    assert "Your first steps, Luka" in page_text(card)
    assert "1 Import your own Statements Sparkasse, N26 or Revolut." in page_text(card)
    assert "you get your own bucket in Per Member." in page_text(card)
    assert (
        "2 Help with the Review queue 2 Transactions wait for a Member to decide. Open"
        in page_text(card)
    )
    assert re.search(r'<a class="button primary" href="/import/">.*?Import</a>', card, re.S)
    assert '<a class="button" href="/review/">Open</a>' in card


def test_first_steps_can_be_hidden_in_this_browser(luka_client, household):
    page = luka_client.get("/").content.decode()

    assert re.search(
        r'<button type="button" class="ghost js-only" data-hide-first-steps>Hide</button>', page
    )
    # Applied before first paint, as the theme is.
    assert f'localStorage.getItem("first-steps-hidden:{household["luka"].pk}")' in page


def test_first_steps_leave_out_the_review_queue_when_it_is_empty(luka_client):
    Transaction.objects.unresolved().update(is_transfer=True)

    card = first_steps(luka_client.get("/").content.decode())

    assert "Import your own Statements" in page_text(card)
    assert "Review queue" not in page_text(card)


def test_a_member_with_a_bucket_has_no_first_steps(logged_in_client, household):
    assert not first_steps(logged_in_client.get("/").content.decode())


def test_owning_only_a_joint_account_is_no_bucket(luka_client, household):
    joint = Account.objects.get(name="Joint Revolut")
    joint.owners.add(household["luka"])

    assert first_steps(luka_client.get("/").content.decode())
