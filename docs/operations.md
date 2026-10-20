# Operations

Installing Pursegraph and keeping it running: backups, restores, re-parsing and admin recovery. Run the commands from the directory with `docker-compose.yml`.

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
