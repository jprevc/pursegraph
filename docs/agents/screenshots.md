# Screenshots and the demo app

Everything here runs on a synthetic demo Household from `manage.py seed_demo`, never real Statements. It needs the test PostgreSQL: `docker compose -f compose.test.yaml up -d`.

- **Members:** Ana (admin) and Luka, password `demo-pass-123`.
- **Accounts:** Ana's Sparkasse, Luka's N26, the Joint Revolut, and Ana's savings (Bank "Other", no Statements). Each has a fictional IBAN.
- **Coverage:** Statement records stand in for files. The Joint Revolut is tracked from two months later than the others; Luka's N26 has a one-month Gap and nothing for the running month.
- **Transactions:** the last twelve months and the running month up to today, only where the Account has a Statement. Fictional Slovenian merchants, salaries on the 15th, rent, electricity, internet and subscriptions each month, and three Refunds.
- **Transfers:** a monthly one-sided Transfer into the savings Account, a monthly paired Transfer from each salary Account into the Joint Revolut, and one recent ambiguous pairing.
- **Rules and the Review queue:** Rules match merchants ("Petrol", "Mercator", …). Recurring merchants await review, most with an LLM suggestion.

Its dates are counted back from today, with a fixed random seed: the same day gives the same data. `scripts/readme-shots` retakes the README's screenshots on it.

## Run the app

`scripts/demo-server <port>` with `run_in_background`, on port 8000 + the issue number. Each start makes a fresh demo database; it reloads on code changes; TaskStop stops it and drops the database.

To check behaviour (a swap, a popover, focus) or shoot a state no page shows on load (an open panel, a saved line), write a script in the scratchpad and run it with `scripts/playwright <script.js>`. `require('browser')` gives `launch()`, `open(browser, base, { scheme, size, user })` (a logged-in page) and `shoot(page, dir, name)`, which also reports sideways scroll; see `scripts/browser.js`. Shoot states into the same `after/` folder as `scripts/compare`, so `publish-shots` can publish them too.

## Before/after for a PR

1. Once the review fixes are committed, `scripts/compare <n> <scratchpad>/shots [page...]`. It runs this worktree and `origin/main` side by side and shoots each page (names: `PAGES` in `scripts/shots.js`; default all) in light and dark at desktop and phone size, into `before/` and `after/`. A page it reports as scrolling sideways in `after/` only is a bug to fix; in both, it predates the change, so say so in the PR.
2. Read only the shots you are comparing: every image Read costs context. Several at once fit in one image made with `uv run --no-project --with pillow`.
3. When the user asks for the PR, `scripts/publish-shots <n> <scratchpad>/shots [shot...]` pushes branch `shots/<n>` and prints a Before/After Markdown table, one row per shot (e.g. `spending-dark-phone`); put the rows that show the change in the PR's Evidence.

Re-running either script replaces the shots, so redo both after a late fix rather than noting that the shots are stale.
