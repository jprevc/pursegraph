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

The Import page takes Revolut CSV exports. Each Statement is checked (opening balance + all rows = closing balance) and rejected as a whole if it doesn't add up. The original files are kept on the `statement-files` Docker volume, so they can be re-parsed after a parser fix.

## Categories and the Review queue

Every Transaction gets an outcome: a Subcategory of the two-level Category list, or Transfer. A default list is seeded on the first migration; admins edit it on the Categories page. Bank fees are categorized Finance → Bank fees at import (while that Subcategory keeps its name). Everything else waits in the Review queue, where a Member picks the outcome; the same inline editor appears on every row of the Transactions view.

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
```

The tests run against a real PostgreSQL database, never SQLite.

HTMX and ECharts are vendored under `static/vendor/` so the app works without internet access. To upgrade one, replace its file there.

All UI text is marked for translation (`{% translate %}` in templates, `gettext` in Python). v1 ships English only.
