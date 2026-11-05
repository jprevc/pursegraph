"""The example Ollama Categorizer (docs/examples/ollama_categorizer.py), against a live Pursegraph and its real
Webhooks, with only Ollama faked."""

import importlib.util
import json
import math
import re
import subprocess
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest

from ledger import api_tokens, webhooks
from ledger.models import ApiToken, Source, Transaction, Webhook
from tests.conftest import finish_deliveries, subcategory_id
from tests.test_rules import make_transaction

EXAMPLE = Path(__file__).parent.parent / "docs" / "examples" / "ollama_categorizer.py"
_spec = importlib.util.spec_from_file_location("ollama_categorizer", EXAMPLE)
assert _spec and _spec.loader
example = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(example)

# Pursegraph serves the API from another thread, so its data must be committed.
live = pytest.mark.django_db(transaction=True, serialized_rollback=True)

SECRET = "s3cret"


class FakeOllama:
    """An HTTP server answering Ollama's /api/chat with a scripted Subcategory and probability per Transaction
    description, spelled out in `logprobs` as Ollama does; `status` other than 200 makes it fail."""

    def __init__(self, answers):
        self.answers = answers
        self.status = 200
        fake = self

        class Handler(BaseHTTPRequestHandler):
            def do_POST(self):
                body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
                if self.path != "/api/chat" or fake.status != 200:
                    self.send_response(fake.status if fake.status != 200 else 404)
                    self.send_header("Content-Length", "0")
                    self.end_headers()
                    return
                description = re.search(
                    r"^Description: (.*)$", body["messages"][-1]["content"], re.M
                )
                assert description
                label, probability = fake.answers[description[1]]
                assert label in body["format"]["properties"]["subcategory"]["enum"]
                content = json.dumps({"subcategory": label}, ensure_ascii=False)
                logprobs = [
                    {"token": '{"subcategory": "', "logprob": 0.0},
                    {"token": label, "logprob": math.log(probability)},
                    {"token": '"}', "logprob": 0.0},
                ]
                reply = json.dumps({"message": {"content": content}, "logprobs": logprobs}).encode()
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(reply)))
                self.end_headers()
                self.wfile.write(reply)

            def log_message(self, *args):
                pass

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.server.daemon_threads = True
        threading.Thread(target=self.server.serve_forever, daemon=True).start()
        self.url = f"http://127.0.0.1:{self.server.server_port}"


ANSWERS = {
    "Corner Shop": ("Food > Groceries", 0.95),
    "Hiša kave": ("Food > Restaurants & cafés", 0.5),
    "Petrol": ("Transport > Fuel", 0.99),
}


@pytest.fixture
def ollama():
    fake = FakeOllama(ANSWERS)
    yield fake
    fake.server.shutdown()
    fake.server.server_close()


@pytest.fixture
def start(live_server, django_user_model, ollama):
    """Starts the example as its script does, with a token of its own, and waits for its first fetch; returns the
    URL its Webhook is at."""
    servers = []

    def start():
        admin = django_user_model.objects.create_user(username="bor", is_admin=True)
        record, token = api_tokens.create("Qwen on the NAS", admin)
        server = example.start(
            {
                "PURSEGRAPH_URL": live_server.url,
                "CATEGORIZER_TOKEN": token,
                "OLLAMA_URL": ollama.url,
                "WEBHOOK_SECRET": SECRET,
                "PORT": "0",
            }
        )
        servers.append(server)
        threading.Thread(target=server.serve_forever, daemon=True).start()
        eventually(lambda: ApiToken.objects.get(pk=record.pk).last_used_at)
        return f"http://127.0.0.1:{server.server_port}"

    yield start
    for server in servers:
        server.shutdown()
        server.server_close()


def eventually(condition, timeout=10):
    deadline = time.monotonic() + timeout
    while not condition():
        assert time.monotonic() < deadline, "timed out"
        time.sleep(0.05)


def suggested(description):
    """The Subcategory a Suggestion set or preselected for the Transaction, with its confidence and source."""
    transaction = Transaction.objects.get(description=description)
    return (
        transaction.subcategory_id or transaction.suggested_subcategory_id,
        transaction.confidence,
        transaction.source,
    )


def has_suggestion(description):
    return Transaction.objects.get(description=description).confidence is not None


@live
def test_on_start_it_suggests_for_the_transactions_already_waiting(start):
    make_transaction("Corner Shop")
    make_transaction("Hiša kave")

    start()

    eventually(lambda: has_suggestion("Corner Shop") and has_suggestion("Hiša kave"))
    assert suggested("Corner Shop") == (
        subcategory_id("Food", "Groceries"),
        pytest.approx(0.95),
        Source.CATEGORIZER,
    )
    assert suggested("Hiša kave") == (
        subcategory_id("Food", "Restaurants & cafés"),
        pytest.approx(0.5),
        "",
    )


def webhook_at(url):
    return Webhook.objects.create(name="Qwen on the NAS", url=url)


def last_outcome(webhook):
    webhook.refresh_from_db()
    return webhook.last_outcome, webhook.last_status


@live
def test_a_webhook_makes_it_suggest_for_what_is_waiting_now(start):
    webhook = webhook_at(f"{start()}/{SECRET}")
    make_transaction("Corner Shop")

    webhooks.fire_if_waiting()

    finish_deliveries()
    assert last_outcome(webhook) == ("delivered", None)
    eventually(lambda: has_suggestion("Corner Shop"))
    assert suggested("Corner Shop")[0] == subcategory_id("Food", "Groceries")


@live
def test_a_webhook_at_another_path_is_not_found_and_starts_nothing(start):
    url = start()
    make_transaction("Corner Shop")
    wrong = webhook_at(f"{url}/not-the-secret")
    bare = webhook_at(f"{url}/")

    webhooks.fire_if_waiting()

    finish_deliveries()
    assert last_outcome(wrong) == ("http_error", 404)
    assert last_outcome(bare) == ("http_error", 404)
    time.sleep(0.5)
    assert not has_suggestion("Corner Shop")


@live
def test_a_failed_call_ends_the_run_and_the_next_webhook_tries_again(start, ollama, capsys):
    url = start()
    ollama.status = 500
    make_transaction("Corner Shop")
    webhook = webhook_at(f"{url}/{SECRET}")

    webhooks.deliver(webhook, 1)
    eventually(lambda: "Stopped after answering 0 Transactions" in capsys.readouterr().err)
    assert not has_suggestion("Corner Shop")

    ollama.status = 200
    webhooks.deliver(webhook, 1)
    eventually(lambda: has_suggestion("Corner Shop"))


def test_runs_never_overlap_and_one_asked_for_meanwhile_follows():
    started, release = threading.Semaphore(0), threading.Event()
    running: list[bool] = []
    overlapped: list[bool] = []
    runs: list[bool] = []

    def work():
        if running:
            overlapped.append(True)
        running.append(True)
        runs.append(True)
        started.release()
        release.wait()
        running.pop()

    runner = example.Runner(work)
    runner.ask()
    assert started.acquire(timeout=5)
    runner.ask()
    runner.ask()
    release.set()

    assert started.acquire(timeout=5)
    time.sleep(0.3)
    assert (len(runs), overlapped) == (2, [])


def tokens(*pieces):
    return [{"token": text, "logprob": logprob} for text, logprob in pieces]


def test_confidence_is_the_product_of_the_answers_token_probabilities():
    logprobs = tokens(
        ('{"', -0.5),
        ('subcategory":"', -0.2),
        ("Food", math.log(0.9)),
        (" > ", math.log(0.8)),
        ("Groceries", math.log(0.5)),
        ('"}', -1.0),
    )

    assert example.answer_confidence(logprobs, "Food > Groceries") == pytest.approx(0.36)


def test_confidence_counts_a_token_straddling_the_answer():
    logprobs = tokens(('{"subcategory":"Food', math.log(0.5)), (' > Other"}', math.log(0.5)))

    assert example.answer_confidence(logprobs, "Food > Other") == pytest.approx(0.25)


def test_an_answer_not_found_in_the_tokens_has_no_confidence():
    assert example.answer_confidence(tokens(("{}", 0.0)), "Food > Groceries") == 0.0


def modules_imported(code, *args):
    """The modules loaded after running `code` in a Python of its own."""
    run = [sys.executable, "-I", "-c", f"import sys; {code}; print(*sys.modules)", *args]
    return set(subprocess.run(run, capture_output=True, text=True, check=True).stdout.split())


def test_it_uses_only_the_standard_library():
    imported = modules_imported("import runpy; runpy.run_path(sys.argv[1])", EXAMPLE)

    added = imported - modules_imported("pass")
    assert {m for m in added if m.split(".")[0] not in sys.stdlib_module_names} == set()
