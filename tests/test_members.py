import re
from datetime import datetime, timedelta

import pytest
from django.contrib.auth import get_user_model
from django.contrib.auth.tokens import PasswordResetTokenGenerator
from django.test import Client

from tests.conftest import PASSWORD, log_in

pytestmark = pytest.mark.django_db

NEW_PASSWORD = "plum orchard lantern"


@pytest.fixture
def admin(django_user_model):
    return django_user_model.objects.create_user(username="boris", password=PASSWORD, is_admin=True)


@pytest.fixture
def admin_client(admin):
    """A client of its own, so tests can also use `client` for another visitor."""
    client = Client()
    client.force_login(admin)
    return client


def member_named(username):
    return get_user_model().objects.get(username=username)


def link_in(response):
    """The one-time link shown on the page, as a path."""
    [url] = re.findall(r'http://testserver(/set-password/[^"<\s]+)', response.content.decode())
    return url


def create_member(admin_client, username="cene", name="Cene Novak"):
    return admin_client.post("/members/new/", {"name": name, "username": username})


def set_password(link, password=NEW_PASSWORD):
    """Follow a one-time link as an anonymous visitor and set a password through it."""
    visitor = Client()
    form = visitor.get(link, follow=True)
    if b'name="new_password1"' not in form.content:
        return form
    return visitor.post(form.redirect_chain[-1][0], {"new_password1": password, "new_password2": password})


# Creating Members and invite links


def test_admin_creates_a_member_and_gets_an_invite_link(admin_client):
    response = create_member(admin_client)

    assert response.status_code == 200
    assert "Cene Novak" in response.content.decode()
    assert link_in(response)
    member = member_named("cene")
    assert member.get_full_name() == "Cene Novak"
    assert not member.has_usable_password()
    assert not member.is_admin


def test_new_member_sets_their_password_through_the_invite_and_logs_in(client, admin_client):
    link = link_in(create_member(admin_client))

    response = set_password(link)

    assert response.status_code == 302
    assert response["Location"] == "/login/"
    assert log_in(client, "cene", NEW_PASSWORD)["Location"] == "/"


def test_invite_link_is_unusable_after_use(admin_client):
    link = link_in(create_member(admin_client))
    set_password(link)

    response = set_password(link, "another fine password")

    assert b"no longer valid" in response.content
    assert member_named("cene").check_password(NEW_PASSWORD)


def later(monkeypatch, delta):
    """Move the one-time links' clock forward."""
    monkeypatch.setattr(PasswordResetTokenGenerator, "_now", lambda self: datetime.now() + delta)


def test_invite_link_is_valid_for_7_days(admin_client, monkeypatch):
    link = link_in(create_member(admin_client))

    later(monkeypatch, timedelta(days=6, hours=23))
    assert b'name="new_password1"' in Client().get(link, follow=True).content

    later(monkeypatch, timedelta(days=7, hours=1))
    response = set_password(link)
    assert b"no longer valid" in response.content
    assert not member_named("cene").has_usable_password()


def test_invite_link_with_a_tampered_token_is_refused(admin_client):
    link = link_in(create_member(admin_client))

    response = set_password(link[:-3] + "xyz/")

    assert b"no longer valid" in response.content


def test_set_password_page_needs_no_login():
    assert Client().get("/set-password/MQ/abc/").status_code == 200


def test_set_password_enforces_the_password_rules(admin_client):
    link = link_in(create_member(admin_client))

    response = set_password(link, "123")

    assert response.status_code == 200
    assert not member_named("cene").has_usable_password()


def test_username_must_be_unique(admin_client, member):
    response = create_member(admin_client, username=member.username)

    assert response.status_code == 200
    assert b"already exists" in response.content
    assert get_user_model().objects.count() == 2


# Password-reset links


def test_admin_generates_a_password_reset_link(client, admin_client, member):
    response = admin_client.post(f"/members/{member.pk}/reset-link/")

    assert response.status_code == 200
    set_password(link_in(response))
    assert log_in(client, member.username, NEW_PASSWORD)["Location"] == "/"


def test_reset_link_is_unusable_after_use(admin_client, member):
    link = link_in(admin_client.post(f"/members/{member.pk}/reset-link/"))
    set_password(link)

    assert b"no longer valid" in set_password(link, "another fine password").content


def test_reset_link_clears_a_failed_login_lockout(client, admin_client, member, settings):
    for _ in range(settings.AXES_FAILURE_LIMIT):
        log_in(client, password="wrong")
    link = link_in(admin_client.post(f"/members/{member.pk}/reset-link/"))

    set_password(link)

    assert log_in(client, member.username, NEW_PASSWORD).status_code == 302


# Deactivating Members and the admin flag


def test_admin_deactivates_a_member(admin_client, member):
    response = admin_client.post(f"/members/{member.pk}/active/", {"active": "0"})

    assert response.status_code == 302
    assert response["Location"] == "/members/"
    member.refresh_from_db()
    assert not member.is_active


def test_deactivated_member_cannot_log_in(client, admin_client, member):
    admin_client.post(f"/members/{member.pk}/active/", {"active": "0"})

    log_in(client)

    assert client.get("/").status_code == 302


def test_deactivating_ends_the_members_session(logged_in_client, admin_client, member):
    admin_client.post(f"/members/{member.pk}/active/", {"active": "0"})

    assert logged_in_client.get("/").status_code == 302


def test_deactivated_member_stays_on_their_accounts(admin_client, member):
    from ledger.models import Account, Bank

    account = Account.objects.create(name="Ana's Revolut", bank=Bank.REVOLUT)
    account.owners.add(member)

    admin_client.post(f"/members/{member.pk}/active/", {"active": "0"})

    assert list(account.owners.all()) == [member]


def test_deactivated_members_links_do_not_work(admin_client, member):
    link = link_in(admin_client.post(f"/members/{member.pk}/reset-link/"))
    admin_client.post(f"/members/{member.pk}/active/", {"active": "0"})

    assert b"no longer valid" in set_password(link).content


def test_admin_reactivates_a_member(admin_client, member):
    member.is_active = False
    member.save()

    admin_client.post(f"/members/{member.pk}/active/", {"active": "1"})

    member.refresh_from_db()
    assert member.is_active


def test_members_are_never_deleted(admin_client, member):
    assert admin_client.post(f"/members/{member.pk}/delete/").status_code == 404
    assert admin_client.delete(f"/members/{member.pk}/active/").status_code == 405


def test_admin_grants_and_removes_the_admin_flag(admin_client, member):
    admin_client.post(f"/members/{member.pk}/admin/", {"admin": "1"})
    member.refresh_from_db()
    assert member.is_admin

    admin_client.post(f"/members/{member.pk}/admin/", {"admin": "0"})
    member.refresh_from_db()
    assert not member.is_admin


def test_deactivating_the_last_active_admin_is_refused(admin_client, admin):
    response = admin_client.post(f"/members/{admin.pk}/active/", {"active": "0"}, follow=True)

    assert b"last active admin" in response.content
    admin.refresh_from_db()
    assert admin.is_active


def test_demoting_the_last_active_admin_is_refused(admin_client, admin, member):
    response = admin_client.post(f"/members/{admin.pk}/admin/", {"admin": "0"}, follow=True)

    assert b"last active admin" in response.content
    admin.refresh_from_db()
    assert admin.is_admin


def test_an_inactive_admin_does_not_count_as_another_active_admin(admin_client, admin, django_user_model):
    django_user_model.objects.create_user(username="dora", is_admin=True, is_active=False)

    admin_client.post(f"/members/{admin.pk}/admin/", {"admin": "0"})

    admin.refresh_from_db()
    assert admin.is_admin


def test_an_admin_can_step_down_when_another_admin_is_active(admin_client, admin, member):
    member.is_admin = True
    member.save()

    admin_client.post(f"/members/{admin.pk}/admin/", {"admin": "0"})

    admin.refresh_from_db()
    assert not admin.is_admin


# The Members page and access


def test_members_page_lists_members(admin_client, member):
    page = admin_client.get("/members/").content.decode()

    assert "boris" in page
    assert "ana" in page


def test_sidebar_links_to_members_for_admins_only(admin_client, logged_in_client):
    assert b'href="/members/"' in admin_client.get("/").content
    assert b'href="/members/"' not in logged_in_client.get("/").content


@pytest.mark.parametrize("method, path", [
    ("get", "/members/"),
    ("get", "/members/new/"),
    ("post", "/members/new/"),
    ("post", "/members/{pk}/reset-link/"),
    ("post", "/members/{pk}/active/"),
    ("post", "/members/{pk}/admin/"),
])
def test_admin_pages_are_forbidden_to_non_admins(logged_in_client, member, method, path):
    response = getattr(logged_in_client, method)(path.format(pk=member.pk), {"active": "0", "admin": "1"})

    assert response.status_code == 403
    member.refresh_from_db()
    assert member.is_active
    assert not member.is_admin
