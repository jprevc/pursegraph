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
4. Optionally, connect a Categorizer, so Transactions no Rule categorizes get a suggested Subcategory; see [Categorizers](#categorizers).

## Categorizers

Transactions that no Rule categorizes wait for a Suggestion. A Categorizer is a program, such as one that asks an LLM or any other service, that fetches them through the [Categorizer API](#the-categorizer-api) and sends back a Subcategory with how sure it is. Pursegraph itself ships no Categorizer and calls none (see [ADR 0002](adr/0002-no-bundled-categorizer-webhooks-say-when-transactions-wait.md)); [Webhooks](#webhooks) tell a Categorizer when there is something to fetch. Without a Categorizer, the Review queue fills without Suggestions.

A Suggestion at least as sure as the auto-accept threshold on the Suggestions page (0.90 by default) sets the outcome; the rest wait in the Review queue, preselected. That threshold applies to every Categorizer alike, so a Categorizer must report a confidence that means something.

**Privacy:** a Categorizer reads each waiting Transaction's description, amount and details, and the Household's earlier choices as examples. Where it sends them is up to it, possibly to a cloud service. Pursegraph can't restrict that, so choose carefully who gets a token: that is the choice of where the Household's Transaction text goes.

### Creating a token

Each Categorizer connects with a token of its own, which can only fetch the waiting Transactions and send Suggestions back; it can't log in.

1. As an admin, open **Categorizers** in the sidebar's Manage links, name the token after the Categorizer (such as "Qwen on the NAS") and create it.
2. Copy the token from the dialog. It starts with `pgc_` and is shown only once; only a hash of it is stored.
3. Give it to the Categorizer, such as in the example's `CATEGORIZER_TOKEN` ([below](#example-an-ollama-categorizer)).

A lost or leaked token can't be shown again: revoke it on the same page and create another. Calls made with a revoked token get a 401 at once. The page lists when each token was last used, and the Suggestions page shows how many Transactions are waiting, since when, and which token sent the last Suggestion.

### Webhooks

A Webhook is a URL Pursegraph calls when Transactions are waiting for a Suggestion, so a Categorizer knows to fetch them without asking all the time. Add one on the **Categorizers** page under New Webhook: a name and an `http://` or `https://` URL. Deliveries aren't signed, so put a secret in the URL, such as `http://192.168.1.10:8765/<secret>`; the page shows only the URL's scheme, host and port once it is added.

Every Webhook is called once an action that can leave Transactions waiting is done, if any are waiting then: a Statement import, a re-parse that re-runs outcomes, Ask again on the Suggestions page, or deleting a Subcategory. Each action calls each Webhook once on its own, so importing three Statements calls it three times. A delivery is one `POST` with a JSON body that says how many Transactions are waiting, never which:

```json
{"event": "transactions_waiting", "at": "2026-10-27T13:02:00+00:00", "waiting": 3}
```

Only a `2xx` reply within 5 seconds counts as delivered. A redirect isn't followed, and a failed delivery isn't retried. Each Webhook's row shows its latest attempt: "Delivered" with when, "Failed" with why (an HTTP status, "timed out" or "couldn't connect"), or "Never called". **Notify now** calls that Webhook right away, even when nothing is waiting, and shows how it went; use it to test a receiver.

The receiver can be the Categorizer itself, as in the [example](#example-an-ollama-categorizer), or something that starts one, such as a Home Assistant automation that turns on the machine the Categorizer runs on. Either way it treats a delivery as "go fetch": it fetches with its own token, whatever the count says, and a repeated delivery does no harm. Because a delivery may be lost, such as while the receiver is down, a Categorizer may also fetch now and then (e.g. hourly) on its own.

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

### Example: an Ollama Categorizer

[`docs/examples/ollama_categorizer.py`](examples/ollama_categorizer.py) is a Categorizer that asks an [Ollama](https://ollama.com) server. It is an example to copy and fit to your Household, such as its prompt and model, not part of Pursegraph; Pursegraph's tests run it against the API with Ollama faked, so it keeps working. It needs only Python 3.10 or later.

It listens for the Webhook and doesn't poll. On a `POST` to `/<WEBHOOK_SECRET>` it answers `204` at once and then, on a background thread, fetches the waiting Transactions, asks Ollama about each and sends the Suggestions, repeating until nothing is waiting. A delivery that arrives during a run starts one more run after it. It runs once when it starts too, for what was already waiting. Its confidence is Ollama's own probability of the answer, from the answer's token `logprobs`. It assumes Ollama is up: when a call to Ollama or Pursegraph fails, it logs why and stops until the next delivery.

It reads:

| Variable | |
| --- | --- |
| `PURSEGRAPH_URL` | Where it reaches Pursegraph, such as `http://192.168.1.20:8000`. That host name or IP must be in Pursegraph's `DJANGO_ALLOWED_HOSTS`. |
| `CATEGORIZER_TOKEN` | Its token, from [Creating a token](#creating-a-token). |
| `OLLAMA_URL` | The Ollama server, such as `http://localhost:11434`. |
| `WEBHOOK_SECRET` | A long random string, such as from `python3 -c 'import secrets; print(secrets.token_urlsafe())'`. |
| `PORT` | Where it listens; 8765 by default. |
| `OLLAMA_MODEL` | The model to ask; `qwen3-vl:8b` by default. |

Run it anywhere Pursegraph can reach on `PORT`, such as on the Ollama machine, with the variables set:

```sh
python3 ollama_categorizer.py
```

To keep it running there, a systemd service, such as `/etc/systemd/system/ollama-categorizer.service`, with the variables in `/etc/ollama-categorizer.env`:

```ini
[Unit]
Description=Pursegraph Ollama Categorizer
After=network-online.target ollama.service
Wants=network-online.target

[Service]
EnvironmentFile=/etc/ollama-categorizer.env
ExecStart=/usr/bin/python3 /opt/ollama-categorizer/ollama_categorizer.py
DynamicUser=yes
Restart=on-failure

[Install]
WantedBy=multi-user.target
```

```sh
sudo systemctl enable --now ollama-categorizer
journalctl -u ollama-categorizer -f
```

Or in Docker, with the variables in `ollama-categorizer.env`:

```sh
docker run -d --name ollama-categorizer --restart unless-stopped \
  --env-file ollama-categorizer.env -p 8765:8765 \
  -v "$PWD/ollama_categorizer.py:/ollama_categorizer.py:ro" \
  python:3.12-slim python /ollama_categorizer.py
```

In a container, `localhost` is the container itself, so point `OLLAMA_URL` at the host's address instead.

Then add the Webhook on the Categorizers page, at `http://<categorizer host>:8765/<WEBHOOK_SECRET>`, and press Notify now: it shows "Delivered" if Pursegraph reached the example, and the example's log shows how many waiting Transactions it answered. Pursegraph must reach that port, so open it in the Categorizer host's firewall to the Pursegraph host.


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
docker compose stop web backup
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

It prints the same differences, then applies or refuses each Statement on its own; one refused or failing Statement doesn't stop the others, and a failure while applying rolls that Statement back. Applying updates each changed Transaction's fields (amount, description, counterparty, reference, running balance, bank fee) and what the parser saw for it. Manual outcomes are kept. A Transaction whose change could alter its automatic outcome (anything but its running balance) loses that outcome and its Suggestion, unpairing its Transfer counterpart, and goes through the import's automatic steps again: bank fees, the IBAN rule and pairing, the Rules, then waiting for a Suggestion. The command lists the outcomes that changed, before → after.

A Statement is refused, and nothing on it changes, when its own fields (period, balances, bank, IBAN) changed, when rows were added or removed, when a changed Transaction is a Duplicate on it (re-parse the Statement that first had it instead), or when a Transaction another Statement also has changed its amount or running balance. A failed re-parse is skipped as failed. For a refused Statement, delete it and import its file again; that loses the manual outcomes on its Transactions.

## Recovering a locked-out admin

If an admin forgot their password, was deactivated, lost the admin flag, or is locked out after too many failed logins (5 failures lock that username from that IP for an hour):

```sh
docker compose exec web python manage.py recover_admin <username>
```

It sets a new password (prompted), reactivates the Member, makes them an admin and clears their failed-login lockout.

`create_admin` and `recover_admin` both accept `--noinput` and then read the password from the `PURSEGRAPH_PASSWORD` environment variable (`docker compose exec -e PURSEGRAPH_PASSWORD=... web ...`).
