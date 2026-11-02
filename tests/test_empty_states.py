"""Empty pages (docs/design/empty-states.md): one centred block that says why the page is empty and what fills it."""

import re

import pytest

from tests.conftest import PASSWORD, page_text

pytestmark = pytest.mark.django_db


def empty_block(page):
    """The empty block: its heading, its sentence, and each action as (label, href, whether it is primary)."""
    block = re.search(r'<section [^>]*class="panel empty-block"[^>]*>(.*?)</section>', page, re.S)
    assert block, "no empty block"
    heading = re.search(r"<h2[^>]*>(.*?)</h2>", block[1], re.S)
    sentence = re.search(r"<p>(.*?)</p>", block[1], re.S)
    actions = [
        (page_text(label), href, "primary" in cls)
        for cls, href, label in re.findall(
            r'<a class="([^"]*)" href="([^"]*)"[^>]*>(.*?)</a>', block[1], re.S
        )
    ]
    assert heading and sentence
    return page_text(heading[1]), page_text(sentence[1]), actions


def test_accounts_before_any_says_importing_creates_them(admin_client):
    heading, sentence, actions = empty_block(admin_client.get("/accounts/").content.decode())

    assert heading == "No Accounts yet"
    assert sentence.startswith(
        "There's nothing to add first: importing a Statement creates its Account"
    )
    assert sentence.endswith("so that money moved there counts as a Transfer.")
    assert actions == [
        ("Import Statements", "/import/", True),
        ("Add an Account without Statements", "/accounts/new/", False),
    ]


def test_adding_an_account_from_the_empty_block_opens_the_new_row_in_place(admin_client):
    page = admin_client.get("/accounts/").content.decode()

    assert re.search(r'id="board"[^>]*class="panel empty-block"', page)
    assert 'hx-get="/accounts/new/" hx-target="#board" hx-swap="outerHTML">Add an Account' in page


def test_imports_coverage_before_any_account_says_each_statement_adds_its_account(logged_in_client):
    heading, sentence, actions = empty_block(logged_in_client.get("/import/").content.decode())

    assert heading == "No Accounts yet"
    assert sentence.startswith(
        "Each Statement adds its Account the first time, from the IBAN printed on it."
    )
    assert sentence.endswith("Each Member usually imports their own bank's Statements.")
    assert actions == []


def test_members_with_only_the_first_admin_asks_to_invite_the_rest(admin_client):
    page = admin_client.get("/members/").content.decode()

    heading, sentence, actions = empty_block(page)
    assert heading == "Invite the rest of the Household"
    assert sentence.startswith("You're the only Member so far.")
    assert actions == [("Invite a Member", "/members/new/", True)]
    assert "<td>bor</td>" in page  # the one row stays


def test_members_with_a_second_member_has_no_empty_block(admin_client, django_user_model):
    django_user_model.objects.create_user(username="luka", password=PASSWORD)

    assert "empty-block" not in admin_client.get("/members/").content.decode()


def test_rules_before_any_points_at_make_a_rule(logged_in_client):
    heading, sentence, actions = empty_block(logged_in_client.get("/rules/").content.decode())

    assert heading == "No Rules yet"
    assert sentence.startswith(
        "A Rule categorizes matching Transactions at import, or marks them Transfers."
    )
    assert (
        "The quickest way to make one is “Make a Rule” after you correct a Transaction" in sentence
    )
    assert actions == [("Write a Rule", "/rules/new/", True)]


def test_transactions_before_any_import_says_what_fills_the_page(logged_in_client):
    heading, sentence, actions = empty_block(
        logged_in_client.get("/transactions/").content.decode()
    )

    assert heading == "No Transactions yet"
    assert (
        sentence
        == "Every Transaction on an imported Statement is listed here, to search, filter and correct."
    )
    assert actions == [("Import Statements", "/import/", True)]


@pytest.mark.parametrize(
    "url", ["/accounts/", "/import/", "/members/", "/rules/", "/transactions/"]
)
def test_an_empty_page_keeps_its_title_row(admin_client, url):
    page = admin_client.get(url).content.decode()

    assert re.search(r'<h1 tabindex="-1">[^<]+</h1>', page)


def test_a_deactivated_member_doesnt_count_as_the_rest_of_the_household(
    admin_client, django_user_model
):
    django_user_model.objects.create_user(username="luka", password=PASSWORD, is_active=False)

    heading, _sentence, _actions = empty_block(admin_client.get("/members/").content.decode())

    assert heading == "Invite the rest of the Household"
