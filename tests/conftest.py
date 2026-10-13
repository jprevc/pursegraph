import pytest

from ledger.models import Account

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
