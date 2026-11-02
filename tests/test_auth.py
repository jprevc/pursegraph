import re
from datetime import timedelta

import pytest
from axes.models import AccessAttempt
from django.conf import settings
from django.utils import timezone

from members.login import locked_out
from tests.conftest import USERNAME, log_in, page_text

pytestmark = pytest.mark.django_db


def test_unauthenticated_request_redirects_to_login(client):
    response = client.get("/")

    assert response.status_code == 302
    assert response["Location"] == "/login/?next=/"


def test_login_page_renders(client):
    response = client.get("/login/")

    assert response.status_code == 200
    assert b'name="username"' in response.content
    assert b'name="password"' in response.content


def test_login_takes_member_to_dashboard(client, member):
    response = log_in(client)

    assert response.status_code == 302
    assert response["Location"] == "/"
    assert b"Set up the Household" in client.get("/").content


def test_login_session_lasts_30_days(client, member):
    response = log_in(client)

    assert response.cookies[settings.SESSION_COOKIE_NAME]["max-age"] == 30 * 24 * 60 * 60


def test_wrong_password_is_rejected(client, member):
    response = log_in(client, password="wrong")

    assert response.status_code == 200
    assert client.get("/").status_code == 302


def test_inactive_member_cannot_log_in(client, member):
    member.is_active = False
    member.save()

    log_in(client)

    assert client.get("/").status_code == 302


def test_repeated_failed_logins_lock_the_member_out(client, member):
    for _ in range(settings.AXES_FAILURE_LIMIT):
        log_in(client, password="wrong")

    response = log_in(client)

    assert response.status_code == 429
    assert client.get("/").status_code == 302


def test_logout_ends_the_session(logged_in_client):
    response = logged_in_client.post("/logout/")

    assert response.status_code == 302
    assert response["Location"] == "/login/"
    assert logged_in_client.get("/").status_code == 302


def test_django_admin_is_not_exposed(logged_in_client):
    assert logged_in_client.get("/admin/").status_code == 404


def test_no_email_password_reset_page(client):
    assert client.get("/password_reset/").status_code in (302, 404)


def field(page, name):
    """The `<input>` tag of the login form's field `name`."""
    tag = re.search(rf'<input[^>]*name="{name}"[^>]*>', page)
    assert tag, f"no field {name!r}"
    return tag[0]


def described_by(page, name):
    """The words of the messages the field `name` points at with aria-describedby."""
    ids = re.search(r'aria-describedby="([^"]*)"', field(page, name))
    if not ids:
        return ""
    messages = [re.search(rf'<p[^>]*id="{i}"[^>]*>(.*?)</p>', page, re.S) for i in ids[1].split()]
    assert all(messages), "aria-describedby names a missing message"
    return " ".join(page_text(m[1]) for m in messages if m)


def test_an_empty_username_is_named_under_its_field_which_takes_focus(client, member):
    page = log_in(client, username="").content.decode()

    assert 'aria-invalid="true"' in field(page, "username")
    assert "autofocus" in field(page, "username")
    assert described_by(page, "username") == "Enter your username."
    assert "aria-invalid" not in field(page, "password")


def test_an_empty_password_is_named_under_its_field(client, member):
    page = log_in(client, password="").content.decode()

    assert described_by(page, "password") == "Enter your password."
    assert "autofocus" in field(page, "password")
    assert "aria-invalid" not in field(page, "username")


def test_a_wrong_pair_is_said_under_the_password_and_both_fields_point_at_it(client, member):
    page = log_in(client, password="wrong").content.decode()

    assert described_by(page, "password") == "That username and password don't match."
    assert described_by(page, "username") == "That username and password don't match."
    assert "autofocus" in field(page, "password")
    assert f'value="{USERNAME}"' in field(page, "username")


@pytest.mark.parametrize(
    ("wrong_tries", "left"), [(1, None), (2, None), (3, "2 more tries"), (4, "1 more try")]
)
def test_tries_left_are_said_from_the_third_wrong_try(client, member, wrong_tries, left):
    for _ in range(wrong_tries):
        response = log_in(client, password="wrong")
    said = described_by(response.content.decode(), "password")

    if left:
        assert said == (
            f"That username and password don't match. {left} before {USERNAME} is locked for an hour "
            "on this device."
        )
    else:
        assert said == "That username and password don't match."


def test_tries_left_are_said_for_a_username_that_doesnt_exist(client):
    for _ in range(3):
        response = log_in(client, username="nobody", password="wrong")

    assert "2 more tries before nobody is locked" in page_text(response.content.decode())


def test_the_login_page_says_who_to_ask_for_a_forgotten_password(client):
    page = page_text(client.get("/login/").content.decode())

    assert "Welcome back" in page
    assert "ask an admin of the Household for a reset link" in page
    assert "The whole Household's money in one private picture." in page


def lock_out(client, username=USERNAME):
    for _ in range(settings.AXES_FAILURE_LIMIT):
        response = log_in(client, username=username, password="wrong")
    return response


def test_the_locked_out_page_names_the_username_and_when_the_lock_lifts(client, member):
    response = lock_out(client)

    last_try = AccessAttempt.objects.get().attempt_time
    lifts = timezone.localtime(last_try + timedelta(hours=1)).strftime("%H:%M")
    assert response.status_code == 429
    text = page_text(response.content.decode())
    assert f"You can try again in 60 min at {lifts}" in text
    assert "Too many wrong passwords for ana on this device" in text
    assert "Or, right away: Ask an admin for a password-reset link." in text
    assert "That also unlocks ana" in text
    assert '<div class="locked" role="alert">' in response.content.decode()


def test_a_try_while_locked_out_starts_the_hour_again(client, member):
    lock_out(client)
    AccessAttempt.objects.update(attempt_time=timezone.now() - timedelta(minutes=30))

    response = log_in(client)

    assert response.status_code == 429
    assert "You can try again in 60 min" in page_text(response.content.decode())


def test_the_minutes_left_round_up(client, member, rf):
    lock_out(client)
    AccessAttempt.objects.update(attempt_time=timezone.now() - timedelta(minutes=2, seconds=30))
    request = rf.post("/login/", REMOTE_ADDR="127.0.0.1")

    page = locked_out(request, None, {"username": USERNAME}).content.decode()

    assert "You can try again in 58 min" in page_text(page)


def test_log_in_as_someone_else_returns_to_an_empty_form(client, member):
    page = lock_out(client).content.decode()

    assert re.search(r'<a class="button block" href="/login/">Log in as someone else</a>', page)
    assert 'value=""' in field(client.get("/login/").content.decode(), "username")
