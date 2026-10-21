## Agent skills

### Issue tracker

Issues and specs are tracked in GitHub Issues, using the `gh` CLI. See `docs/agents/issue-tracker.md`.

### Triage labels

Uses the five default triage labels (`needs-triage`, `needs-info`, `ready-for-agent`, `ready-for-human`, `wontfix`). See `docs/agents/triage-labels.md`.

### Domain docs

Single-context: one root `CONTEXT.md`, plus `docs/adr/` once the first ADR is written. See `docs/agents/domain.md`.

### Prototypes

Serving, handoff and screenshots for `/prototype` tickets. See `docs/agents/prototypes.md`.

### Design docs

Before reading `DESIGN.md`, `docs/design/`, `static/pursegraph.css` or a prototype, read `docs/agents/design-docs.md`.

### Checks

`scripts/check` runs every check (ruff, format, mypy, imports without dev dependencies, pytest); `--fast` skips pytest. The pre-commit hook and CI run it.

### Screenshots and the demo app

Running the app on demo data, checking a change in a browser, and before/after screenshots for a PR. See `docs/agents/screenshots.md`.
