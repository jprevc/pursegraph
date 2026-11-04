"""An example Categorizer for Pursegraph: it suggests Subcategories with an Ollama server.

Copy it and fit it to your Household; docs/operations.md ("Example: an Ollama Categorizer") explains how to run
it. It needs only Python 3 (3.10 or later) and its standard library, and Pursegraph's CI runs it, so it keeps working.

It waits for Pursegraph's Webhook: it listens on PORT and, for a POST to /<WEBHOOK_SECRET>, fetches the Transactions
waiting for a Suggestion through the Categorizer API, asks Ollama about each and sends the answers back, until
nothing is waiting. It does that once when it starts too. It reads

- PURSEGRAPH_URL: where it reaches Pursegraph, such as http://192.168.1.20:8000;
- CATEGORIZER_TOKEN: a token from Pursegraph's Categorizers page;
- OLLAMA_URL: the Ollama server, such as http://localhost:11434;
- WEBHOOK_SECRET: the secret at the end of the Webhook's URL, http://<this host>:<PORT>/<WEBHOOK_SECRET>;
- PORT: where it listens, 8765 by default;
- OLLAMA_MODEL: the model to ask, qwen3-vl:8b by default.

It assumes Ollama is up: when a call to Ollama or Pursegraph fails, it logs why and stops until the next delivery.
"""

import hmac
import json
import math
import os
import sys
import threading
import urllib.error
import urllib.request
from collections.abc import Callable, Mapping
from http.server import BaseHTTPRequestHandler, HTTPServer

# Transactions fetched at a time.
BATCH_SIZE = 50

# The Household's conventions, from Pursegraph's default Category list. Fit them to yours.
SYSTEM_PROMPT = """You categorize one household bank Transaction (a Household in Slovenia; merchant names and
purposes are often Slovenian) into exactly one Subcategory from this list:
{options}

Conventions of this Household:
- Transfers between the Household's own Accounts have no Category and never reach you.
- Money in at a shop is a Refund: use the shop's spending Subcategory, not income.
- Payments to a private person: categorize by purpose if the purpose text makes it clear,
  otherwise "Other > Payments to people".
- Cash withdrawals count as spending: "Other > Cash withdrawal".
Answer with JSON only."""


def log(line: str) -> None:
    print(line, file=sys.stderr, flush=True)


class CallFailed(Exception):
    """A call to Pursegraph or Ollama failed: it was unreachable, timed out or answered with an error."""


def _call(url: str, body: dict | None, headers: dict[str, str], timeout: float) -> dict:
    request = urllib.request.Request(
        url,
        None if body is None else json.dumps(body).encode(),
        {"Content-Type": "application/json", **headers},
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return json.load(response)
    except urllib.error.HTTPError as err:
        raise CallFailed(f"{url}: {err}: {err.read()!r:.200}") from err
    except (OSError, ValueError) as err:  # URLError and timeouts are OSErrors
        raise CallFailed(f"{url}: {err}") from err


class Pursegraph:
    """The Categorizer API of the Pursegraph at `base_url`, called with the Categorizer token `token`."""

    def __init__(self, base_url: str, token: str, *, timeout: float = 30):
        self.base_url = base_url.rstrip("/")
        self.token = token
        self.timeout = timeout

    def waiting(self) -> dict:
        """The Subcategories to choose from and the oldest Transactions waiting for a Suggestion."""
        return self._call(f"/api/categorizer/v1/transactions/?limit={BATCH_SIZE}")

    def send(self, transaction_id: int, suggestion: tuple[int, float] | None) -> None:
        """Sends the Suggestion (Subcategory id, confidence) for the Transaction `transaction_id`, or None for
        none, so the Transaction waits in the Review queue without one."""
        body: dict[str, int | float | None] = {"subcategory": None}
        if suggestion:
            body["subcategory"], body["confidence"] = suggestion
        self._call(f"/api/categorizer/v1/transactions/{transaction_id}/suggestion/", body)

    def _call(self, path: str, body: dict | None = None) -> dict:
        return _call(
            self.base_url + path, body, {"Authorization": f"Bearer {self.token}"}, self.timeout
        )


class Ollama:
    """Suggests a Subcategory with the model `model` on the Ollama server at `base_url`.

    The model must answer with one of the Subcategories (a JSON-schema `enum`), and the confidence is its own
    probability of that answer: the product of the answer's token probabilities, from Ollama's `logprobs`, not a
    number the model reports about itself. Pursegraph auto-accepts a Suggestion at least as sure as its threshold,
    so the confidence must mean something.
    """

    def __init__(self, base_url: str, model: str, *, timeout: float = 120):
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.timeout = timeout

    def suggest(self, subcategories: list[dict], transaction: dict) -> tuple[int, float] | None:
        """The Suggestion (Subcategory id, confidence) for `transaction`, as the Categorizer API lists them, or None
        when Ollama's answer is unusable."""
        labels = {offered["id"]: offered["label"] for offered in subcategories}
        by_label: dict[str, int] = {}
        for pk, label in labels.items():
            by_label.setdefault(label, pk)
        body = {
            "model": self.model,
            "stream": False,
            "think": False,
            "keep_alive": "15m",
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT.format(options="\n".join(by_label))},
                {"role": "user", "content": prompt(transaction, labels)},
            ],
            "format": {
                "type": "object",
                "properties": {"subcategory": {"type": "string", "enum": list(by_label)}},
                "required": ["subcategory"],
            },
            "logprobs": True,
            "options": {"temperature": 0, "num_ctx": 8192},
        }
        response = _call(f"{self.base_url}/api/chat", body, {}, self.timeout)
        try:
            message = response["message"]
            # qwen3-vl answers in `thinking` even with `think: false`.
            answer = json.loads(message.get("content") or message.get("thinking"))["subcategory"]
            subcategory = by_label[answer]
        except (KeyError, TypeError, ValueError):
            return None
        return subcategory, answer_confidence(response.get("logprobs") or [], answer)


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


def prompt(transaction: dict, labels: dict[int, str]) -> str:
    """What Ollama is told about `transaction`, with the Household's earlier choices as examples."""
    lines = []
    # An example's Subcategory may be missing from `labels` if it was deleted during the fetch.
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


def run(pursegraph: Pursegraph, ollama: Ollama) -> None:
    """Suggests a Subcategory for every Transaction waiting, a batch at a time, until none is waiting. Stops at the
    first failed call: the Transactions not done yet wait for the next run."""
    answered = 0
    try:
        while (batch := pursegraph.waiting())["transactions"]:
            for transaction in batch["transactions"]:
                pursegraph.send(
                    transaction["id"], ollama.suggest(batch["subcategories"], transaction)
                )
                answered += 1
    except CallFailed as error:
        log(f"Stopped after answering {answered} Transactions: {error}")
        return
    log(f"Answered {answered} Transactions; none is waiting now.")


class Runner:
    """Calls `work` on a background thread of its own each time it is asked to, one call at a time. Asked while
    `work` runs, it calls `work` once more afterwards, however often it was asked meanwhile."""

    def __init__(self, work: Callable[[], None]):
        self._work = work
        self._asked = threading.Event()
        threading.Thread(target=self._loop, name="categorizer", daemon=True).start()

    def ask(self) -> None:
        self._asked.set()

    def _loop(self) -> None:
        while True:
            self._asked.wait()
            # Cleared before the work starts, so asking during it counts.
            self._asked.clear()
            try:
                self._work()
            except Exception as error:
                log(f"Run failed: {error!r}")


def listener(port: int, secret: str, runner: Runner) -> HTTPServer:
    """An HTTP server on `port` that asks `runner` for a run on each POST to /<secret>, answering 204 at once
    (Pursegraph stops waiting for the reply after 5 seconds), and 404 on any other path. It ignores the body:
    whatever the delivery says is waiting, the run fetches what is."""
    expected = f"/{secret}".encode()

    class Delivery(BaseHTTPRequestHandler):
        def do_POST(self):
            self.rfile.read(int(self.headers.get("Content-Length") or 0))
            if hmac.compare_digest(self.path.encode(), expected):
                runner.ask()
                self.send_response(204)
            else:
                self.send_response(404)
            self.send_header("Content-Length", "0")
            self.end_headers()

        def log_message(self, format, *args):
            pass  # The secret is in the path.

    return HTTPServer(("", port), Delivery)


def start(environ: Mapping[str, str]) -> HTTPServer:
    """Starts the Categorizer that `environ` describes, with a run for what is already waiting, and returns its
    listener; the caller serves it."""
    missing = [
        name
        for name in ("PURSEGRAPH_URL", "CATEGORIZER_TOKEN", "OLLAMA_URL", "WEBHOOK_SECRET")
        if not environ.get(name)
    ]
    if missing:
        raise SystemExit(f"Set {', '.join(missing)}; see docs/operations.md.")
    pursegraph = Pursegraph(environ["PURSEGRAPH_URL"], environ["CATEGORIZER_TOKEN"])
    ollama = Ollama(environ["OLLAMA_URL"], environ.get("OLLAMA_MODEL") or "qwen3-vl:8b")
    runner = Runner(lambda: run(pursegraph, ollama))
    server = listener(int(environ.get("PORT") or 8765), environ["WEBHOOK_SECRET"], runner)
    log(
        f"Suggesting with {ollama.model} at {ollama.base_url} for {pursegraph.base_url};"
        f" listening on port {server.server_port}."
    )
    runner.ask()
    return server


if __name__ == "__main__":
    start(os.environ).serve_forever()
