import html
import json
import re
from datetime import date

import pytest
from django.test import Client

from ledger.models import Account, Subcategory, Transaction

USERNAME = "ana"
PASSWORD = "correct horse battery"
# What follows an amount on a page: a no-break space and the euro sign, as in "1.234,56\u00a0€".
EUR = "\u00a0€"


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


@pytest.fixture
def household(member, django_user_model):
    """Two Members, Ana and Marko, each with an Account of their own and a joint one, over August to October 2026.

    September 2026: money in 3550.00 (two salaries, interest and 45.00 awaiting review), money out 262.30
    (Food 180.00, Shopping 70.00 after a 30.00 Refund, 12.30 awaiting review), and a Transfer into the joint
    Account, which counts as neither."""
    marko = django_user_model.objects.create_user(username="marko", password=PASSWORD)
    anas = make_account("Ana's Sparkasse", "sparkasse_si", member)
    markos = make_account("Marko's N26", "n26", marko)
    joint = make_account("Joint Revolut", "revolut", member)
    joint.owners.add(marko)
    groceries = Subcategory.objects.get(category__name="Food", name="Groceries")
    restaurants = Subcategory.objects.get(category__name="Food", name="Restaurants & cafés")
    shopping = Subcategory.objects.get(category__name="Shopping", name="Other")
    salary = Subcategory.objects.get(category__name="Income", name="Salary")
    interest = Subcategory.objects.get(category__name="Income", name="Interest")
    rows = [
        (anas, date(2026, 8, 31), "-999.00", "August groceries", groceries, False),
        (markos, date(2026, 8, 15), "1500.00", "Marko's August salary", salary, False),
        (anas, date(2026, 9, 1), "-80.00", "Mercator", groceries, False),
        (anas, date(2026, 9, 9), "-100.00", "Shoe shop", shopping, False),
        (anas, date(2026, 9, 12), "30.00", "Shoe shop refund", shopping, False),
        (anas, date(2026, 9, 15), "2000.00", "Ana's salary", salary, False),
        (anas, date(2026, 9, 20), "-500.00", "To Joint Revolut", None, True),
        (joint, date(2026, 9, 20), "500.00", "From Ana's Sparkasse", None, True),
        (anas, date(2026, 9, 25), "-12.30", "Unknown shop", None, False),
        (anas, date(2026, 9, 26), "45.00", "Unknown payment in", None, False),
        (joint, date(2026, 9, 21), "-60.00", "Spar", groceries, False),
        (markos, date(2026, 9, 15), "1500.00", "Marko's salary", salary, False),
        (markos, date(2026, 9, 18), "-40.00", "Gostilna", restaurants, False),
        (markos, date(2026, 9, 30), "5.00", "Interest", interest, False),
        (anas, date(2026, 10, 1), "-777.00", "October groceries", groceries, False),
    ]
    for account, day, amount, description, outcome, is_transfer in rows:
        Transaction.objects.create(
            account=account,
            date=day,
            amount=amount,
            description=description,
            subcategory=outcome,
            is_transfer=is_transfer,
            source="manual" if outcome or is_transfer else "",
        )
    return {"ana": member, "marko": marko}


def view_table(page):
    """A dashboard view's table: each clickable row as [label, *amounts], in the order shown."""
    return [
        [html.unescape(cell) for cell in re.findall(r"<td[^>]*>([^<]*)</td>", row)]
        for row in re.findall(r'<tr class="mark"[^>]*>(.*?)</tr>', page, re.S)
    ]


def view_chart(page, view):
    """The JSON a dashboard view's chart is drawn from."""
    data = re.search(rf'<script id="{view}-data" type="application/json">(.*?)</script>', page)
    assert data, "no chart data"
    return json.loads(data[1])


def drill_rows(client, url, params):
    """The descriptions of the Transactions a drill-down lists."""
    page = client.get(url, params).content.decode()
    return [
        html.unescape(d)
        for d in re.findall(
            r'<tr id="transaction-\d+">\s*<td>[^<]*</td><td>[^<]*</td><td>([^<]*)</td>', page
        )
    ]
