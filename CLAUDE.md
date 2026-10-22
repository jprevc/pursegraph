## Agent skills

### Issue tracker

Issues and specs are tracked in GitHub Issues, using the `gh` CLI. Read one with `gh issue view <n> --json title,body,labels,comments --jq '{title, body, labels: [.labels[].name], comments: [.comments[].body]}'`. Everything else: `docs/agents/issue-tracker.md`.

### Triage labels

Uses the five default triage labels (`needs-triage`, `needs-info`, `ready-for-agent`, `ready-for-human`, `wontfix`). See `docs/agents/triage-labels.md`.

### Domain docs

Single-context: one root `CONTEXT.md`, plus `docs/adr/` once the first ADR is written. See `docs/agents/domain.md`.

### Prototypes

Serving, handoff and screenshots for `/prototype` tickets. See `docs/agents/prototypes.md`.

### Design docs

Before reading `DESIGN.md`, `docs/design/`, `static/pursegraph.css` or a prototype, read `docs/agents/design-docs.md`.

### Test seams

When the tdd skill calls for agreed seams, choose them yourself: the public interfaces you would recommend. Name them in the PR body, so the user agrees to them there.

### Checks

`scripts/check` runs every check (ruff, format, mypy, one-line template comments, imports without dev dependencies, pytest); `--fast` skips pytest. The pre-commit hook and CI run it.

### Branches

A worktree's local `main` lags behind; branch from, diff against and review against `origin/main` (`git fetch` first).

### Screenshots and the demo app

Running the app on demo data, checking a change in a browser, and before/after screenshots for a PR. See `docs/agents/screenshots.md`.
