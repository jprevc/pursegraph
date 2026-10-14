"""The Suggester backed by the local Ollama server on the LAN; Transaction text never leaves it.

The model must answer with one of the Subcategories (a JSON-schema `enum`), and the confidence is
its own probability of that answer: the product of the answer's token probabilities, from
Ollama's `logprobs`, not a number the model reports about itself.
"""

import json
import math
import urllib.error
import urllib.request

from .models import Subcategory
from .suggestions import NoSuggestion, Query, Suggestion, SuggestionsUnavailable

MODEL = "qwen3-vl:8b"

# Stored data, so not translated. The household's conventions, from the default Category list.
SYSTEM = """You categorize one household bank Transaction (a Household in Slovenia; merchant names and
purposes are often Slovenian) into exactly one Subcategory from this list:
{options}

Conventions of this Household:
- Transfers between the Household's own Accounts have no Category and never reach you.
- Money in at a shop is a Refund: use the shop's spending Subcategory, not income.
- Payments to a private person: categorize by purpose if the purpose text makes it clear,
  otherwise "Other > Payments to people".
- Cash withdrawals count as spending: "Other > Cash withdrawal".
Answer with JSON only."""


def label(subcategory: Subcategory) -> str:
    """How the model sees a Subcategory: "Category > Subcategory"."""
    return f"{subcategory.category.name} > {subcategory.name}"


class OllamaSuggester:
    def __init__(self, base_url: str, *, model: str = MODEL, timeout: float = 120):
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.timeout = timeout

    def suggest(self, query: Query) -> Suggestion:
        by_label: dict[str, Subcategory] = {}
        for subcategory in query.subcategories:
            by_label.setdefault(label(subcategory), subcategory)
        body = {
            "model": self.model,
            "stream": False,
            "think": False,
            "keep_alive": "15m",
            "messages": [
                {"role": "system", "content": SYSTEM.format(options="\n".join(by_label))},
                {"role": "user", "content": _prompt(query)},
            ],
            "format": {
                "type": "object",
                "properties": {"subcategory": {"type": "string", "enum": list(by_label)}},
                "required": ["subcategory"],
            },
            "logprobs": True,
            "options": {"temperature": 0, "num_ctx": 8192},
        }
        response = self._post(body)
        try:
            message = response["message"]
            # qwen3-vl answers in `thinking` even with `think: false`.
            answer = json.loads(message.get("content") or message.get("thinking"))["subcategory"]
            subcategory = by_label[answer]
        except (KeyError, TypeError, ValueError) as err:
            raise NoSuggestion(f"unusable answer from Ollama: {response!r:.200}") from err
        return Suggestion(subcategory, answer_confidence(response.get("logprobs") or [], answer))

    def _post(self, body: dict) -> dict:
        if not self.base_url:
            raise SuggestionsUnavailable("no Ollama URL is configured (OLLAMA_URL)")
        request = urllib.request.Request(
            f"{self.base_url}/api/chat",
            json.dumps(body).encode(),
            {"Content-Type": "application/json"},
        )
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                return json.load(response)
        except (OSError, ValueError) as err:  # URLError, HTTPError and timeouts are OSErrors
            raise SuggestionsUnavailable(f"Ollama at {self.base_url}: {err}") from err


def answer_confidence(logprobs: list[dict], answer: str) -> float:
    """The product of the probabilities of the tokens that spell `answer`, or 0 if they don't."""
    text = "".join(token["token"] for token in logprobs)
    # As it appears inside the JSON string, with or without non-ASCII letters escaped.
    for spelling in (json.dumps(answer, ensure_ascii=False)[1:-1], json.dumps(answer)[1:-1]):
        start = text.find(spelling)
        if answer and start >= 0:
            end = start + len(spelling)
            break
    else:
        return 0.0
    total, position = 0.0, 0
    for token in logprobs:
        if position < end and position + len(token["token"]) > start:
            total += token["logprob"]
        position += len(token["token"])
    return math.exp(total)


def _prompt(query: Query) -> str:
    lines = []
    if query.examples:
        lines.append("Earlier corrections by this Household (other merchants):")
        for example in query.examples:
            detail = f" ({example.detail})" if example.detail else ""
            lines.append(
                f"- {example.direction} {example.description}{detail} -> {label(example.subcategory)}"
            )
        lines.append("")
    lines += [
        "Transaction to categorize:",
        f"Direction: {query.direction}",
        f"Amount: {query.amount:.2f} EUR",
        f"Description: {query.description}",
    ]
    if query.detail:
        lines.append(f"Details: {query.detail}")
    return "\n".join(lines)
