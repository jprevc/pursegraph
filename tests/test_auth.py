import pytest
from django.conf import settings

from tests.conftest import PASSWORD

pytestmark = pytest.mark.django_db


def log_in(client, username="ana", password=PASSWORD):
    return client.post("/login/", {"username": username, "password": password})


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
    assert client.get("/").status_code == 200


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
