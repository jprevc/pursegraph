# Prototypes

Used by `/prototype` (and `/wayfinder` when it routes a ticket to one). Prototypes are static pages under `prototypes/<n>-<slug>/` on a throwaway `prototype/<n>-<slug>` branch, served by `python3 -m http.server` from the worktree root.

## Serving

- **Port:** 8000 + the issue number (#85 → 8085), so parallel worktrees never collide.
- **Start:** `python3 -m http.server <port> --bind 127.0.0.1` with `run_in_background`. Stop it with TaskStop on that task.
- **Stray servers:** `ss -ltnp | grep <port>` to see who holds the port; stop one with a bracketed pattern, `pkill -f "[h]ttp.server <port>"` (an unbracketed `pkill -f` matches the Bash call's own shell and kills it; a hook blocks it).

## Handoff

The handoff is done when the user can open the link right now:

1. The worktree is checked out on `prototype/<n>-<slug>` (not the issue branch: `prototypes/` exists only on the prototype branch).
2. The server is running from the worktree root, in the background.
3. `curl -s -o /dev/null -w '%{http_code}' <url>` on the exact URL you hand over returns `200`.

Then hand over the URL (with any `?variant=` query), not a recipe to run. Leave the server running until the user picks a variant; stop it at wrap-up.

## Screenshots

Python Playwright is not installed. Use the Playwright-cached Chromium under `~/.cache/ms-playwright/`:

- **Static shot:** `scripts/shoot <url> <out.png> [WxH]` (default 1440x1000). Use 390x844 for phone.
- **Shots after clicks/typing:** a scratchpad script run with `scripts/playwright <script.js>`, using `launch()`, `open(browser, url, { user: null })` and `shoot()` from `require('browser')` (`scripts/browser.js`).

Keep shots at viewport height (no 2600px full-page captures) and Read only the ones you are comparing; every image Read costs context.
