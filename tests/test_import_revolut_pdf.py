from pathlib import Path

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile

from tests.conftest import assert_nothing_stored, make_account, outcome_shown

pytestmark = pytest.mark.django_db

FIXTURES = Path(__file__).parent / "fixtures"
FIXTURE = (FIXTURES / "revolut.txt").read_text()
IBAN = "LT121000011101001000"


@pytest.fixture(autouse=True)
def pdf_text(monkeypatch):
    """The uploaded "PDF" is the fixture's extracted text itself."""
    monkeypatch.setattr("ledger.parsers.pdf_text.extract_text", lambda content: content.decode())


def upload(client, content, filename, **data):
    return client.post("/import/", {"file": SimpleUploadedFile(filename, content), **data})


def test_a_revolut_pdf_imports_into_the_account_of_its_iban(logged_in_client, member):
    make_account("Ana's Revolut", "revolut", member)
    make_account("Bor's Revolut", "revolut", member, ibans=[IBAN])

    page = upload(logged_in_client, FIXTURE.encode(), "revolut-june.pdf").content.decode()

    assert "Imported into Bor&#x27;s Revolut" in page
    assert "1 Jun 2026 – 11 Jun 2026" in page
    assert "8 Transactions imported" in page
    transactions = logged_in_client.get("/transactions/").content.decode()
    assert outcome_shown(transactions, "Fee: Corner Shop") == "Finance → Bank fees"
    assert outcome_shown(transactions, "Fee: To Janez Kranjc") == "Finance → Bank fees"


def test_the_revolut_csv_of_an_imported_pdfs_period_is_all_duplicates(logged_in_client, member):
    account = make_account("Ana's Revolut", "revolut", member, ibans=[IBAN])
    upload(logged_in_client, FIXTURE.encode(), "revolut-june.pdf")

    page = upload(
        logged_in_client,
        (FIXTURES / "revolut.csv").read_bytes(),
        "revolut-june.csv",
        account=str(account.pk),
    ).content.decode()

    assert "0 Transactions imported" in page
    assert "8 Duplicates skipped" in page


def test_rows_that_dont_match_the_printed_money_in_are_rejected(logged_in_client, statement_files):
    # The rows still add up to the closing balance, but 1 euro more is printed as coming in.
    text = FIXTURE.replace("€372.36 €2,025.00", "€373.36 €2,026.00")

    page = upload(logged_in_client, text.encode(), "revolut-june.pdf").content.decode()

    assert "rows don&#x27;t match its printed totals" in page
    assert '<tr><th>Printed</th><td class="num">2026.00</td><td class="num">—</td>' in page
    assert '<tr><th>Parsed rows</th><td class="num">2025.00</td><td class="num">2</td>' in page
    assert_nothing_stored(logged_in_client, statement_files)
