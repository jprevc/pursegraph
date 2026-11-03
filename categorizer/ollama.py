"""The Ollama Categorizer that ships with Pursegraph: it fetches the Transactions waiting for a Suggestion through the
Categorizer API (ledger/api.py) and sends back what an Ollama server suggests.

It uses only that API and the standard library, not Django or Pursegraph's code, so it runs anywhere Python does,
such as on the Ollama machine: `python categorizer/ollama.py`. It reads

- PURSEGRAPH_URL: where Pursegraph is, such as http://192.168.1.20:8000;
- CATEGORIZER_TOKEN: a token from Pursegraph's Categorizers page;
- OLLAMA_URL: the Ollama server, such as http://192.168.1.10:11434.
"""

import json
import math
import os
import sys
import time
import urllib.error
import urllib.request

MODEL = "qwen3-vl:8b"

# Transactions fetched per run, so the loop notices new work and failures between batches.
BATCH_SIZE = 50

# Seconds between looks for new work while there is none.
IDLE_POLL = 10

# The household's conventions, from Pursegraph's default Category list.
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


class Unavailable(Exception):
    """Pursegraph or Ollama can't answer at all, such as when it is unreachable or refuses the token."""


class Pursegraph:
    """The Categorizer API of the Pursegraph at `base_url`, called with the Categorizer token `token`."""

    def __init__(self, base_url: str, token: str, *, timeout: float = 30):
        self.base_url = base_url.rstrip("/")
        self.token = token
        self.timeout = timeout

    def waiting(self, limit: int = BATCH_SIZE) -> dict:
        """The Subcategories to choose from and up to `limit` Transactions waiting for a Suggestion."""
        return self._call(f"/api/categorizer/v1/transactions/?limit={limit}")

    def send(self, transaction: int, suggestion: tuple[int, float] | None) -> dict:
        """Sends the Suggestion (Subcategory id, confidence) for the Transaction `transaction`, or None for none."""
        body: dict[str, int | float | None] = {"subcategory": None}
        if suggestion:
            body["subcategory"], body["confidence"] = suggestion
        return self._call(f"/api/categorizer/v1/transactions/{transaction}/suggestion/", body)

    def _call(self, path: str, body: dict | None = None) -> dict:
        request = urllib.request.Request(
            f"{self.base_url}{path}",
            None if body is None else json.dumps(body).encode(),
            {"Authorization": f"Bearer {self.token}", "Content-Type": "application/json"},
        )
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                return json.load(response)
        except urllib.error.HTTPError as err:
            if err.code == 401:
                raise Unavailable(
                    f"Pursegraph at {self.base_url} refused CATEGORIZER_TOKEN; is it revoked?"
                ) from err
            raise Unavailable(f"Pursegraph at {self.base_url}: {err}: {err.read()!r:.200}") from err
        except (OSError, ValueError) as err:  # URLError and timeouts are OSErrors
            raise Unavailable(f"Pursegraph at {self.base_url}: {err}") from err


class Ollama:
    """Suggests a Subcategory with the Ollama server at `base_url`.

    The model must answer with one of the Subcategories (a JSON-schema `enum`), and the confidence is its own
    probability of that answer: the product of the answer's token probabilities, from Ollama's `logprobs`, not a
    number the model reports about itself.
    """

    def __init__(self, base_url: str, *, model: str = MODEL, timeout: float = 120):
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.timeout = timeout

    def suggest(self, subcategories: list[dict], transaction: dict) -> tuple[int, float] | None:
        """The Suggestion (Subcategory id, confidence) for `transaction`, as the Categorizer API lists them, or None
        when Ollama's answer is unusable. Raises Unavailable when Ollama can't answer at all."""
        labels = {offered["id"]: offered["label"] for offered in subcategories}
        by_label: dict[str, int] = {}
        for pk, offered_label in labels.items():
            by_label.setdefault(offered_label, pk)
        body = {
            "model": self.model,
            "stream": False,
            "think": False,
            "keep_alive": "15m",
            "messages": [
                {"role": "system", "content": SYSTEM.format(options="\n".join(by_label))},
                {"role": "user", "content": _prompt(transaction, labels)},
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
        except (KeyError, TypeError, ValueError):
            return None
        return subcategory, answer_confidence(response.get("logprobs") or [], answer)

    def _post(self, body: dict) -> dict:
        if not self.base_url:
            raise Unavailable("no OLLAMA_URL is set")
        request = urllib.request.Request(
            f"{self.base_url}/api/chat",
            json.dumps(body).encode(),
            {"Content-Type": "application/json"},
        )
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                return json.load(response)
        except (OSError, ValueError) as err:  # URLError, HTTPError and timeouts are OSErrors
            raise Unavailable(f"Ollama at {self.base_url}: {err}") from err


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


def _prompt(transaction: dict, labels: dict[int, str]) -> str:
    lines = []
    # An example's Subcategory may be missing from `labels` if it was deleted between the queries of one fetch.
    examples = [e for e in transaction["examples"] if e["subcategory"] in labels]
    if examples:
        lines.append("Earlier corrections by this Household (other merchants):")
        for example in examples:
            detail = f" ({example['detail']})" if example["detail"] else ""
            lines.append(
                f"- {example['direction']} {example['description']}{detail}"
                f" -> {labels[example['subcategory']]}"
            )
        lines.append("")
    lines += [
        "Transaction to categorize:",
        f"Direction: {transaction['direction']}",
        f"Amount: {transaction['amount']} EUR",
        f"Description: {transaction['description']}",
    ]
    if transaction["detail"]:
        lines.append(f"Details: {transaction['detail']}")
    return "\n".join(lines)


def run_once(pursegraph: Pursegraph, ollama) -> int:
    """Asks `ollama` about a batch of the waiting Transactions and sends each answer to `pursegraph`. Returns how
    many it asked about; stops at the first failure, raising Unavailable."""
    waiting = pursegraph.waiting()
    for transaction in waiting["transactions"]:
        pursegraph.send(transaction["id"], ollama.suggest(waiting["subcategories"], transaction))
    return len(waiting["transactions"])


def backoff(attempt: int) -> int:
    """Seconds to wait after the `attempt`-th failure in a row: 5, 10, 20, … up to 5 minutes."""
    return min(5 * 2 ** (attempt - 1), 300)


def main(
    environ=os.environ,
    *,
    sleep=time.sleep,
    log=lambda line: print(line, file=sys.stderr, flush=True),
):
    """Categorizes for as long as it runs: a batch whenever Transactions wait, else a look every IDLE_POLL seconds,
    backing off while Pursegraph or Ollama can't answer. Wakes nothing: Ollama must be up by itself."""
    token = environ.get("CATEGORIZER_TOKEN", "")
    if not token:
        log(
            "no CATEGORIZER_TOKEN: create one on Pursegraph's Categorizers page and set it; waiting."
        )
        while True:
            sleep(IDLE_POLL)
    pursegraph = Pursegraph(environ.get("PURSEGRAPH_URL", "http://localhost:8000"), token)
    ollama = Ollama(environ.get("OLLAMA_URL", ""))
    log(
        f"Suggesting with {ollama.model} at {ollama.base_url or '(no OLLAMA_URL)'} for {pursegraph.base_url}."
    )
    failures = 0
    while True:
        try:
            asked = run_once(pursegraph, ollama)
        except Unavailable as error:
            failures += 1
            delay = backoff(failures)
            log(f"Suggestions unavailable, retrying in {delay}s: {error}")
            sleep(delay)
            continue
        if failures:
            log("Suggestions available again.")
        failures = 0
        if asked:
            log(f"Asked about {asked} Transactions.")
        else:
            sleep(IDLE_POLL)


if __name__ == "__main__":
    main()
