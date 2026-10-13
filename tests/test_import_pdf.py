import re
from pathlib import Path

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile

from tests.conftest import assert_nothing_stored, make_account

pytestmark = pytest.mark.django_db

FIXTURE = (Path(__file__).parent / "fixtures" / "sparkasse.txt").read_text()
IBAN = "SI56340001234567864"


@pytest.fixture(autouse=True)
def pdf_text(monkeypatch):
    """The uploaded "PDF" is the fixture's extracted text itself."""
    monkeypatch.setattr("ledger.parsers.pdf_text.extract_text", lambda content: content.decode())


def upload(client, text=FIXTURE, filename="izpisek-2026-09.pdf", **data):
    return client.post("/import/", {"file": SimpleUploadedFile(filename, text.encode()), **data})


def choose(client, response, **data):
    """Post the Account step that `response` shows, carrying its pending file along."""
    hidden = dict(
        re.findall(
            r'<input type="hidden" name="(content|filename)" value="([^"]*)"',
            response.content.decode(),
        )
    )
    return client.post("/import/", {**hidden, **data})


def make_sparkasse(name, owner, ibans=()):
    return make_account(name, "sparkasse_si", owner, ibans)


def test_an_unknown_iban_asks_for_the_account_with_a_new_one_preselected(logged_in_client):
    response = upload(logged_in_client)

    page = response.content.decode()
    assert "Choose the Account" in page
    assert "Sparkasse SI" in page
    assert IBAN in page
    assert '<option value="new" selected>' in page
    assert 'value="Sparkasse SI"' in page
    assert "No Transactions yet" in logged_in_client.get("/transactions/").content.decode()


def test_creating_the_account_for_an_unknown_iban_imports_the_statement(logged_in_client):
    response = choose(
        logged_in_client,
        upload(logged_in_client),
        account="new",
        new_account_name="Ana's Sparkasse",
    )

    summary = response.content.decode()
    assert "Imported into Ana&#x27;s Sparkasse" in summary
    assert "1 Sep 2026 – 30 Sep 2026" in summary
    assert "12 Transactions imported" in summary
    page = logged_in_client.get("/import/").content.decode()
    assert "Sparkasse SI · ana" in page  # the importing Member owns the new Account
    assert IBAN in page  # with the Statement's IBAN filled in
    assert "<td>PDF</td>" in page


def october(text=FIXTURE):
    """The next month's Statement of the same Account: a different file with the same IBAN."""
    return text.replace(
        "31.08.2026 Datum izpiska: 30.09.2026", "30.09.2026 Datum izpiska: 31.10.2026"
    )


def test_a_known_iban_imports_straight_into_its_account(logged_in_client, member):
    make_sparkasse("Joint Sparkasse", member, ibans=[IBAN])
    make_sparkasse("Bor's Sparkasse", member, ibans=["SI56020100001234582"])

    response = upload(logged_in_client)

    page = response.content.decode()
    assert "Imported into Joint Sparkasse" in page
    assert "Choose the Account" not in page
    assert "<td>Joint Sparkasse</td>" in logged_in_client.get("/transactions/").content.decode()


def test_picking_an_existing_account_for_an_unknown_iban_adds_the_iban_to_it(
    logged_in_client, member
):
    make_account("Ana's Revolut", "revolut", member)
    account = make_sparkasse("Joint Sparkasse", member, ibans=["SI56020100001234582"])
    step = upload(logged_in_client)
    page = step.content.decode()
    assert "Joint Sparkasse</option>" in page
    assert "Ana&#x27;s Revolut</option>" not in page  # only Accounts of the Statement's bank
    assert "selected>" not in page.replace('<option value="" selected>', "")

    assert (
        "Imported into Joint Sparkasse"
        in choose(logged_in_client, step, account=str(account.pk)).content.decode()
    )

    # The next Statement of that IBAN is recognised.
    assert "Imported into Joint Sparkasse" in upload(logged_in_client, october()).content.decode()


def test_a_statement_of_a_known_iban_cant_go_into_another_account(logged_in_client, member):
    other = make_sparkasse("Bor's Sparkasse", member)
    step = choose(
        logged_in_client,
        upload(logged_in_client),
        account="new",
        new_account_name="Ana's Sparkasse",
    )
    assert "Imported" in step.content.decode()

    response = upload(logged_in_client, october(), account=str(other.pk))

    assert f"IBAN {IBAN} belongs to Ana&#x27;s Sparkasse" in response.content.decode()
    assert (
        "Bor&#x27;s Sparkasse</td>" not in logged_in_client.get("/transactions/").content.decode()
    )


def test_two_identical_rows_on_one_statement_are_both_imported(logged_in_client, member):
    make_sparkasse("Ana's Sparkasse", member, ibans=[IBAN])

    upload(logged_in_client)

    page = logged_in_client.get("/transactions/").content.decode()
    fee = '<td>2026-09-15</td><td>Ana&#x27;s Sparkasse</td><td>Banka Sparkasse, d. d.</td><td class="num">-0.40</td>'
    assert page.count(fee) == 2
    assert "Pozitivne obresti" in page


def test_rows_that_dont_match_the_printed_totals_are_rejected_with_a_diagnosis(
    logged_in_client, statement_files
):
    # The rows still add up to the closing balance, but one interest row too many is printed.
    text = FIXTURE.replace("1.842,85 10 1.250,02 2 3.729,07", "1.842,85 10 1.250,02 3 3.729,07")

    page = upload(logged_in_client, text).content.decode()

    assert "rows don&#x27;t match its printed totals" in page
    assert "keep this file" in page
    assert '<tr><th>Printed</th><td class="num">1250.02</td><td class="num">3</td>' in page
    assert '<tr><th>Parsed rows</th><td class="num">1250.02</td><td class="num">2</td>' in page
    assert "Pozitivne obresti" in page  # the parsed rows
    assert_nothing_stored(logged_in_client, statement_files)


def test_statement_whose_balances_dont_add_up_is_rejected(logged_in_client, statement_files):
    text = FIXTURE.replace("EUR 4.321,90 1.842,85", "EUR 4.320,90 1.842,85")  # the opening balance

    page = upload(logged_in_client, text).content.decode()

    assert "balances don&#x27;t add up" in page
    assert "4320.90" in page
    assert_nothing_stored(logged_in_client, statement_files)


def test_statement_with_an_unsupported_row_is_rejected(logged_in_client, statement_files):
    text = FIXTURE.replace("02.09.2026 SI56020100001234582 Flik plačilo", "02.09.2026 Flik plačilo")

    page = upload(logged_in_client, text).content.decode()

    assert "unsupported row: 02.09.2026 MARKO K 85,00 / 02.09.2026 Flik plačilo" in page
    assert "keep this file" in page
    assert_nothing_stored(logged_in_client, statement_files)


def test_a_file_that_is_not_a_pdf_is_rejected(logged_in_client, statement_files, monkeypatch):
    monkeypatch.undo()  # the real PDF-to-text adapter

    page = upload(logged_in_client, "not a PDF at all").content.decode()

    assert "The file is not a readable PDF." in page
    assert_nothing_stored(logged_in_client, statement_files)


def test_a_tampered_pending_file_is_asked_for_again(logged_in_client):
    response = logged_in_client.post(
        "/import/", {"content": "not base64!", "filename": "x.pdf", "account": "new"}
    )

    assert "Upload the Statement file again." in response.content.decode()
