import re

import pytest
from django.test import Client

from ledger.models import Account, Subcategory, Transaction

USERNAME = "ana"
PASSWORD = "correct horse battery"


def log_in(client, username=USERNAME, password=PASSWORD):
    return client.post("/login/", {"username": username, "password": password})


@pytest.fixture
def member(django_user_model):
    return django_user_model.objects.create_user(username=USERNAME, password=PASSWORD)


@pytest.fixture
def logged_in_client(client, member):
    client.force_login(member)
    return client


@pytest.fixture(autouse=True)
def statement_files(settings, tmp_path):
    """Stored Statement files go to a per-test directory."""
    settings.MEDIA_ROOT = tmp_path / "statement-files"
    return settings.MEDIA_ROOT


def outcome_shown(page, description):
    """The outcome selected in the Transaction row whose description is `description`, as "Category → Subcategory",
    "Transfer" or "Awaiting review"."""
    row = re.search(
        rf"<tr[^>]*>(?:(?!</tr>).)*>{re.escape(description)}<(?:(?!</tr>).)*</tr>", page, re.S
    )
    assert row, f"no row for {description!r}"
    group = None
    for match in re.finditer(
        r'<optgroup label="([^"]*)">|<option value="[^"]*"( selected)?>([^<]*)</option>', row[0]
    ):
        if match[1] is not None:
            group = match[1]
        elif match[2]:
            return f"{group} → {match[3]}" if group and match[3] != "Transfer" else match[3]
    raise AssertionError(f"nothing selected for {description!r}")


@pytest.fixture
def admin_client(django_user_model):
    """A client of its own, so a test can act as a Member and as an admin side by side."""
    client = Client()
    client.force_login(
        django_user_model.objects.create_user(username="bor", password=PASSWORD, is_admin=True)
    )
    return client


def transaction_id(description):
    return Transaction.objects.get(description=description).pk


def subcategory_id(category, name):
    return Subcategory.objects.get(category__name=category, name=name).pk


def review_queue_count(page):
    """The count the sidebar shows next to "Review queue"."""
    count = re.search(r'<span id="review-queue-count"[^>]*>\((\d+)\)</span>', page)
    assert count, "no Review queue count"
    return int(count[1])


def make_account(name, bank, owner=None, ibans=()):
    account = Account.objects.create(name=name, bank=bank)
    if owner:
        account.owners.add(owner)
    for iban in ibans:
        account.ibans.create(iban=iban)
    return account


def assert_nothing_stored(client, statement_files):
    assert "No Accounts yet" in client.get("/import/").content.decode()
    assert "No Transactions yet" in client.get("/transactions/").content.decode()
    assert not list(statement_files.rglob("*.*"))
