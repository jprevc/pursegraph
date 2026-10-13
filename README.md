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

## Importing Statements

The Import page takes Sparkasse SI PDF Statements and Revolut CSV exports, several files at once; each file is accepted or rejected on its own, in period order. A PDF's Account is found from the IBAN printed on it; for an IBAN no Account has yet (and for a CSV, which has none) the page asks which Account it goes into, or creates one owned by the importing Member. Each Statement is checked (opening balance + all rows = closing balance, and a PDF's rows against its printed money in/out totals and row counts) and rejected as a whole if it doesn't add up. The original files are kept on the `statement-files` Docker volume, so they can be re-parsed after a parser fix.

Statements may overlap the Account's Coverage (the dates already imported). The overlapping rows must match the Transactions already imported for those days (date, amount, and running balance where printed); they are then skipped as Duplicates. If they don't match, or the new Statement's opening balance doesn't continue the Account's running balance, the file is rejected. On the first and last day of the existing Coverage, a Statement may add rows the earlier one didn't have, such as a CSV exported in the middle of a day. The Import page shows each Account's Coverage, with its gaps.

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
```

The tests run against a real PostgreSQL database, never SQLite. Parser tests use anonymized extracted-text fixtures in `tests/fixtures/`; `PURSEGRAPH_SAMPLES=1 uv run pytest tests/test_samples.py` also runs the parsers against the real Statements in the gitignored `samples/` directory.

HTMX and ECharts are vendored under `static/vendor/` so the app works without internet access. To upgrade one, replace its file there.

All UI text is marked for translation (`{% translate %}` in templates, `gettext` in Python). v1 ships English only.
