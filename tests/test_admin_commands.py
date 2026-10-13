"""The shell-side admin commands, checked through what a Member can then do over HTTP."""

import pytest
from django.conf import settings
from django.core.management import CommandError, call_command

from members.management.commands._admin_command import PASSWORD_ENV
from tests.conftest import USERNAME, log_in

pytestmark = pytest.mark.django_db

NEW_PASSWORD = "a brand new passphrase"


@pytest.fixture(autouse=True)
def admin_password(monkeypatch):
    monkeypatch.setenv(PASSWORD_ENV, NEW_PASSWORD)


def test_create_admin_creates_an_admin_who_can_log_in(client, django_user_model):
    call_command("create_admin", "boss", "--noinput")

    log_in(client, "boss", NEW_PASSWORD)

    assert client.get("/").status_code == 200
    assert django_user_model.objects.get(username="boss").is_admin


def test_create_admin_refuses_an_existing_username(member):
    with pytest.raises(CommandError):
        call_command("create_admin", USERNAME, "--noinput")


def test_create_admin_needs_a_password_with_noinput(monkeypatch):
    monkeypatch.delenv(PASSWORD_ENV)

    with pytest.raises(CommandError):
        call_command("create_admin", "boss", "--noinput")


def test_create_admin_rejects_a_weak_password(monkeypatch):
    monkeypatch.setenv(PASSWORD_ENV, "123")

    with pytest.raises(CommandError):
        call_command("create_admin", "boss", "--noinput")


def test_recover_admin_restores_a_locked_out_deactivated_admin(client, member):
    member.is_active = False
    member.is_admin = False
    member.save()
    for _ in range(settings.AXES_FAILURE_LIMIT):
        log_in(client, password="wrong")

    call_command("recover_admin", USERNAME, "--noinput")
    log_in(client, password=NEW_PASSWORD)

    assert client.get("/").status_code == 200
    member.refresh_from_db()
    assert member.is_admin and member.is_active


def test_recover_admin_refuses_an_unknown_username():
    with pytest.raises(CommandError):
        call_command("recover_admin", "nobody", "--noinput")
