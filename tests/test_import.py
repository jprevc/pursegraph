from pathlib import Path

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile

from tests.conftest import assert_nothing_stored, make_account

pytestmark = pytest.mark.django_db

FIXTURE = (Path(__file__).parent / "fixtures" / "revolut.csv").read_bytes()
FILENAME = "account-statement_2026-06-01_2026-06-11.csv"


def upload(client, content=FIXTURE, filename=FILENAME, **data):
    data.setdefault("account", "new")
    data.setdefault("new_account_name", "Ana's Revolut")
    return client.post("/import/", {"file": SimpleUploadedFile(filename, content), **data})


def test_import_into_a_new_revolut_account_shows_the_summary(logged_in_client):
    response = upload(logged_in_client)

    assert response.status_code == 200
    summary = response.content.decode()
    assert "Ana&#x27;s Revolut" in summary
    assert "1 Jun 2026 – 11 Jun 2026" in summary
    assert "8 Transactions imported" in summary
    assert "1 non-completed row skipped" in summary


def test_imported_statement_is_listed_under_its_account(logged_in_client):
    upload(logged_in_client)

    page = logged_in_client.get("/import/").content.decode()

    assert "Ana&#x27;s Revolut" in page
    assert "Revolut · ana" in page  # the importing Member owns the new Account
    assert "1 Jun 2026 – 11 Jun 2026" in page
    assert "<td>CSV</td>" in page


def test_imported_transactions_appear_in_the_transactions_view(logged_in_client):
    upload(logged_in_client)

    page = logged_in_client.get("/transactions/").content.decode()

    for text in ("Hiša kave", "Payment from Ana Novak", "Fee: Corner Shop", "-0.50", "Mercator Žalec", "2000.00"):
        assert text in page
    assert "Bakery" not in page  # pending


def test_sidebar_links_to_transactions(logged_in_client):
    assert b'href="/transactions/"' in logged_in_client.get("/").content


def test_the_original_file_is_stored(logged_in_client, statement_files):
    upload(logged_in_client)

    [stored] = statement_files.rglob("*.csv")
    assert stored.name == FILENAME
    assert stored.read_bytes() == FIXTURE


def test_reuploading_the_same_file_is_rejected(logged_in_client):
    upload(logged_in_client)

    response = upload(logged_in_client, filename="renamed.csv", new_account_name="Second")

    page = response.content.decode()
    assert "Not imported" in page
    assert "already imported" in page
    assert "keep this file" not in page
    assert "Second" not in logged_in_client.get("/import/").content.decode()
    assert logged_in_client.get("/transactions/").content.decode().count("Hiša kave") == 1


def test_statement_whose_balances_dont_add_up_is_rejected_with_a_diagnosis(logged_in_client, statement_files):
    # Drop the refund row: the balances after it no longer follow from the rows.
    content = b"\n".join(line for line in FIXTURE.split(b"\n") if b"Card Refund" not in line)

    response = upload(logged_in_client, content=content)

    page = response.content.decode()
    assert "balances don&#x27;t add up" in page
    assert "keep this file" in page
    assert "500.00" in page  # opening
    assert "1627.64" in page  # Σ rows
    assert "2152.64" in page  # closing
    assert "Mercator Žalec" in page  # the parsed rows
    assert_nothing_stored(logged_in_client, statement_files)


def test_statement_with_an_unsupported_row_is_rejected(logged_in_client, statement_files):
    line = b"Card Payment,Current,2026-06-12 9:00:00,yesterday,Bakery,-3.2,0,EUR,COMPLETED,2149.44"

    response = upload(logged_in_client, content=FIXTURE + line + b"\n")

    page = response.content.decode()
    assert "unsupported row: " + line.decode() in page
    assert "keep this file" in page
    assert_nothing_stored(logged_in_client, statement_files)


def test_unknown_file_type_is_rejected(logged_in_client, statement_files):
    response = upload(logged_in_client, filename="statement.xlsx")

    assert "Only PDF and CSV Statements can be imported" in response.content.decode()
    assert_nothing_stored(logged_in_client, statement_files)


def upload_without_account(client):
    """Upload the CSV alone; the response asks for the Account."""
    return client.post("/import/", {"file": SimpleUploadedFile(FILENAME, FIXTURE)}).content.decode()


def test_a_csv_asks_for_the_account(logged_in_client):
    page = upload_without_account(logged_in_client)

    assert "Choose the Account" in page
    assert "a Revolut Statement, 1 Jun 2026 – 11 Jun 2026" in page
    assert "No Transactions yet" in logged_in_client.get("/transactions/").content.decode()


def test_with_no_revolut_account_a_new_one_is_preselected(logged_in_client):
    page = upload_without_account(logged_in_client)

    assert '<option value="new" selected>' in page
    assert 'value="Revolut"' in page


def test_the_only_revolut_account_is_preselected(logged_in_client, member):
    make_account("Joint N26", "n26", member)
    account = make_account("Ana's Revolut", "revolut", member)

    page = upload_without_account(logged_in_client)

    assert f'<option value="{account.pk}" selected>' in page
    assert "Joint N26</option>" not in page


def test_with_several_revolut_accounts_the_member_must_choose(logged_in_client, member):
    make_account("Ana's Revolut", "revolut", member)
    make_account("Bor's Revolut", "revolut", member)

    page = upload_without_account(logged_in_client)

    assert "selected>" not in page.replace('<option value="" selected>', "")
    assert upload(logged_in_client, account="").status_code == 200
    assert "No Transactions yet" in logged_in_client.get("/transactions/").content.decode()


def test_import_into_an_existing_revolut_account(logged_in_client, member):
    make_account("Ana's Revolut", "revolut", member)
    account = make_account("Bor's Revolut", "revolut", member)

    response = upload(logged_in_client, account=str(account.pk))

    assert "Imported into Bor&#x27;s Revolut" in response.content.decode()
    page = logged_in_client.get("/transactions/").content.decode()
    assert "<td>Bor&#x27;s Revolut</td>" in page
    assert "<td>Ana&#x27;s Revolut</td>" not in page


def test_statement_bank_must_match_the_account_bank(logged_in_client, member, statement_files):
    account = make_account("Joint N26", "n26", member)

    response = upload(logged_in_client, account=str(account.pk))

    # Only Revolut Accounts are offered for a Revolut CSV, so the N26 one is refused outright.
    assert "Select a valid choice" in response.content.decode()
    assert "No Transactions yet" in logged_in_client.get("/transactions/").content.decode()
    assert not list(statement_files.rglob("*.*"))


def test_a_new_account_needs_a_name(logged_in_client, statement_files):
    response = upload(logged_in_client, new_account_name="  ")

    assert "Name the new Account." in response.content.decode()
    assert_nothing_stored(logged_in_client, statement_files)


def test_dashboard_stops_asking_for_the_first_statement_after_an_import(logged_in_client):
    upload(logged_in_client)

    assert b"Import your first Statement" not in logged_in_client.get("/").content
