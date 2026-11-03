# Operations

Installing Pursegraph and keeping it running: Categorizers, backups, restores, re-parsing and admin recovery. Run the commands from the directory with `docker-compose.yml`.

## Installing

1. Copy `.env.example` to `.env` and fill in `DJANGO_SECRET_KEY`, `DJANGO_ALLOWED_HOSTS` and `POSTGRES_PASSWORD`. Create the data directory as the host user who will own it (`PURSEGRAPH_USER`, `1000:1000` by default):

   ```sh
   mkdir -p data/statement-files data/backups
   ```

   The original Statement files and the nightly database dumps go there (`PURSEGRAPH_DATA`, `./data` by default); the dumps are readable by that user only.
2. Start it:

   ```sh
   docker compose up -d --build
   ```

   The `web` container applies database migrations every time it starts.
3. Create the first admin. There is no first-run web page, so nobody who reaches the port first can take over the installation:

   ```sh
   docker compose exec web python manage.py create_admin <username>
   ```

   It prompts for the password. Then open `http://<host>:8000/` (or the `PURSEGRAPH_PORT` you set) and log in.
4. For suggested Subcategories, create a token for a Categorizer, such as the bundled Ollama one; see [Categorizers](#categorizers).

## Categorizers

Transactions that no Rule categorizes wait for a Suggestion. A Categorizer is a program that fetches them through the [Categorizer API](#the-categorizer-api) and sends back a Subcategory with how sure it is. Pursegraph itself calls no LLM (see [ADR 0001](adr/0001-categorizers-pull-suggestions-through-an-api.md)). A Suggestion at least as sure as the auto-accept threshold on the LLM suggestions page sets the outcome; the rest wait in the Review queue, preselected. That threshold applies to every Categorizer alike, so a Categorizer must report a confidence that means something. Without a Categorizer the Review queue fills without Suggestions.

Transaction text leaves the LAN only if a Categorizer sends it elsewhere. The bundled Ollama Categorizer sends it only to your Ollama server, but one that asks a cloud service sends it there. That choice is made when an admin creates a token for it.

### Creating a token

Each Categorizer connects with a token of its own, which can only fetch the waiting Transactions and send Suggestions back; it can't log in.

1. As an admin, open **Categorizers** in the sidebar's Manage links, name the token after the Categorizer (such as "Ollama on the NAS") and create it.
2. Copy the token from the dialog. It starts with `pgc_` and is shown only once; only a hash of it is stored.
3. Give it to the Categorizer. For the bundled one, put it in `.env` as `CATEGORIZER_TOKEN` (below).

A lost or leaked token can't be shown again: revoke it on the same page and create another. Calls made with a revoked token get a 401 at once. The page lists when each token was last used, and the LLM suggestions page shows how many Transactions are waiting, since when, and which token sent the last Suggestion.

### The bundled Ollama Categorizer

Pursegraph ships an Ollama Categorizer, which uses only the Categorizer API. It needs:

- `PURSEGRAPH_URL`: where it reaches Pursegraph;
- `CATEGORIZER_TOKEN`: its token from the Categorizers page;
- `OLLAMA_URL`: the Ollama server, such as `http://192.168.1.10:11434`.

It checks for waiting Transactions every 10 seconds. While Ollama doesn't answer it waits longer between tries, up to 5 minutes, and until `CATEGORIZER_TOKEN` is set it logs that and waits. It doesn't wake a sleeping machine; for that, see [Waking a sleeping LLM machine](#waking-a-sleeping-llm-machine).

**In Compose,** the `categorize_worker` service runs it next to Pursegraph, and Compose points `PURSEGRAPH_URL` at the `web` service. Set `OLLAMA_URL` in `.env`, create a token, add it to `.env` and restart the service:

```sh
echo 'CATEGORIZER_TOKEN=pgc_...' >> .env
docker compose up -d categorize_worker
docker compose logs -f categorize_worker
```

**On another machine,** such as the Ollama machine itself, run only that service from a checkout of Pursegraph there. Its `.env` holds just the three variables, with `PURSEGRAPH_URL` pointing at the Pursegraph host. That host's name or IP must be in Pursegraph's `DJANGO_ALLOWED_HOSTS`. Then stop the `categorize_worker` service on the Pursegraph machine, or leave `CATEGORIZER_TOKEN` unset there.

```sh
docker compose up -d --build --no-deps categorize_worker
```

### The Categorizer API

Every call sends the token as `Authorization: Bearer pgc_...`. The API takes no session or CSRF token, and it answers in JSON.

#### Fetching the waiting Transactions

```http
GET /api/categorizer/v1/transactions/?limit=50
```

`limit` is optional: from 1 to 200, 50 by default. The answer is the Subcategories to choose from, and up to `limit` Transactions waiting for a Suggestion, oldest first:

```json
{
  "subcategories": [
    {"id": 1, "label": "Food > Groceries"},
    {"id": 2, "label": "Food > Restaurants & cafés"}
  ],
  "transactions": [
    {
      "id": 812,
      "direction": "out",
      "amount": "23.40",
      "description": "Kavarna Zvezda",
      "detail": "Card payment",
      "examples": [
        {"direction": "out", "description": "Mercator", "detail": "", "subcategory": 1}
      ]
    }
  ]
}
```

- `direction` is `"in"` or `"out"`, and `amount` is the amount in EUR without its sign, as a string with two decimals.
- `detail` is other text the parser found on the Transaction, such as the counterparty or a purpose line, joined with `; `; it may be empty.
- `examples` are the Household's latest manual outcome for each other merchant, most recent first and at most 100, as few-shot examples for a prompt. Their `subcategory` is an `id` from `subcategories`.

Fetching claims nothing: the same Transactions come back until Suggestions for them arrive, or until a Member categorizes them. Two Categorizers may therefore get the same Transaction; the first Suggestion stored wins.

#### Sending a Suggestion

```http
POST /api/categorizer/v1/transactions/812/suggestion/
Content-Type: application/json

{"subcategory": 2, "confidence": 0.93}
```

`subcategory` is an `id` from the last fetch, and `confidence` is a number from 0 to 1: how sure the Categorizer is. To say it has no Suggestion, so the Transaction waits in the Review queue without one and isn't fetched again, send `{"subcategory": null}`. The answer:

```json
{"stored": true, "accepted": true}
```

- `stored` is false when the Suggestion was ignored: the Transaction already has an outcome or a Suggestion (the first one wins), or the Subcategory was deleted meanwhile. That last one is fetched again.
- `accepted` is true when the Suggestion cleared the auto-accept threshold and set the Transaction's outcome.

#### Errors

| Status | When |
| --- | --- |
| 400 | A malformed request: a `limit` that isn't a whole number from 1 to 200, a body that isn't a JSON object with `"subcategory"`, a `subcategory` that isn't an id or `null`, or a missing or out-of-range `confidence`. Also an unknown Subcategory; fetch again for the current ones. |
| 401 | A missing, wrong or revoked token. The answer has `WWW-Authenticate: Bearer`. |
| 404 | No Transaction with that id. |
| 405 | The wrong method, with an empty body and an `Allow` header. |

The token is checked first, so a request without a valid one gets a 401 whatever else is wrong with it, even the method.

All but the 405 answer `{"error": "<why>"}`, such as `{"error": "limit must be a whole number from 1 to 200."}`.

### Waking a sleeping LLM machine

If Ollama runs on a machine that sleeps until it is woken with Wake-on-LAN, the Categorizer should poll from an always-on machine instead, such as the Pursegraph host or a NAS. When Transactions are waiting and Ollama doesn't answer, it wakes the machine. The sample below does that. It is documentation, not part of Pursegraph: copy it, then fit it to your machine. It needs only Python 3 and the same three variables as the bundled Categorizer, plus `OLLAMA_MAC`, the MAC address of the Ollama machine's network card. Wake-on-LAN must be enabled in that machine's firmware and network settings. If the always-on machine is on another subnet, set `BROADCAST` to that subnet's broadcast address, such as `192.168.1.255`.

Its prompt is minimal and it reports a fixed confidence of 0.5, so its Suggestions stay below the default auto-accept threshold of 0.90; an admin can lower the threshold to 0.50, and then they would clear it. Before letting it auto-accept, give it a real confidence, as the bundled Categorizer does with Ollama's `logprobs`.

```python
"""A Categorizer that wakes the sleeping Ollama machine with Wake-on-LAN when Transactions are waiting."""

import json
import os
import socket
import time
import urllib.request

PURSEGRAPH_URL = os.environ["PURSEGRAPH_URL"].rstrip("/")
TOKEN = os.environ["CATEGORIZER_TOKEN"]
OLLAMA_URL = os.environ["OLLAMA_URL"].rstrip("/")
OLLAMA_MAC = os.environ["OLLAMA_MAC"]  # the Ollama machine's network card, e.g. 3c:7c:3f:12:34:56
BROADCAST = os.environ.get("BROADCAST", "255.255.255.255")
MODEL = os.environ.get("MODEL", "qwen3-vl:8b")
POLL, WAKE_TIMEOUT = 60, 180  # seconds


def call(url, body=None, headers=None, timeout=10):
    data = None if body is None else json.dumps(body).encode()
    headers = {"Content-Type": "application/json", **(headers or {})}
    with urllib.request.urlopen(urllib.request.Request(url, data, headers), timeout=timeout) as r:
        return json.load(r)


def pursegraph(path, body=None):
    return call(PURSEGRAPH_URL + path, body, {"Authorization": f"Bearer {TOKEN}"})


def ollama_up():
    try:
        call(OLLAMA_URL + "/api/version", timeout=3)
        return True
    except OSError:
        return False


def wake():
    """Sends the magic packet (6 × 0xFF, then the MAC 16 times) and waits for Ollama to answer."""
    packet = b"\xff" * 6 + bytes.fromhex(OLLAMA_MAC.replace(":", "").replace("-", "")) * 16
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
        s.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        s.sendto(packet, (BROADCAST, 9))
    deadline = time.monotonic() + WAKE_TIMEOUT
    while time.monotonic() < deadline:
        if ollama_up():
            return True
        time.sleep(5)
    return False


def suggest(transaction, labels):
    """Asks Ollama for one of the labels. A fixed 0.5 is below the auto-accept threshold, so every
    Suggestion waits in the Review queue. Report a real confidence before letting it auto-accept,
    such as the bundled Categorizer's, from Ollama's logprobs."""
    t = transaction
    text = f"{t['direction']} {t['amount']} EUR: {t['description']} {t['detail']}"
    answer = call(
        OLLAMA_URL + "/api/chat",
        {
            "model": MODEL,
            "stream": False,
            "messages": [
                {
                    "role": "user",
                    "content": f"Pick the Subcategory of this bank Transaction: {text}",
                }
            ],
            "format": {
                "type": "object",
                "properties": {"subcategory": {"type": "string", "enum": list(labels)}},
                "required": ["subcategory"],
            },
        },
        timeout=120,
    )
    label = json.loads(answer["message"]["content"])["subcategory"]
    return {"subcategory": labels[label], "confidence": 0.5}


while True:
    try:
        work = pursegraph("/api/categorizer/v1/transactions/?limit=20")
        if not work["transactions"]:
            time.sleep(POLL)
            continue
        if not ollama_up() and not wake():
            print("Ollama didn't wake up; trying again later", flush=True)
            time.sleep(POLL)
            continue
        labels = {s["label"]: s["id"] for s in work["subcategories"]}
        for transaction in work["transactions"]:
            try:
                body = suggest(transaction, labels)
            except (KeyError, ValueError):  # an unusable answer: no Suggestion
                body = {"subcategory": None}
            pursegraph(f"/api/categorizer/v1/transactions/{transaction['id']}/suggestion/", body)
    except (OSError, ValueError) as error:  # unreachable, an HTTP error, or not JSON
        print(error, flush=True)
        time.sleep(POLL)
```

Run it with `python3 wake_categorizer.py` and the variables set, for example as a systemd service. In a container, the magic packet is a UDP broadcast, and Docker's default bridge network doesn't pass it onto the LAN. Give the container the host's network (`network_mode: host` in Compose, `--network host` with `docker run`).

## Backups

The `backup` service dumps the database with `pg_dump` every night at `BACKUP_HOUR` (3:00 by default, in `BACKUP_TZ`) into `data/backups/`. It keeps the newest 14 daily dumps (`daily/pursegraph-YYYY-MM-DD.dump`) and 6 monthly ones (`monthly/pursegraph-YYYY-MM.dump`, the month's first). Check it works with `docker compose logs backup`, or take a dump right away:

```sh
docker compose exec backup /backup.sh once
```

The dumps hold the database only; the Statement files are next to them, in `data/statement-files/`. Copying `data/` off the machine is up to you, for example to a NAS.

### Restoring a dump

This replaces the whole database with the dump. It works the same on a fresh installation, such as after a disk failure, as on a running one. Run it from the directory with `docker-compose.yml`:

```sh
docker compose up -d postgres
docker compose stop web categorize_worker backup
docker compose exec postgres sh -c 'dropdb -U "$POSTGRES_USER" --force "$POSTGRES_DB" && createdb -U "$POSTGRES_USER" "$POSTGRES_DB"'
docker compose exec -T postgres sh -c 'pg_restore -U "$POSTGRES_USER" -d "$POSTGRES_DB" --no-owner --exit-on-error' < data/backups/daily/pursegraph-YYYY-MM-DD.dump
docker compose up -d
docker compose exec web python manage.py reparse
```

If you set `PURSEGRAPH_DATA`, take the dump from that directory instead of `data/`.

The `web` service applies any migrations newer than the dump when it starts. The last command checks that every restored Statement's file is still there. Statements deleted after the dump was taken have lost their files, and those Statements show as failed. Statements imported after the dump are gone from the database, but their files stay on the volume, so import them again.

This procedure was tested end to end: a database volume deleted and re-created empty, then restored from a dump with its Members, Accounts, Statements and Transactions intact.

## Re-parsing Statements

After a parser fix, check what it would change in the Statements already imported:

```sh
docker compose exec web python manage.py reparse [<statement id> ...]
```

It parses each stored Statement file again, all of them by default, and prints the differences against what is stored. Those are the Statement's period and balances, plus each Transaction: `~` changed (field by field, stored → re-parsed), `+` a row the parser now finds, `-` a stored Transaction it no longer finds. A Duplicate keeps the fields of the Statement that first had it, so on a later Statement only its amount and running balance are compared. If that first Statement was since deleted, the Duplicate's other fields may show as differences although nothing changed. A file that no longer parses, or whose re-parsed rows don't add up, is listed as failed. By itself the command only shows the differences and changes nothing. To take a fix on, add `--apply`:

```sh
docker compose exec web python manage.py reparse --apply [<statement id> ...]
```

It prints the same differences, then applies or refuses each Statement on its own; one refused or failing Statement doesn't stop the others, and a failure while applying rolls that Statement back. Applying updates each changed Transaction's fields (amount, description, counterparty, reference, running balance, bank fee) and what the parser saw for it. Manual outcomes are kept. A Transaction whose change could alter its automatic outcome (anything but its running balance) loses that outcome and its LLM suggestion, unpairing its Transfer counterpart, and goes through the import's automatic steps again: bank fees, the IBAN rule and pairing, the Rules, then the LLM. The command lists the outcomes that changed, before → after.

A Statement is refused, and nothing on it changes, when its own fields (period, balances, bank, IBAN) changed, when rows were added or removed, when a changed Transaction is a Duplicate on it (re-parse the Statement that first had it instead), or when a Transaction another Statement also has changed its amount or running balance. A failed re-parse is skipped as failed. For a refused Statement, delete it and import its file again; that loses the manual outcomes on its Transactions.

## Recovering a locked-out admin

If an admin forgot their password, was deactivated, lost the admin flag, or is locked out after too many failed logins (5 failures lock that username from that IP for an hour):

```sh
docker compose exec web python manage.py recover_admin <username>
```

It sets a new password (prompted), reactivates the Member, makes them an admin and clears their failed-login lockout.

`create_admin` and `recover_admin` both accept `--noinput` and then read the password from the `PURSEGRAPH_PASSWORD` environment variable (`docker compose exec -e PURSEGRAPH_PASSWORD=... web ...`).
