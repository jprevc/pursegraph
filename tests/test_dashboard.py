from datetime import date

import pytest

from ledger.models import Account, Transaction

pytestmark = pytest.mark.django_db


def test_empty_dashboard_asks_for_the_first_statement(logged_in_client):
    response = logged_in_client.get("/")

    assert response.status_code == 200
    assert b"Import your first Statement" in response.content
    assert b'href="/import/"' in response.content


def test_sidebar_links_to_import_and_review_queue(logged_in_client):
    content = logged_in_client.get("/").content

    assert b'href="/import/"' in content
    assert b'href="/review/"' in content
    assert b"Review queue" in content


def test_sidebar_pages_render_in_the_shell(logged_in_client):
    for url in ("/import/", "/review/"):
        response = logged_in_client.get(url)

        assert response.status_code == 200
        assert b"Pursegraph" in response.content


def test_htmx_and_echarts_are_vendored(logged_in_client):
    account = Account.objects.create(name="Joint N26", bank="n26")
    Transaction.objects.create(account=account, date=date.today(), amount=-1, description="Bread")

    content = logged_in_client.get("/").content

    assert b"/static/vendor/htmx.min.js" in content
    assert b"/static/vendor/echarts.min.js" in content
    assert b"unpkg.com" not in content
    assert b"jsdelivr" not in content
