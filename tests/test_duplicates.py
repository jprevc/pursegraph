"""Overlapping Statements: Duplicates, Coverage and multi-file uploads."""

from datetime import date
from decimal import Decimal

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile

from ledger.models import Account

from .conftest import EUR, board_row, page_text, transaction_rows

pytestmark = pytest.mark.django_db

HEADER = "Type,Product,Started Date,Completed Date,Description,Amount,Fee,Currency,State,Balance"


def revolut_csv(opening, rows):
    """A Revolut CSV of `rows` = (day, description, amount[, fee]), with the balances worked out from `opening`."""
    balance = Decimal(opening)
    lines = [HEADER]
    for day, description, amount, *fee in rows:
        fee = Decimal(fee[0] if fee else "0")
        balance += Decimal(amount) - fee
        completed = f"{date.fromisoformat(day)} 9:00:00"
        lines.append(
            f"Card Payment,Current,{completed},{completed},{description},{amount},{fee},EUR,COMPLETED,{balance}"
        )
    return ("\n".join(lines) + "\n").encode()


JUNE_1_TO_10 = [
    ("2026-06-01", "Hisa kave", "-4.50"),
    ("2026-06-03", "Salary", "2000"),
    ("2026-06-05", "Corner Shop", "-50.02", "0.5"),
    ("2026-06-08", "Bakery", "-3.20"),
    ("2026-06-10", "Mercator", "-12.34"),
]
# The balance after JUNE_1_TO_10, starting from 500.
BALANCE_JUNE_10 = "2429.44"


def upload(client, *files, account="new", new_account_name="Ana's Revolut"):
    """Upload `files`, each (filename, content), in one request."""
    return client.post(
        "/import/",
        {
            "file": [SimpleUploadedFile(name, content) for name, content in files],
            "account": account,
            "new_account_name": new_account_name,
        },
    )


def import_page(client):
    return client.get("/import/").content.decode()


def transactions_page(client):
    return client.get("/transactions/").content.decode()


@pytest.fixture
def june_imported(logged_in_client):
    """June 1–10 imported into a new Revolut Account, which is then the only one (and preselected)."""
    upload(logged_in_client, ("june.csv", revolut_csv("500", JUNE_1_TO_10)))
    return Account.objects.get()


def test_overlapping_rows_that_match_are_skipped_as_duplicates(logged_in_client, june_imported):
    overlap = revolut_csv(
        "2444.98",
        [  # the balance on the morning of June 8
            ("2026-06-08", "Bakery", "-3.20"),
            ("2026-06-10", "Mercator", "-12.34"),
            ("2026-06-12", "Petrol", "-60"),
        ],
    )

    response = upload(logged_in_client, ("overlap.csv", overlap), account=str(june_imported.pk))

    page = response.content.decode()
    assert "1 Transaction imported" in page_text(page)
    assert "2 Duplicates skipped" in page_text(page)
    descriptions = [d for _d, _a, d, _x in transaction_rows(transactions_page(logged_in_client))]
    assert descriptions.count("Bakery") == 1
    assert descriptions.count("Mercator") == 1
    assert "Petrol" in descriptions


def test_overlap_that_does_not_match_rejects_the_whole_file(
    logged_in_client, june_imported, statement_files
):
    overlap = revolut_csv(
        "2444.98",
        [
            ("2026-06-08", "Bakery", "-3.30"),  # imported as -3.20
            ("2026-06-12", "Petrol", "-60"),
        ],
    )

    response = upload(logged_in_client, ("overlap.csv", overlap), account=str(june_imported.pk))

    page = response.content.decode()
    said = page_text(page)
    assert "Disagrees with what's already imported" in said
    assert "On 2 days inside Ana's Revolut's Coverage, its rows don't match" in said
    mismatch = page[page.index('class="mismatch"') :]
    assert "8 Jun 2026" in mismatch
    assert f"−3,20{EUR}" in mismatch  # already imported, missing from the file
    assert f"−3,30{EUR}" in mismatch  # in the file, not imported before
    assert "Mercator" in mismatch  # June 10 is in the Coverage, but missing from the file
    assert "Petrol" not in transactions_page(logged_in_client)
    assert len(list(statement_files.rglob("*.csv"))) == 1


def test_a_statement_may_add_rows_on_the_last_day_of_the_coverage(logged_in_client, june_imported):
    # Such as a CSV exported in the middle of June 10, completed by a later Statement.
    overlap = revolut_csv(
        "2444.98",
        [
            ("2026-06-08", "Bakery", "-3.20"),
            ("2026-06-10", "Mercator", "-12.34"),
            ("2026-06-10", "Kiosk", "-2"),
            ("2026-06-12", "Petrol", "-60"),
        ],
    )

    page = upload(
        logged_in_client, ("overlap.csv", overlap), account=str(june_imported.pk)
    ).content.decode()

    assert "2 Transactions imported" in page_text(page)
    assert "2 Duplicates skipped" in page_text(page)
    assert "Kiosk" in transactions_page(logged_in_client)


def test_a_statement_may_add_rows_on_the_first_day_of_the_coverage(logged_in_client, june_imported):
    earlier = revolut_csv(
        "506",
        [
            ("2026-05-30", "Kiosk", "-5"),
            ("2026-06-01", "Newsagent", "-1"),
            ("2026-06-01", "Hisa kave", "-4.50"),
        ],
    )

    page = upload(
        logged_in_client, ("may.csv", earlier), account=str(june_imported.pk)
    ).content.decode()

    assert "2 Transactions imported" in page_text(page)
    assert "1 Duplicate skipped" in page_text(page)


def test_an_edge_day_must_still_match_every_existing_row(logged_in_client, june_imported):
    earlier = revolut_csv("501", [("2026-05-30", "Kiosk", "-5"), ("2026-06-01", "Newsagent", "-1")])

    page = upload(
        logged_in_client, ("may.csv", earlier), account=str(june_imported.pk)
    ).content.decode()

    assert "Not imported" in page
    assert "Hisa kave" in page[page.index('class="mismatch"') :]
    assert "Kiosk" not in transactions_page(logged_in_client)


def test_a_statement_may_not_add_rows_inside_the_coverage(logged_in_client, june_imported):
    overlap = revolut_csv(
        "2444.98",
        [
            ("2026-06-08", "Bakery", "-3.20"),
            ("2026-06-09", "Kiosk", "-2"),
            ("2026-06-10", "Mercator", "-12.34"),
        ],
    )

    page = upload(
        logged_in_client, ("overlap.csv", overlap), account=str(june_imported.pk)
    ).content.decode()

    assert "Not imported" in page
    assert "Kiosk" in page[page.index('class="mismatch"') :]
    assert "Kiosk" not in transactions_page(logged_in_client)


def test_identical_rows_on_one_statement_are_both_imported_and_both_matched_later(logged_in_client):
    twice = [("2026-06-01", "Parking", "-2"), ("2026-06-01", "Parking", "-2")]
    upload(logged_in_client, ("first.csv", revolut_csv("100", twice)))
    account = Account.objects.get()
    rows = transaction_rows(transactions_page(logged_in_client))
    assert [description for _d, _a, description, _x in rows].count("Parking") == 2

    page = upload(
        logged_in_client,
        ("second.csv", revolut_csv("100", [*twice, ("2026-06-02", "Petrol", "-50")])),
        account=str(account.pk),
    ).content.decode()

    assert "1 Transaction imported" in page_text(page)
    assert "2 Duplicates skipped" in page_text(page)
    rows = transaction_rows(transactions_page(logged_in_client))
    assert [description for _d, _a, description, _x in rows].count("Parking") == 2


def statement_row(page, period):
    """The Import page's table row for the Statement covering `period`."""
    start = page.index(f'<td class="fig">{period}</td>')
    return page[start : page.index("</tr>", start)]


def test_a_duplicate_is_linked_to_every_statement_it_appears_on(logged_in_client, june_imported):
    overlap = revolut_csv(
        "2444.98",
        [
            ("2026-06-08", "Bakery", "-3.20"),
            ("2026-06-10", "Mercator", "-12.34"),
            ("2026-06-12", "Petrol", "-60"),
        ],
    )
    upload(logged_in_client, ("overlap.csv", overlap), account=str(june_imported.pk))

    page = import_page(logged_in_client)

    assert '<td class="num">6</td>' in statement_row(page, "1–10 Jun 2026")
    assert '<td class="num">3</td>' in statement_row(page, "8–12 Jun 2026")


def test_opening_balance_must_line_up_with_the_accounts_running_balance(
    logged_in_client, june_imported
):
    # Rows from June 11 on: nothing to match, but the balance before them is known to be 2429.44.
    later = revolut_csv("2400", [("2026-06-11", "Petrol", "-60")])

    page = upload(
        logged_in_client, ("later.csv", later), account=str(june_imported.pk)
    ).content.decode()

    assert "Not imported" in page
    assert f"2.400,00{EUR}" in page
    assert f"2.429,44{EUR}" in page
    assert "Petrol" not in transactions_page(logged_in_client)


def test_a_statement_that_continues_the_running_balance_is_imported(
    logged_in_client, june_imported
):
    later = revolut_csv(BALANCE_JUNE_10, [("2026-06-11", "Petrol", "-60")])

    page = upload(
        logged_in_client, ("later.csv", later), account=str(june_imported.pk)
    ).content.decode()

    assert "1 Transaction imported" in page_text(page)


def test_several_files_are_imported_independently_in_period_order(
    logged_in_client, statement_files
):
    later = ("later.csv", revolut_csv(BALANCE_JUNE_10, [("2026-06-11", "Petrol", "-60")]))
    broken = ("broken.csv", b"not a statement\n")
    june = ("june.csv", revolut_csv("500", JUNE_1_TO_10))

    page = upload(logged_in_client, later, broken, june).content.decode()

    # The later file lines up only because June was imported first; each lands on the Account's row.
    row = board_row(page, "Ana's Revolut")
    assert row.index("New: 1–10 Jun 2026") < row.index("New: 11 Jun 2026")
    assert "Not imported broken.csv" in page_text(page)
    assert "2 files Needs you" not in page_text(page)
    assert page_text(page).count("Not imported") == 1
    # Both went into the one Account created by the upload.
    assert import_page(logged_in_client).count("Revolut · ana") == 1
    assert "Petrol" in transactions_page(logged_in_client)
    assert len(list(statement_files.rglob("*.csv"))) == 2


def test_the_row_shows_the_gap_a_statement_leaves(logged_in_client, june_imported):
    later = revolut_csv("1000", [("2026-06-15", "Petrol", "-60"), ("2026-06-20", "Kiosk", "-2")])

    page = upload(
        logged_in_client, ("later.csv", later), account=str(june_imported.pk)
    ).content.decode()

    row = board_row(page, "Ana's Revolut")
    assert "New: 15–20 Jun 2026 · 2 Transactions" in row  # a Gap, not a rejection
    assert "Covered 1–10 Jun 2026 Gap 11–14 Jun 2026 Covered by this import 15–20 Jun 2026" in row
    assert "Gap 11–14 Jun 2026 Gap 21 Jun" in row  # the captions, the last since the last Statement


def test_import_page_shows_each_accounts_coverage_with_its_gaps(logged_in_client, june_imported):
    later = revolut_csv("1000", [("2026-06-15", "Petrol", "-60"), ("2026-06-20", "Kiosk", "-2")])
    upload(logged_in_client, ("later.csv", later), account=str(june_imported.pk))
    savings = Account.objects.create(name="Savings", bank="revolut")

    page = import_page(logged_in_client)

    row = board_row(page, "Ana's Revolut")
    assert "Covered 1–10 Jun 2026 Gap 11–14 Jun 2026 Covered 15–20 Jun 2026 Gap 21 Jun" in row
    assert ", since the last Statement" in row
    assert "Tracked from 1 Jun 2026" in row
    assert 'aria-label="Gap 11–14 Jun 2026: import a Statement"' in page
    assert row.index("15–20 Jun 2026 CSV") < row.index("1–10 Jun 2026 CSV")  # newest first
    assert board_row(page, savings.name).endswith("No Statements yet.")


def test_a_statement_just_before_the_coverage_must_close_at_its_opening_balance(
    logged_in_client, june_imported
):
    # June 1–10 opens at 500, so the day before it must close there.
    earlier = revolut_csv("1000", [("2026-05-30", "Kiosk", "-1"), ("2026-05-31", "Kiosk", "-0.50")])

    page = upload(
        logged_in_client, ("may.csv", earlier), account=str(june_imported.pk)
    ).content.decode()

    assert "Not imported" in page
    assert f"998,50{EUR}" in page
    assert f"500,00{EUR}" in page
    assert "Kiosk" not in transactions_page(logged_in_client)


def test_a_statement_inside_the_coverage_adds_no_new_stretch(logged_in_client, june_imported):
    inside = revolut_csv(
        "2444.98", [("2026-06-08", "Bakery", "-3.20"), ("2026-06-10", "Mercator", "-12.34")]
    )

    page = upload(
        logged_in_client, ("inside.csv", inside), account=str(june_imported.pk)
    ).content.decode()

    assert "2 Duplicates skipped" in page_text(page)
    row = board_row(page, "Ana's Revolut")
    assert "New: 8–10 Jun 2026 · 0 Transactions" in row
    assert "Covered by this import" not in row
