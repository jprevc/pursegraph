# Pursegraph

A self-hosted family finance overview. Household Members import their bank Statements, every Transaction is categorized, and the whole Household's money flow is shown together. The vocabulary is defined in [`CONTEXT.md`](CONTEXT.md).

Pursegraph is meant to be reached only on the LAN or over a VPN. Never expose it to the internet.

## Running it

1. Copy `.env.example` to `.env` and fill in `DJANGO_SECRET_KEY`, `DJANGO_ALLOWED_HOSTS` and `POSTGRES_PASSWORD`.
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

## Members

Admins manage the Household's Members on the Members page. There is no email server, so creating a Member gives you a one-time invite link to hand over yourself; through it they choose their own password. A password-reset link works the same way. Both links work once and expire after 7 days. Members are never deleted, only deactivated: they can no longer log in but stay on their Statements and Accounts. The last active admin can't be deactivated or lose the admin flag.

## Importing Statements

The Import page takes Sparkasse SI and N26 PDF Statements and Revolut PDF Statements or CSV exports, several files at once; each file is accepted or rejected on its own, in period order. A PDF's Account is found from the IBAN printed on it; for an IBAN no Account has yet (and for a CSV, which has none) the page asks which Account it goes into, or creates one owned by the importing Member. Each Statement is checked (opening balance + all rows = closing balance, and a PDF's rows against its printed money in/out totals and, where printed, row counts) and rejected as a whole if it doesn't add up. The original files are kept on the `statement-files` Docker volume, so they can be re-parsed after a parser fix.

Statements may overlap the Account's Coverage (the dates already imported). The overlapping rows must match the Transactions already imported for those days (date, amount, and running balance where printed); they are then skipped as Duplicates. If they don't match, or the new Statement's opening balance doesn't continue the Account's running balance, the file is rejected. On the first and last day of the existing Coverage, a Statement may add rows the earlier one didn't have, such as a CSV exported in the middle of a day. The Import page shows each Account's Coverage, with its gaps.

## Categories and the Review queue

Every Transaction gets an outcome: a Subcategory of the two-level Category list, or Transfer. A default list is seeded on the first migration; admins edit it on the Categories page. Bank fees that a parser splits off their payment are categorized Finance → Bank fees at import, even after that Subcategory is renamed. Everything else waits in the Review queue, where a Member picks the outcome; the same inline editor appears on every row of the Transactions view.

Transactions no Rule categorizes get a Subcategory suggested by the local LLM in the background. A suggestion at least as confident as the auto-accept threshold (0.90 by default) categorizes its Transaction; the rest wait in the Review queue with the suggestion preselected. Admins change the threshold on the LLM suggestions page. Lowering it offers to accept the queued suggestions that now clear it; raising it leaves outcomes the LLM already set alone. After a model or prompt change, "Re-suggest the Review queue" clears the queued Transactions' suggestions so the LLM is asked again. Deleting a Subcategory clears the suggestions pointing at it.

## Rules

Rules categorize Transactions at import. Any Member manages them on the Rules page. A Rule has conditions (description contains, ignoring case and accents; counterparty IBAN; direction in or out; Account), every one it sets must hold, and an outcome: a Subcategory or Transfer. At import, each Transaction still awaiting review gets the outcome of the first Rule it matches, in the order the Rules page lists them (drag to reorder). After correcting a Transaction by hand, "Make a Rule" opens a new Rule pre-filled from it; a new Rule goes to the top. Saving a Rule offers to apply it to existing Transactions, changing only those awaiting review or categorized by the LLM or a Rule. Deleting a Subcategory moves its Rules to the catch-all.

## Recovering a locked-out admin

If an admin forgot their password, was deactivated, lost the admin flag, or is locked out after too many failed logins (5 failures lock that username from that IP for an hour):

```sh
docker compose exec web python manage.py recover_admin <username>
```

It sets a new password (prompted), reactivates the Member, makes them an admin and clears their failed-login lockout.

Both commands accept `--noinput` and then read the password from the `PURSEGRAPH_PASSWORD` environment variable (`docker compose exec -e PURSEGRAPH_PASSWORD=... web ...`).

## Development

Dependencies are managed with [uv](https://docs.astral.sh/uv/).

```sh
uv sync
docker compose -f compose.test.yaml up -d   # throwaway PostgreSQL on 127.0.0.1:5433
uv run pytest
uv run ruff check && uv run ruff format --check   # lint + formatting
uv run mypy .                                     # type check (django-stubs knows models' reverse relations)
```

The tests run against a real PostgreSQL database, never SQLite. Parser tests use anonymized extracted-text fixtures in `tests/fixtures/`; `PURSEGRAPH_SAMPLES=1 uv run pytest tests/test_samples.py` also runs the parsers against the real Statements in the gitignored `samples/` directory.

HTMX and ECharts are vendored under `static/vendor/` so the app works without internet access. To upgrade one, replace its file there.

All UI text is marked for translation (`{% translate %}` in templates, `gettext` in Python). v1 ships English only.
