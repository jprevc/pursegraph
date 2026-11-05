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


def cards(client):
    """The Categorizers page's cards, by heading, each as the text of everything in it."""
    page = client.get("/categorizers/").content.decode()
    found = re.finditer(
        r'<section class="panel".*?<h2[^>]*>(?P<heading>.*?)</h2>.*?</section>', page, re.S
    )
    return {page_text(card["heading"]): page_text(card[0]) for card in found}


def test_each_list_and_its_form_share_one_card(admin_client):
    shown = cards(admin_client)

    assert list(shown) == ["Tokens · 0", "Webhooks · 0"]
    assert "Create token" in shown["Tokens · 0"]
    assert "Add Webhook" in shown["Webhooks · 0"]


@pytest.mark.parametrize(
    "info",
    [
        "possibly outside this network, such as to a cloud service",
        "how many are waiting, never what they are",
    ],
)
def test_what_a_form_sends_is_behind_a_closed_toggle(admin_client, info):
    page = admin_client.get("/categorizers/").content.decode()
    disclosed = {
        id_: page_text(body)
        for id_, body in re.findall(r'<p id="([^"]+)"[^>]*data-disclosed>(.*?)</p>', page, re.S)
    }
    shown_by = next(id_ for id_, body in disclosed.items() if info in body)

    toggle = re.search(rf'<button[^>]*aria-controls="{shown_by}"[^>]*>', page)
    assert toggle, "no toggle"
    assert 'aria-expanded="false"' in toggle[0]
    assert 'aria-label="About ' in toggle[0]


def test_a_new_token_is_shown_once(admin_client):
    page = admin_client.post(
        "/categorizers/", {"name": "Qwen on the NAS"}, follow=True
    ).content.decode()

    assert "Token for Qwen on the NAS" in page_text(page)
    assert "Shown only now." in page_text(page)
    secret = re.search(r'value="(pgc_[^"]+)"', page)
    assert secret
    assert secret[1] not in admin_client.get("/categorizers/").content.decode()


def test_refreshing_after_creating_doesnt_create_another(admin_client):
    created = admin_client.post("/categorizers/", {"name": "Qwen on the NAS"})
    assert created.status_code == 302

    page = admin_client.get(created["Location"]).content.decode()
    refreshed = admin_client.get(created["Location"]).content.decode()

    assert "pgc_" in page
    assert "pgc_" not in refreshed
    assert len(tokens_shown(admin_client)) == 1


def test_a_token_needs_a_name(admin_client):
    response = admin_client.post("/categorizers/", {"name": ""})

    assert response.status_code == 200
    assert "pgc_" not in response.content.decode()
    assert tokens_shown(admin_client) == []


def test_each_token_shows_when_it_was_last_used(admin_client, client, monkeypatch):
    monkeypatch.setattr(timezone, "now", lambda: datetime(2026, 10, 27, 13, 2, tzinfo=UTC))
    used = create_token(admin_client, "Qwen on the NAS")
    create_token(admin_client, "Cloud")

    client.get(WAITING, headers={"Authorization": f"Bearer {used}"})

    assert tokens_shown(admin_client) == [
        "Cloud created 27 Oct 2026 by bor · never used",
        "Qwen on the NAS created 27 Oct 2026 by bor · last used 27 Oct 2026 14:02",
    ]


def test_revoking_is_confirmed_inline_and_removes_the_token(admin_client):
    create_token(admin_client, "Qwen on the NAS")
    revoke = revoke_url(admin_client)

    confirm = page_text(admin_client.get(revoke, HTTP_HX_REQUEST="true").content.decode())
    assert confirm.startswith("Revoke Qwen on the NAS ? Its Categorizer can't connect any more.")
    assert tokens_shown(admin_client) != []

    page = admin_client.post(revoke, follow=True).content.decode()

    assert "“Qwen on the NAS” is revoked" in page_text(page)
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
