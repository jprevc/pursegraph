import json
import re
from pathlib import Path

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile

from tests.conftest import (
    EUR,
    assert_nothing_stored,
    board_row,
    make_account,
    page_text,
    transaction_rows,
)

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
    page = response.content.decode()
    assert "8 Transactions imported from 1 file" in page_text(page)
    row = board_row(page, "Ana's Revolut")
    assert "New: 1–11 Jun 2026 · 8 Transactions" in row
    assert "8 Transactions imported" in row
    assert "1 card payment still pending or declined, left out" in row


def test_imported_statement_is_listed_under_its_account(logged_in_client):
    upload(logged_in_client)

    row = board_row(logged_in_client.get("/import/").content.decode(), "Ana's Revolut")

    assert "Revolut · ana" in row  # the importing Member owns the new Account
    assert "1 Statement" in row
    assert "1–11 Jun 2026 CSV 8" in row
    assert "New:" not in row  # only right after the import


def test_imported_transactions_appear_in_the_transactions_view(logged_in_client):
    upload(logged_in_client)

    page = logged_in_client.get("/transactions/").content.decode()

    for text in (
        "Hiša kave",
        "Payment from Ana Novak",
        "Fee: Corner Shop",
        f"−0,50{EUR}",
        "Mercator Žalec",
        f"2.000,00{EUR}",
    ):
        assert text in page
    assert "Bakery" not in page  # pending


def test_the_import_page_names_every_supported_format(logged_in_client):
    page = logged_in_client.get("/import/").content.decode()

    assert "PDF Statements from Sparkasse SI, N26 and Revolut, and Revolut CSV exports" in page


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

    page = page_text(response.content.decode())
    assert "Nothing imported 1 was already imported" in page
    assert "Already imported renamed.csv went into Ana's Revolut on" in page
    assert "Not imported" not in page
    assert "Second" not in logged_in_client.get("/import/").content.decode()
    rows = transaction_rows(logged_in_client.get("/transactions/").content.decode())
    assert [description for _d, _a, description, _x in rows].count("Hiša kave") == 1


def test_statement_whose_balances_dont_add_up_is_rejected_with_a_diagnosis(
    logged_in_client, statement_files
):
    # Drop the refund row: the balances after it no longer follow from the rows.
    content = b"\n".join(line for line in FIXTURE.split(b"\n") if b"Card Refund" not in line)

    response = upload(logged_in_client, content=content)

    page = page_text(response.content.decode())
    assert "Not imported account-statement_2026-06-01_2026-06-11.csv" in page
    assert "A payment seems to be missing" in page
    assert "its rows should add up to 1.652,64" in page
    assert "So nothing from this file was imported." in page
    assert "Keep the file: the Revolut reader needs a fix." in page
    assert f"500,00{EUR}" in page  # opening
    assert f"1.627,64{EUR}" in page  # Σ rows
    assert f"2.152,64{EUR}" in page  # closing
    assert "Mercator Žalec" in page  # the parsed rows
    assert_nothing_stored(logged_in_client, statement_files)


def test_statement_with_an_unsupported_row_is_rejected(logged_in_client, statement_files):
    line = b"Card Payment,Current,2026-06-12 9:00:00,yesterday,Bakery,-3.2,0,EUR,COMPLETED,2149.44"

    response = upload(logged_in_client, content=FIXTURE + line + b"\n")

    page = page_text(response.content.decode())
    assert "Not a Statement Pursegraph can read" in page
    assert "What the reader found unsupported row: " + line.decode() in page
    assert "If it is a downloaded Statement, keep it" in page
    assert_nothing_stored(logged_in_client, statement_files)


def test_unknown_file_type_is_rejected(logged_in_client, statement_files):
    response = upload(logged_in_client, filename="statement.xlsx")

    page = page_text(response.content.decode())
    assert "Not a PDF or CSV file" in page
    assert "Download the Statement as a PDF (or a CSV from Revolut)" in page
    assert_nothing_stored(logged_in_client, statement_files)


def upload_without_account(client):
    """Upload the CSV alone; the response asks for the Account."""
    return client.post("/import/", {"file": SimpleUploadedFile(FILENAME, FIXTURE)}).content.decode()


def test_a_csv_asks_for_the_account(logged_in_client):
    page = page_text(upload_without_account(logged_in_client))

    assert "Needs you · 1 file Needs an Account" in page
    assert "A Revolut CSV export, 1–11 Jun 2026. It carries no IBAN" in page
    assert "Nothing imported 1 file needs an Account" in page
    assert "No Transactions yet" in logged_in_client.get("/transactions/").content.decode()


def test_with_no_revolut_account_a_new_one_is_preselected(logged_in_client):
    page = upload_without_account(logged_in_client)

    assert 'value="new" id="id_0_account_new" checked>' in page
    assert 'value="Revolut"' in page


def test_the_only_revolut_account_is_preselected(logged_in_client, member):
    make_account("Joint N26", "n26", member)
    account = make_account("Ana's Revolut", "revolut", member)

    page = upload_without_account(logged_in_client)

    assert f'value="{account.pk}" id="id_0_account_{account.pk}" checked>' in page
    choose = page[
        page.index('class="choose"') : page.index("</form>", page.index('class="choose"'))
    ]
    assert "Joint N26" not in choose


def test_with_several_revolut_accounts_the_member_must_choose(logged_in_client, member):
    make_account("Ana's Revolut", "revolut", member)
    make_account("Bor's Revolut", "revolut", member)

    page = upload_without_account(logged_in_client)

    assert 'name="account" value="new"' in page
    assert not re.search(r'name="account" value="[^"]*" id="[^"]*" checked>', page)
    assert upload(logged_in_client, account="").status_code == 200
    assert "No Transactions yet" in logged_in_client.get("/transactions/").content.decode()


def test_import_into_an_existing_revolut_account(logged_in_client, member):
    make_account("Ana's Revolut", "revolut", member)
    account = make_account("Bor's Revolut", "revolut", member)

    response = upload(logged_in_client, account=str(account.pk))

    assert "New: 1–11 Jun 2026" in board_row(response.content.decode(), "Bor's Revolut")
    page = logged_in_client.get("/transactions/").content.decode()
    assert {account for _d, account, _t, _x in transaction_rows(page)} == {"Bor's Revolut"}


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


def test_an_htmx_import_swaps_in_the_region_and_announces_the_result(logged_in_client):
    response = logged_in_client.post(
        "/import/",
        {
            "file": SimpleUploadedFile(FILENAME, FIXTURE),
            "account": "new",
            "new_account_name": "Ana's Revolut",
        },
        headers={"HX-Request": "true"},
    )

    page = response.content.decode()
    assert page.lstrip().startswith("<title>Import · Pursegraph</title>")
    assert '<div id="import"' in page
    assert "<html" not in page
    assert 'tabindex="-1" data-focus>8 Transactions imported from 1 file<' in page
    announced = json.loads(response["HX-Trigger"])["announce"]
    assert announced == "8 Transactions imported from 1 file. 6 wait for review"


def test_a_new_account_gets_the_owners_chosen(logged_in_client, member, django_user_model):
    bor = django_user_model.objects.create_user(username="bor", first_name="Bor", last_name="Novak")

    response = upload(logged_in_client, owners=[member.pk, bor.pk])

    assert "Revolut · ana, Bor Novak" in board_row(response.content.decode(), "Ana's Revolut")


def test_an_account_that_takes_no_statements_says_so_in_place_of_a_track(logged_in_client, member):
    make_account("Ana's savings", "other", member, ["SI56020100001234582"])
    upload(logged_in_client)

    row = board_row(logged_in_client.get("/import/").content.decode(), "Ana's savings")

    assert "Takes no Statements: money moved to its IBAN counts as a Transfer." in row
    assert "1 Statement" not in row


def test_an_htmx_post_without_files_announces_why(logged_in_client):
    response = logged_in_client.post("/import/", {}, headers={"HX-Request": "true"})

    assert json.loads(response["HX-Trigger"])["announce"] == "Choose a Statement file."
