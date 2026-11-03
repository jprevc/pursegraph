import re
from datetime import UTC, datetime

import pytest
from django.utils import timezone

from tests.conftest import page_text
from tests.test_categorizer_api import WAITING, create_token

pytestmark = pytest.mark.django_db


def tokens_shown(client):
    """The Categorizers page's token rows, as text."""
    page = client.get("/categorizers/").content.decode()
    return [page_text(row) for row in re.findall(r'<div class="t-who">(.*?)</div>', page, re.S)]


def revoke_url(client):
    """Where the first token's Revoke leads."""
    revoke = re.search(
        r'href="(/categorizers/\d+/revoke/)"', client.get("/categorizers/").content.decode()
    )
    assert revoke, "no Revoke"
    return revoke[1]


def test_the_page_says_where_transaction_text_may_go(admin_client):
    text = page_text(admin_client.get("/categorizers/").content.decode())

    assert "possibly outside this network, such as to a cloud service" in text
    assert "No Categorizer can connect yet" in text


def test_a_new_token_is_shown_once(admin_client):
    page = admin_client.post("/categorizers/", {"name": "Ollama on the NAS"}).content.decode()

    assert "Token for Ollama on the NAS" in page_text(page)
    assert "Shown only now." in page_text(page)
    secret = re.search(r'value="(pgc_[^"]+)"', page)
    assert secret
    assert secret[1] not in admin_client.get("/categorizers/").content.decode()


def test_a_token_needs_a_name(admin_client):
    response = admin_client.post("/categorizers/", {"name": ""})

    assert response.status_code == 200
    assert "pgc_" not in response.content.decode()
    assert tokens_shown(admin_client) == []


def test_each_token_shows_when_it_was_last_used(admin_client, client, monkeypatch):
    monkeypatch.setattr(timezone, "now", lambda: datetime(2026, 10, 27, 13, 2, tzinfo=UTC))
    used = create_token(admin_client, "Ollama on the NAS")
    create_token(admin_client, "Cloud")

    client.get(WAITING, headers={"Authorization": f"Bearer {used}"})

    assert tokens_shown(admin_client) == [
        "Cloud created 27 Oct 2026 by bor · never used",
        "Ollama on the NAS created 27 Oct 2026 by bor · last used 27 Oct 2026 14:02",
    ]


def test_revoking_is_confirmed_inline_and_removes_the_token(admin_client):
    create_token(admin_client, "Ollama on the NAS")
    revoke = revoke_url(admin_client)

    confirm = page_text(admin_client.get(revoke, HTTP_HX_REQUEST="true").content.decode())
    assert confirm.startswith("Revoke Ollama on the NAS ? Its Categorizer can't connect any more.")
    assert tokens_shown(admin_client) != []

    page = admin_client.post(revoke, follow=True).content.decode()

    assert "“Ollama on the NAS” is revoked" in page_text(page)
    assert tokens_shown(admin_client) == []
    assert admin_client.post(revoke).status_code == 404


def test_non_admins_are_forbidden(logged_in_client, admin_client):
    create_token(admin_client)
    revoke = revoke_url(admin_client)

    for url, data in [("/categorizers/", None), ("/categorizers/", {"name": "Mine"}), (revoke, {})]:
        response = logged_in_client.get(url) if data is None else logged_in_client.post(url, data)
        assert response.status_code == 403, url
    assert len(tokens_shown(admin_client)) == 1


def test_only_admins_see_the_categorizers_link(logged_in_client, admin_client, household):
    assert b'href="/categorizers/"' in admin_client.get("/").content
    assert b'href="/categorizers/"' not in logged_in_client.get("/").content
