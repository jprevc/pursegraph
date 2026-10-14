import json
import math
import os
from decimal import Decimal

import pytest

from ledger.models import Subcategory
from ledger.ollama import OllamaSuggester, answer_confidence, label
from ledger.suggestions import Example, Query, SuggestionsUnavailable

pytestmark = pytest.mark.django_db


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


def query(**overrides):
    subcategories = list(Subcategory.objects.select_related("category"))
    return Query(
        **{
            "direction": "out",
            "amount": Decimal("12.34"),
            "description": "Mercator Žalec",
            "detail": "Card Payment",
            "subcategories": subcategories,
            "examples": [
                Example(
                    "out",
                    "Petrol",
                    "",
                    Subcategory.objects.get(name="Fuel"),
                )
            ],
            **overrides,
        }
    )


def test_the_request_restricts_the_answer_to_the_subcategories(monkeypatch):
    sent = {}

    def fake_post(self, body):
        sent.update(body)
        answer = "Food > Groceries"
        content = json.dumps({"subcategory": answer})
        return {
            "message": {"content": content},
            "logprobs": tokens((content, math.log(0.95))),
        }

    monkeypatch.setattr(OllamaSuggester, "_post", fake_post)

    suggestion = OllamaSuggester("http://ollama.invalid:11434").suggest(query())

    assert suggestion.subcategory.name == "Groceries"
    assert suggestion.confidence == pytest.approx(0.95)
    assert sent["model"] == "qwen3-vl:8b"
    assert (sent["think"], sent["logprobs"], sent["options"]["temperature"]) == (False, True, 0)
    enum = sent["format"]["properties"]["subcategory"]["enum"]
    assert len(enum) == Subcategory.objects.count()
    assert "Transport > Fuel" in enum
    prompt = "\n".join(m["content"] for m in sent["messages"])
    assert "Mercator Žalec" in prompt
    assert "Petrol" in prompt and "Transport > Fuel" in prompt
    assert "Cash withdrawal" in prompt  # the household conventions


def test_an_answer_in_thinking_is_read_too(monkeypatch):
    content = '{"subcategory": "Food > Groceries"}'
    monkeypatch.setattr(
        OllamaSuggester,
        "_post",
        lambda self, body: {
            "message": {"content": "", "thinking": content},
            "logprobs": tokens((content, math.log(0.5))),
        },
    )

    suggestion = OllamaSuggester("http://ollama.invalid:11434").suggest(query())

    assert (suggestion.subcategory.name, suggestion.confidence) == ("Groceries", pytest.approx(0.5))


def test_an_unreachable_server_is_unavailable():
    with pytest.raises(SuggestionsUnavailable):
        OllamaSuggester("http://127.0.0.1:9", timeout=2).suggest(query())


def test_no_configured_server_is_unavailable():
    with pytest.raises(SuggestionsUnavailable):
        OllamaSuggester("").suggest(query())


def test_labels_name_the_category():
    assert label(Subcategory.objects.get(name="Groceries")) == "Food > Groceries"


@pytest.mark.skipif(
    not os.environ.get("OLLAMA_URL"), reason="set OLLAMA_URL to test against a real Ollama"
)
def test_a_real_ollama_suggests_a_subcategory():
    suggestion = OllamaSuggester(os.environ["OLLAMA_URL"]).suggest(query())

    assert suggestion.subcategory in query().subcategories
    assert 0 < suggestion.confidence <= 1
