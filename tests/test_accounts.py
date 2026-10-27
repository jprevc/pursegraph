"""Account admin: the Accounts board, where admins create, edit and delete the Household's Accounts in place."""

import json
import re

import pytest

from ledger.importer import ImportRejected, check_statement, commit_statement
from ledger.models import Account, Rule, Transaction
from tests.conftest import board_row, make_account, page_text
from tests.test_import import FIXTURE as REVOLUT_CSV
from tests.test_import import upload as upload_csv
from tests.test_import import upload_without_account
from tests.test_import_pdf import IBAN as SPARKASSE_IBAN
from tests.test_import_pdf import pdf_text  # noqa: F401 (autouse fixture)
from tests.test_import_pdf import upload as upload_pdf

pytestmark = pytest.mark.django_db

OTHER_IBAN = "SI56020100001234582"


@pytest.fixture
def admin(django_user_model):
    return django_user_model.objects.get(username="bor")


def save_account(client, url="/accounts/new/", follow=False, **data):
    data.setdefault("name", "Ana's savings")
    data.setdefault("bank", "other")
    data.setdefault("ibans", OTHER_IBAN)
    return client.post(url, data, follow=follow)


def ibans_of(account):
    return sorted(account.ibans.values_list("iban", flat=True))


# Who may use the pages


@pytest.mark.parametrize(
    "url", ["/accounts/", "/accounts/new/", "/accounts/1/edit/", "/accounts/1/delete/"]
)
def test_non_admins_get_a_403(logged_in_client, member, url):
    make_account("Ana's Revolut", "revolut", member)

    assert logged_in_client.get(url).status_code == 403
    assert logged_in_client.post(url).status_code == 403


def test_members_can_still_create_an_account_during_import(logged_in_client):
    assert "New: " in board_row(upload_csv(logged_in_client).content.decode(), "Ana's Revolut")


def test_the_import_page_links_admins_to_the_accounts_page(admin_client, logged_in_client):
    assert 'href="/accounts/"' in admin_client.get("/import/").content.decode()
    assert 'href="/accounts/"' not in logged_in_client.get("/import/").content.decode()


def accounts_link(page):
    """The sidebar's admin link to the Accounts page, or None; its first group says whether it is current."""
    return re.search(
        r'<a class="nav" href="/accounts/"( aria-current="page")?><svg[^>]*>.*?</svg>Accounts</a>',
        page,
    )


def test_admins_find_accounts_among_the_sidebar_admin_links(admin_client, logged_in_client):
    link = accounts_link(admin_client.get("/transactions/").content.decode())
    assert link and not link[1]
    assert not accounts_link(logged_in_client.get("/transactions/").content.decode())


@pytest.mark.parametrize(
    "url", ["/accounts/", "/accounts/new/", "/accounts/{pk}/edit/", "/accounts/{pk}/delete/"]
)
def test_the_sidebar_accounts_link_is_highlighted_on_the_account_pages(admin_client, member, url):
    account = make_account("Ana's Revolut", "revolut", member)

    link = accounts_link(admin_client.get(url.format(pk=account.pk)).content.decode())
    assert link and link[1]


# Listing


def test_the_board_shows_each_account_with_its_bank_and_owners_by_name(admin_client, member, admin):
    member.first_name, member.last_name = "Ana", "Novak"
    member.save()
    joint = make_account("Joint Sparkasse", "sparkasse_si", member, [SPARKASSE_IBAN])
    joint.owners.add(admin)

    row = board_row(admin_client.get("/accounts/").content.decode(), "Joint Sparkasse")

    assert row.startswith("Joint Sparkasse Sparkasse SI · Ana Novak, bor Edit")
    assert "No Statements yet." in row


def test_the_board_reads_each_accounts_coverage_with_its_gaps(admin_client):
    upload_csv(admin_client)

    page = admin_client.get("/accounts/").content.decode()

    assert "Each Account with its Coverage, as on Import." in page_text(page)
    assert "Tracked from" in board_row(page, "Ana's Revolut")
    # A Gap leads to Import, where its Statement is dropped.
    assert re.search(
        r'<a class="stretch gap" href="/import/"[^>]*aria-label="Gap [^"]*: import a Statement"',
        page,
    )


HTMX = {"HX-Request": "true"}


def announced(response):
    return json.loads(response["HX-Trigger"])["announce"]


# Creating


def test_admin_registers_an_account_with_no_statements(admin_client, member):
    response = save_account(admin_client, owners=[member.pk])

    assert response.status_code == 302
    assert response["Location"] == "/accounts/"
    account = Account.objects.get(name="Ana's savings")
    assert account.bank == "other"
    assert list(account.owners.all()) == [member]
    assert ibans_of(account) == [OTHER_IBAN]


def test_a_joint_account_has_several_owners(admin_client, member, admin):
    save_account(admin_client, owners=[member.pk, admin.pk])

    account = Account.objects.get(name="Ana's savings")
    assert set(account.owners.all()) == {member, admin}


def test_an_account_needs_an_owner(admin_client):
    response = save_account(admin_client)

    assert response.status_code == 200
    assert not Account.objects.exists()


def test_several_ibans_are_given_one_per_line_and_tidied(admin_client, member):
    save_account(
        admin_client,
        owners=[member.pk],
        ibans=f"si56 0201 0000 1234 582\n\n  {SPARKASSE_IBAN}  \n",
    )

    account = Account.objects.get(name="Ana's savings")
    assert ibans_of(account) == sorted([OTHER_IBAN, SPARKASSE_IBAN])


def test_an_invalid_iban_is_refused(admin_client, member):
    response = save_account(admin_client, owners=[member.pk], ibans="SI56020100001234583")

    assert response.status_code == 200
    assert "SI56020100001234583" in response.content.decode()
    assert not Account.objects.exists()


def test_an_iban_already_on_another_account_is_refused(admin_client, member):
    make_account("Joint Sparkasse", "sparkasse_si", member, [SPARKASSE_IBAN])

    response = save_account(admin_client, owners=[member.pk], ibans=SPARKASSE_IBAN)

    assert response.status_code == 200
    assert "Joint Sparkasse" in response.content.decode()
    assert not Account.objects.filter(name="Ana's savings").exists()


def test_an_account_with_no_statements_needs_an_iban(admin_client, member):
    response = save_account(admin_client, owners=[member.pk], ibans="")

    assert response.status_code == 200
    assert not Account.objects.exists()


def test_an_account_of_a_bank_with_statements_may_have_no_iban(admin_client, member):
    save_account(admin_client, owners=[member.pk], bank="revolut", ibans="")

    assert Account.objects.get(name="Ana's savings").bank == "revolut"


def test_only_active_members_are_offered_as_owners(admin_client, member):
    member.is_active = False
    member.save()

    page = admin_client.get("/accounts/new/").content.decode()

    assert f'value="{member.pk}"' not in page


# Editing


def test_an_inactive_owner_stays_on_offer_for_their_account(admin_client, member):
    member.is_active = False
    member.save()
    account = make_account("Ana's Revolut", "revolut", member)

    page = admin_client.get(f"/accounts/{account.pk}/edit/").content.decode()

    assert re.search(rf'value="{member.pk}"[^>]* checked', page)


def test_admin_renames_an_account_and_changes_its_owners_and_ibans(admin_client, member, admin):
    account = make_account("Sparkasse", "sparkasse_si", member, [SPARKASSE_IBAN])

    response = save_account(
        admin_client,
        f"/accounts/{account.pk}/edit/",
        name="Joint Sparkasse",
        bank="sparkasse_si",
        owners=[admin.pk],
        ibans=f"{SPARKASSE_IBAN}\n{OTHER_IBAN}",
    )

    assert response.status_code == 302
    account.refresh_from_db()
    assert account.name == "Joint Sparkasse"
    assert list(account.owners.all()) == [admin]
    assert ibans_of(account) == sorted([SPARKASSE_IBAN, OTHER_IBAN])


def test_edit_opens_the_row_in_place_with_its_form_and_delete(admin_client, member):
    account = make_account("Ana's savings", "other", member, [OTHER_IBAN])

    response = admin_client.get(f"/accounts/{account.pk}/edit/", headers=HTMX)

    page = response.content.decode()
    assert page.lstrip().startswith("<title>Accounts · Pursegraph</title>")
    assert re.search(
        r'<div class="board-row" data-open>\s*<div class="who">\s*<div class="who-name"><h3>Ana&#x27;s savings',
        page,
    )
    assert "Several owners make it a joint Account, shown in the Joint bucket." in page
    assert f'hx-get="/accounts/{account.pk}/delete/"' in page


def test_the_first_field_takes_the_focus_when_the_row_opens(admin_client, member):
    account = make_account("Ana's savings", "other", member, [OTHER_IBAN])

    page = admin_client.get(f"/accounts/{account.pk}/edit/", headers=HTMX).content.decode()

    assert re.search(r'<input[^>]*name="name"[^>]*data-focus', page)


def test_saving_closes_the_row_and_says_saved_beside_the_name(admin_client, member):
    account = make_account("Sparkasse", "sparkasse_si", member, [SPARKASSE_IBAN])

    response = admin_client.post(
        f"/accounts/{account.pk}/edit/",
        {
            "name": "Joint Sparkasse",
            "bank": "sparkasse_si",
            "owners": [member.pk],
            "ibans": SPARKASSE_IBAN,
        },
        headers=HTMX,
    )

    page = response.content.decode()
    assert "data-open" not in page
    assert board_row(page, "Joint Sparkasse").startswith("Joint Sparkasse Saved")
    assert '<span class="status saved" role="status">' in page
    assert re.search(rf'href="/accounts/{account.pk}/edit/"[^>]*data-focus>Edit</a>', page)
    assert announced(response) == "Saved Joint Sparkasse."


def test_without_js_a_save_goes_back_to_the_board_saying_so(admin_client, member):
    response = save_account(admin_client, owners=[member.pk], follow=True)

    assert "Saved Ana&#x27;s savings." in response.content.decode()


def test_a_save_that_fails_keeps_the_row_open_and_focuses_what_to_fix(admin_client, member):
    account = make_account("Ana's savings", "other", member, [OTHER_IBAN])

    response = admin_client.post(
        f"/accounts/{account.pk}/edit/",
        {"name": "Ana's savings", "bank": "other", "ibans": OTHER_IBAN},
        headers=HTMX,
    )

    page = response.content.decode()
    assert '<div class="board-row" data-open>' in page
    assert re.search(r'<input type="checkbox" name="owners"[^>]*data-focus', page)
    assert announced(response) == "Choose at least one Member."


def test_cancel_closes_the_row_and_gives_its_edit_the_focus(admin_client, member):
    account = make_account("Ana's savings", "other", member, [OTHER_IBAN])

    page = admin_client.get(f"/accounts/?closed={account.pk}", headers=HTMX).content.decode()

    assert "data-open" not in page
    assert re.search(rf'href="/accounts/{account.pk}/edit/"[^>]*data-focus>Edit</a>', page)


def test_new_account_opens_a_row_of_its_own_last(admin_client, member):
    make_account("Ana's savings", "other", member, [OTHER_IBAN])

    page = admin_client.get("/accounts/new/", headers=HTMX).content.decode()

    assert page.index("Ana&#x27;s savings") < page.index("<h3>New Account</h3>")
    assert 'hx-post="/accounts/new/"' in page


def test_the_edit_page_shows_the_current_values(admin_client, member):
    account = make_account("Joint Sparkasse", "sparkasse_si", member, [SPARKASSE_IBAN])

    page = admin_client.get(f"/accounts/{account.pk}/edit/").content.decode()

    assert 'value="Joint Sparkasse"' in page
    assert SPARKASSE_IBAN in page


def test_removing_an_iban_frees_it(admin_client, member):
    account = make_account("Sparkasse", "sparkasse_si", member, [SPARKASSE_IBAN, OTHER_IBAN])

    save_account(
        admin_client,
        f"/accounts/{account.pk}/edit/",
        name="Sparkasse",
        bank="sparkasse_si",
        owners=[member.pk],
        ibans=OTHER_IBAN,
    )

    assert ibans_of(account) == [OTHER_IBAN]
    response = save_account(admin_client, owners=[member.pk], ibans=SPARKASSE_IBAN)
    assert response.status_code == 302


def test_an_account_keeps_its_bank_while_it_has_statements(admin_client, member):
    upload_pdf(admin_client, account="new", new_account_name="Sparkasse")
    account = Account.objects.get(name="Sparkasse")

    response = save_account(
        admin_client,
        f"/accounts/{account.pk}/edit/",
        name="Sparkasse",
        bank="other",
        owners=[member.pk],
        ibans=SPARKASSE_IBAN,
    )

    assert response.status_code == 200
    account.refresh_from_db()
    assert account.bank == "sparkasse_si"


# An Account with no Statements


def test_an_account_with_no_statements_cant_receive_one(admin_client, member):
    make_account("Ana's savings", "other", member, [SPARKASSE_IBAN])

    page = upload_pdf(admin_client).content.decode()

    said = page_text(page)
    assert "Not imported" in said
    assert "Ana's savings takes no Statements" in said
    assert "Choose another Account, or ask an admin to change its bank." in said
    assert not Account.objects.get(name="Ana's savings").statements.exists()


def test_an_account_with_no_statements_isnt_offered_at_import(logged_in_client, member):
    make_account("Ana's savings", "other", member, [OTHER_IBAN])

    page = upload_without_account(logged_in_client)

    [account_step] = re.findall(r"Choose the Account.*?</form>", page, re.S)
    assert "Ana&#x27;s savings" not in account_step


def test_an_import_rechecks_the_account_once_it_holds_it(member):
    """An admin may make the Account an Account with no Statements while the import is under way."""
    account = make_account("Ana's Revolut", "revolut", member)
    checked = check_statement(content=REVOLUT_CSV, filename="revolut.csv")
    Account.objects.filter(pk=account.pk).update(bank="other")

    with pytest.raises(ImportRejected) as rejected:
        commit_statement(checked, member=member, account=account)

    assert rejected.value.heading == "Ana's Revolut takes no Statements"
    assert not account.statements.exists()


# Deleting


def test_admin_deletes_an_account_with_no_statements(admin_client, member):
    account = make_account("Ana's savings", "other", member, [OTHER_IBAN])

    response = admin_client.post(f"/accounts/{account.pk}/delete/")

    assert response.status_code == 302
    assert not Account.objects.exists()


def test_deleting_asks_first_and_names_the_rules_that_go_with_it(admin_client, member):
    account = make_account("Ana's savings", "other", member, [OTHER_IBAN])
    Rule.objects.create(description_contains="SAVINGS", account=account)

    page = admin_client.get(f"/accounts/{account.pk}/delete/").content.decode()

    assert "Delete “Ana's savings”? 1 Rule only for this Account goes with it." in page_text(page)
    assert Account.objects.exists()


def test_deleting_confirms_inline_with_htmx(admin_client, member):
    account = make_account("Ana's savings", "other", member, [OTHER_IBAN])

    page = admin_client.get(f"/accounts/{account.pk}/delete/", headers=HTMX).content.decode()

    assert "<html" not in page
    assert "No Rules are only for this Account." in page
    assert '<button type="button" data-keep>Keep it</button>' in page
    assert '<button type="submit" class="primary" data-focus>Delete Account</button>' in page


def test_deleting_with_htmx_swaps_in_the_board_without_it(admin_client, member):
    account = make_account("Ana's savings", "other", member, [OTHER_IBAN])

    response = admin_client.post(f"/accounts/{account.pk}/delete/", headers=HTMX)

    assert "Ana&#x27;s savings" not in response.content.decode()
    assert announced(response) == "Deleted Ana's savings."


def test_an_account_with_statements_says_why_it_cant_be_deleted(admin_client):
    upload_csv(admin_client)
    account = Account.objects.get()

    page = admin_client.get(f"/accounts/{account.pk}/edit/").content.decode()

    assert "Can't be deleted while it has 1 Statement. Delete it first." in page_text(page)
    assert f"/accounts/{account.pk}/delete/" not in page


def test_deleting_an_account_is_refused_while_it_has_statements(admin_client):
    upload_csv(admin_client)
    account = Account.objects.get()

    response = admin_client.post(f"/accounts/{account.pk}/delete/", follow=True)

    assert Account.objects.filter(pk=account.pk).exists()
    assert "has Statements" in response.content.decode()


# Recognising Transfers to IBANs added later

REVOLUT_IBAN = "LT633250001234567890"


def test_payments_already_imported_to_an_added_iban_become_transfers(admin_client, admin):
    """The Sparkasse fixture pays 1500.00 to REVOLUT_IBAN, as "Ana Novak"."""
    make_account("Sparkasse", "sparkasse_si", admin, [SPARKASSE_IBAN])
    upload_pdf(admin_client)
    assert Transaction.objects.get(description="Ana Novak").is_unresolved

    save_account(admin_client, owners=[admin.pk], ibans=REVOLUT_IBAN)

    payment = Transaction.objects.get(description="Ana Novak")
    assert payment.is_transfer
    assert payment.source == "iban"
    assert Transaction.objects.filter(is_transfer=True).count() == 1
