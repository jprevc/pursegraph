# Pursegraph

A self-hosted family finance overview. Household Members import their bank Statements, every Transaction is categorized, and the whole Household's money flow is shown together. The vocabulary is defined in [`CONTEXT.md`](CONTEXT.md).

Pursegraph is meant to be reached only on the LAN or over a VPN. Never expose it to the internet.

## Running it

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

## Members

Admins manage the Household's Members on the Members page. There is no email server, so creating a Member gives you a one-time invite link to hand over yourself; through it they choose their own password. A password-reset link works the same way. Both links work once and expire after 7 days. Members are never deleted, only deactivated: they can no longer log in but stay on their Statements and Accounts. The last active admin can't be deactivated or lose the admin flag.

## Importing Statements

The Import page takes Sparkasse SI and N26 PDF Statements and Revolut PDF Statements or CSV exports, several files at once; each file is accepted or rejected on its own, in period order. A PDF's Account is found from the IBAN printed on it; for an IBAN no Account has yet (and for a CSV, which has none) the page asks which Account it goes into, or creates one owned by the importing Member. Each Statement is checked (opening balance + all rows = closing balance, and a PDF's rows against its printed money in/out totals and, where printed, row counts) and rejected as a whole if it doesn't add up. The original files are kept in `data/statement-files/`, so they can be re-parsed after a parser fix (see "Re-parsing Statements").

Statements may overlap the Account's Coverage (the dates already imported). The overlapping rows must match the Transactions already imported for those days (date, amount, and running balance where printed); they are then skipped as Duplicates. If they don't match, or the new Statement's opening balance doesn't continue the Account's running balance, the file is rejected. On the first and last day of the existing Coverage, a Statement may add rows the earlier one didn't have, such as a CSV exported in the middle of a day. The Import page shows each Account's Coverage, with its gaps.

## Accounts

Admins manage the Accounts on the Accounts page, linked from the Import page: their name, bank, owning Members (several make a joint Account) and IBANs (several when the bank re-issued one; each belongs to one Account only). An Account with bank "Other" never receives Statements: it is registered only by its IBANs, so that money moved to it, such as to savings at another bank, is recognised as a Transfer. Adding an IBAN also makes the Transactions already imported that are awaiting review and pay to or from it Transfers. An Account keeps its bank, and can't be deleted, while it has Statements; deleting one also deletes the Rules only for it, after a confirmation that says how many. Deactivated Members are offered as owners only of the Accounts they already own.

## Categories and the Review queue

Every Transaction gets an outcome: a Subcategory of the two-level Category list, or Transfer. A default list is seeded on the first migration; admins edit it on the Categories page. Bank fees that a parser splits off their payment are categorized Finance → Bank fees at import, even after that Subcategory is renamed. Everything else waits in the Review queue, where a Member picks the outcome; the same inline editor appears on every row of the Transactions view.

Transactions no Rule categorizes get a Subcategory suggested by the local LLM in the background. A suggestion at least as confident as the auto-accept threshold (0.90 by default) categorizes its Transaction; the rest wait in the Review queue with the suggestion preselected. Admins change the threshold on the LLM suggestions page. Lowering it offers to accept the queued suggestions that now clear it (as if the LLM had accepted them); raising it leaves outcomes the LLM already set alone. After a model or prompt change, "Re-suggest the Review queue" clears the queued Transactions' suggestions so the LLM is asked again. Deleting a Subcategory clears the suggestions pointing at it, so the LLM is asked again; Transactions it already categorized there move to the catch-all like any others.

## Rules

Rules categorize Transactions at import. Any Member manages them on the Rules page. A Rule has conditions (description contains, ignoring case and accents; counterparty IBAN; direction in or out; Account), every one it sets must hold, and an outcome: a Subcategory or Transfer. At import, each Transaction still awaiting review gets the outcome of the first Rule it matches, in the order the Rules page lists them (drag to reorder). After correcting a Transaction by hand, "Make a Rule" opens a new Rule pre-filled from it; a new Rule goes to the top. Saving a Rule offers to apply it to existing Transactions, changing only those awaiting review or categorized by the LLM or a Rule. Deleting a Subcategory moves its Rules to the catch-all.

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
