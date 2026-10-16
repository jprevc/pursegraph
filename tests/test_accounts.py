"""Account admin: admins list, create, edit and delete the Household's Accounts."""

import re

import pytest

from ledger.importer import ImportRejected, check_statement, commit_statement
from ledger.models import Account, Rule, Transaction
from tests.conftest import make_account
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


def save_account(client, url="/accounts/new/", **data):
    data.setdefault("name", "Ana's savings")
    data.setdefault("bank", "other")
    data.setdefault("ibans", OTHER_IBAN)
    return client.post(url, data)


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
    assert "Imported into Ana&#x27;s Revolut" in upload_csv(logged_in_client).content.decode()


def test_the_import_page_links_admins_to_the_accounts_page(admin_client, logged_in_client):
    assert 'href="/accounts/"' in admin_client.get("/import/").content.decode()
    assert 'href="/accounts/"' not in logged_in_client.get("/import/").content.decode()


def accounts_link(page):
    """The sidebar's admin link to the Accounts page, or None."""
    return re.search(r'<a class="nav ?(on)?" href="/accounts/">Accounts</a>', page)


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


def test_the_list_shows_each_account_with_its_bank_owners_and_ibans(admin_client, member, admin):
    joint = make_account("Joint Sparkasse", "sparkasse_si", member, [SPARKASSE_IBAN])
    joint.owners.add(admin)

    page = admin_client.get("/accounts/").content.decode()

    assert "Joint Sparkasse" in page
    assert "Sparkasse SI" in page
    assert "ana, bor" in page
    assert SPARKASSE_IBAN in page


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

    assert "Not imported" in page
    assert "Ana&#x27;s savings is an Account with no Statements" in page
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

    with pytest.raises(ImportRejected, match="no Statements"):
        commit_statement(checked, member=member, account=account)

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

    assert "Delete Account" in page
    assert "1 Rule only for this Account will be deleted with it." in page
    assert Account.objects.exists()


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
