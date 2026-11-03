"""The Ollama Categorizer that ships with Pursegraph (categorizer/ollama.py), against a running Pursegraph."""

import json
import math
import os
import subprocess
import sys
from pathlib import Path

import pytest

from categorizer.ollama import (
    Ollama,
    Pursegraph,
    Unavailable,
    answer_confidence,
    main,
    run_once,
)
from ledger import categorizers
from ledger.models import Source, Transaction
from tests.conftest import subcategory_id
from tests.test_rules import make_transaction

# Pursegraph serves the API from another thread, so its data must be committed.
live = pytest.mark.django_db(transaction=True, serialized_rollback=True)


class FakeOllama:
    """Answers with a scripted label and confidence per description, and records what it was asked."""

    def __init__(self, answers=None, default=("Other > Miscellaneous", 0.5)):
        self.answers = answers or {}
        self.default = default
        self.asked: list[str] = []

    def suggest(self, subcategories, transaction):
        self.asked.append(transaction["description"])
        answer = self.answers.get(transaction["description"], self.default)
        if answer is None:
            return None
        label, confidence = answer
        (subcategory,) = [s["id"] for s in subcategories if s["label"] == label]
        return subcategory, confidence


@pytest.fixture
def pursegraph(live_server, django_user_model):
    admin = django_user_model.objects.create_user(username="bor", is_admin=True)
    _token, secret = categorizers.create("Ollama on the NAS", admin)
    return Pursegraph(live_server.url, secret)


@live
def test_a_run_sends_a_suggestion_for_each_waiting_transaction(pursegraph):
    make_transaction("Corner Shop")
    make_transaction("Hiša kave")
    ollama = FakeOllama({"Corner Shop": ("Food > Groceries", 0.95)})

    assert run_once(pursegraph, ollama) == 2

    corner = Transaction.objects.get(description="Corner Shop")
    assert (corner.subcategory_id, corner.source) == (
        subcategory_id("Food", "Groceries"),
        Source.LLM,
    )
    hisa = Transaction.objects.get(description="Hiša kave")
    assert (hisa.suggested_subcategory_id, hisa.subcategory) == (
        subcategory_id("Other", "Miscellaneous"),
        None,
    )
    assert run_once(pursegraph, FakeOllama()) == 0


def test_it_runs_on_its_own_without_django_or_pursegraphs_code():
    script = Path(__file__).parent.parent / "categorizer" / "ollama.py"
    imported = subprocess.run(
        [
            sys.executable,
            "-I",
            "-c",
            "import runpy, sys; runpy.run_path(sys.argv[1]); print(*sys.modules)",
            script,
        ],
        capture_output=True,
        text=True,
        check=True,
    ).stdout.split()

    assert not [m for m in imported if m.split(".")[0] in ("django", "ledger", "pursegraph")]


class Stop(Exception):
    pass


def running(environ, waits=3):
    """Runs the Categorizer as its script does, until it has waited `waits` times; returns how long each wait was
    and what it logged."""
    slept: list[float] = []
    logged: list[str] = []

    def sleep(seconds):
        slept.append(seconds)
        if len(slept) == waits:
            raise Stop

    with pytest.raises(Stop):
        main(environ, sleep=sleep, log=logged.append)
    return slept, logged


def test_without_a_token_it_says_so_and_waits():
    slept, logged = running({"PURSEGRAPH_URL": "http://127.0.0.1:9", "OLLAMA_URL": "x"})

    assert len(slept) == 3
    assert logged == [
        "no CATEGORIZER_TOKEN: create one on Pursegraph's Categorizers page and set it; waiting."
    ]


@live
def test_while_nothing_waits_it_looks_every_10_seconds(pursegraph):
    slept, _logged = running(
        {
            "PURSEGRAPH_URL": pursegraph.base_url,
            "CATEGORIZER_TOKEN": pursegraph.token,
            "OLLAMA_URL": "http://127.0.0.1:9",
        }
    )

    assert slept == [10, 10, 10]


@live
def test_while_ollama_doesnt_answer_it_backs_off(pursegraph):
    make_transaction("Corner Shop")

    slept, logged = running(
        {
            "PURSEGRAPH_URL": pursegraph.base_url,
            "CATEGORIZER_TOKEN": pursegraph.token,
            "OLLAMA_URL": "http://127.0.0.1:9",
        },
        waits=9,
    )

    assert slept == [5, 10, 20, 40, 80, 160, 300, 300, 300]
    assert logged[-1].startswith(
        "Suggestions unavailable, retrying in 300s: Ollama at http://127.0.0.1:9"
    )
    assert Transaction.objects.get(description="Corner Shop").confidence is None


def tokens(*pieces):
    return [{"token": text, "logprob": logprob} for text, logprob in pieces]


def test_confidence_is_the_product_of_the_answers_token_probabilities():
    logprobs = tokens(
        ('{"', -0.5),
        ("sub", 0.0),
        ('category":"', -0.2),
        ("Food", math.log(0.9)),
        (" > ", math.log(0.8)),
        ("Groceries", math.log(0.5)),
        ('"}', -1.0),
    )

    assert answer_confidence(logprobs, "Food > Groceries") == pytest.approx(0.9 * 0.8 * 0.5)


def test_confidence_counts_a_token_straddling_the_answer():
    logprobs = tokens(('{"subcategory":"Food', math.log(0.5)), (' > Other"}', math.log(0.5)))

    assert answer_confidence(logprobs, "Food > Other") == pytest.approx(0.25)


def test_an_answer_not_found_in_the_tokens_has_no_confidence():
    assert answer_confidence(tokens(("{}", 0.0)), "Food > Groceries") == 0.0


# As the Categorizer API lists them.
SUBCATEGORIES = [
    {"id": 1, "label": "Food > Groceries"},
    {"id": 2, "label": "Food > Restaurants & cafés"},
    {"id": 3, "label": "Transport > Fuel"},
    {"id": 4, "label": "Other > Cash withdrawal"},
]
TRANSACTION = {
    "id": 7,
    "direction": "out",
    "amount": "12.34",
    "description": "Mercator Žalec",
    "detail": "Card Payment",
    "examples": [{"direction": "out", "description": "Petrol", "detail": "", "subcategory": 3}],
}


def answering(monkeypatch, message, logprobs=()):
    """Has Ollama answer `message`; returns what it is sent."""
    sent = {}

    def fake_post(self, body):
        sent.update(body)
        return {"message": message, "logprobs": list(logprobs)}

    monkeypatch.setattr(Ollama, "_post", fake_post)
    return sent


def test_the_request_restricts_the_answer_to_the_subcategories(monkeypatch):
    content = json.dumps({"subcategory": "Food > Groceries"})
    sent = answering(monkeypatch, {"content": content}, tokens((content, math.log(0.95))))

    answer = Ollama("http://ollama.invalid:11434").suggest(SUBCATEGORIES, TRANSACTION)

    assert answer == (1, pytest.approx(0.95))
    assert sent["model"] == "qwen3-vl:8b"
    assert (sent["think"], sent["logprobs"], sent["options"]["temperature"]) == (False, True, 0)
    assert sent["format"]["properties"]["subcategory"]["enum"] == [
        s["label"] for s in SUBCATEGORIES
    ]
    prompt = "\n".join(m["content"] for m in sent["messages"])
    assert "Mercator Žalec" in prompt and "12.34 EUR" in prompt and "Card Payment" in prompt
    assert "- out Petrol -> Transport > Fuel" in prompt
    assert "Cash withdrawal" in prompt  # the household conventions


def test_an_answer_in_thinking_is_read_too(monkeypatch):
    content = '{"subcategory": "Food > Groceries"}'
    answering(monkeypatch, {"content": "", "thinking": content}, tokens((content, math.log(0.5))))

    assert Ollama("http://ollama.invalid:11434").suggest(SUBCATEGORIES, TRANSACTION) == (
        1,
        pytest.approx(0.5),
    )


def test_an_answer_outside_the_subcategories_is_no_suggestion(monkeypatch):
    answering(monkeypatch, {"content": '{"subcategory": "Food > Caviar"}'})

    assert Ollama("http://ollama.invalid:11434").suggest(SUBCATEGORIES, TRANSACTION) is None


def test_an_unreachable_ollama_is_unavailable():
    with pytest.raises(Unavailable):
        Ollama("http://127.0.0.1:9", timeout=2).suggest(SUBCATEGORIES, TRANSACTION)


@pytest.mark.skipif(
    not os.environ.get("OLLAMA_URL"), reason="set OLLAMA_URL to test against a real Ollama"
)
def test_a_real_ollama_suggests_a_subcategory():
    answer = Ollama(os.environ["OLLAMA_URL"]).suggest(SUBCATEGORIES, TRANSACTION)

    assert answer
    assert answer[0] in [s["id"] for s in SUBCATEGORIES]
    assert 0 < answer[1] <= 1
