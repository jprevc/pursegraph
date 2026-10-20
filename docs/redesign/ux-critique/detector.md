# Assessment B: Detector + Browser Evidence (Pursegraph)

Run date 2026-10-16. Impeccable 4.6.0. Worktree read-only (live-server's `.impeccable/live/` scratch dir was removed after `stop --keep-inject`; `git status` clean).

## 1. CLI scan (`impeccable detect --json templates/`)

- **Exit 0, `[]` — 0 findings across 35 templates** (also 0 with `--no-config`).
- Caveat that makes this weak evidence: stderr says `could not read linked stylesheet {% static 'pursegraph.css' %}` — the detector cannot resolve Django `{% static %}` tags, so colour, contrast and custom-property rules never saw `static/pursegraph.css`. And static analysis of Django partials (`_*.html`, `{% include %}`) cannot see the assembled page. So "clean" means "nothing detectable in raw template markup", not "clean app".

## 2. URL scan (`impeccable detect --json <url>`)

- First try failed: exit 1 with `No Chrome, Chromium, Edge, or Brave installation found`. Fixed by setting `IMPECCABLE_BROWSER=<playwright chromium>`.
- The CLI has no cookie or session option, so only `/login/` could be scanned: 1440x900 and 390x844 both gave **1 advisory: low-contrast, `button`, #fff on #2a78d6 = 4.4:1**.
- I also tried `detect --cdp 9333 --target <path>` against an authenticated Chromium. It failed: `Warning: cannot access 9333`. 4.6.0's `detect` does not support `--cdp` (it is not in `--help` either; the critique reference describes it, but this CLI build doesn't have it). So the only detector evidence for authenticated pages is the overlay below.

## 3. Browser overlay (detect.js injected via Playwright)

Flow: `live-server --background` (port 8400) -> fresh Playwright context per width, logged in as `maja` -> mutation preflight (set `document.title` and append a `<script>`: both passed) -> scroll to top -> `add_script_tag(http://localhost:8400/detect.js)` -> wait 3 s -> collect console -> `live-server stop --keep-inject`. No injection errors. **There is no human-visible [Human] tab**: the run was headless Playwright, so the user never saw the overlay. The overlay screenshots and raw data were kept outside the repository.

Counts were identical at 1440 and 390, except for one extra phone finding on Rules.

| Page | Total | Breakdown |
|---|---|---|
| Spending `/spending/?period=2026-09` | 1 | low-contrast x1: `p.muted.hint` "Click a bar or a Category…" (#898781 on #f9f9f7, 3.4:1) |
| Review queue `/review/` | 24 | low-contrast x22: `button`/`button.accept` (#fff on #2a78d6, 4.4:1; "Accept all 21 suggestions" plus every row's Accept). low-contrast x2: `p.muted` intro and `span.muted.source` "Suggested · 76% sure" (3.4:1) |
| Transactions `/transactions/` | 24 | low-contrast x22: `button.accept`, `button` Filter (4.4:1). x1: `span.muted.source` (3.4:1). x1: `a.source` "Make a Rule" (#2a78d6 on #f9f9f7, 4.2:1) |
| Import `/import/` | 10 | low-contrast x8: `p.muted`, `span.muted`, `p.muted.iban` (3.4-3.5:1), Import button (4.4:1), "Manage Accounts" link (4.2:1). flat-type-hierarchy x1: body 14 / h4 15 / h3 17 / h1 18 / h2 22 px, largest adjacent step 1.22 (h1 is smaller than h2). repeating-stripes-gradient x1: from `.coverage .gap` (`static/pursegraph.css:69`) |
| Rules `/rules/` | 3 (+1 phone) | low-contrast: `p.muted` intro (3.4:1), `a.button` "New Rule" (4.4:1), "Edit" link (4.2:1). Phone only: body-text-viewport-edge on `p.muted` (161 chars, 16px from edge) |

By rule, deduped by distinct element type: low-contrast comes from 3 token pairs (`--muted` #898781 on page/surface = 3.4-3.5:1; white on `--accent` #2a78d6 = 4.4:1; `--accent` text on page = 4.2:1). Plus flat-type-hierarchy x1, repeating-stripes-gradient x1, body-text-viewport-edge x1.

## 4. Extra browser evidence (outside detector rules, found while inspecting overlay output)

1. **A Django template comment shows as text on every authenticated page.** `templates/_sidebar.html:1-2` uses a multi-line `{# … #}`. Django `{# #}` comments must fit on one line, so the comment renders literally: "{# The sidebar. Its links carry the dashboard's period and filters; … (`swap_nav`), so that they carry the view's. #}". It is visible at the top of the sidebar on all 14 authenticated pages I checked (`document.body.innerText` contains `{#`). Confirmed in the phone-review screenshot. The detector surfaced it only indirectly, because the `body` node's text in the flat-type finding started with it. Fix: `{% comment %}…{% endcomment %}`. Other multi-line `{#` comments may have the same problem: `dashboard/_filters.html`, `dashboard/_view.html`, `ledger/_transaction_row.html` and others contain `{#`, but I saw only the sidebar one leak. Worth grepping.
2. **Horizontal overflow at 390px.** Review, Transactions and Rules widen the layout viewport to 767-807 px, so the phone page zooms out or scrolls sideways. `<meta viewport>` is set correctly. Causes: the sidebar nav row (`aside`, `a.nav` items, `form.logout`) does not wrap, and the tables (`tr` 735px on Review and Rules, `nav.pages` on Transactions) have no scroll container. Import overflows slightly (tables 394px in a 390px viewport). Spending fits.
3. **Small touch targets (<24px in some dimension) at 390px:** Transactions 17, Rules 15, Import 24, Review 0. This is a raw count of `a, button, input, select, summary`. Some will be inline text links, which are exempt from WCAG 2.5.8.

## 5. False positives / caveats

- **CLI "0 findings" is a false negative** (see section 1: CSS unresolved, partials).
- **body-text-viewport-edge (Rules, phone)** is a side effect of the overflow in 4.2: the layout viewport is 776px wide, so the `p` really sits at the page edge. That will go away once the overflow is fixed. It is not a separate measure/padding problem.
- **flat-type-hierarchy and repeating-stripes-gradient were reported on Import only**, attributed to `body`, and only that page triggers them. The stripes are the hatched "gap" marks on the statement-coverage bar, which carry meaning. That is defensible, not decoration, so I count it as a false positive.
- **The low-contrast 4.4:1 and 4.2:1 hits are real but marginal** (just under 4.5). The detector repeats them for each button (22x per page), which inflates the counts; the real issue is 3 colour tokens.

## 6. Look-only vs structural classification

| Finding | Class | Carries into redesign? |
|---|---|---|
| low-contrast `--muted` 3.4:1 | look-only (token value) | Low value. Note for the new palette: secondary text must reach >= 4.5:1 |
| low-contrast white on accent 4.4:1, accent text 4.2:1 | look-only | Low value. Same note for the new accent |
| flat-type-hierarchy (h1 18px < h2 22px) | mostly look-only. h1 smaller than h2 is a heading-role inversion | Low-medium. Check that the redesign's type scale keeps h1 > h2 |
| repeating-stripes-gradient (coverage gaps) | look-only, false positive | No |
| **Leaked `{# #}` sidebar comment** | **structural (template bug)** | **Yes, a real bug visible on every page. Fix now, independent of the redesign** |
| **Phone horizontal overflow (nav not wrapping, tables without scroll wrapper)** | **structural (layout/responsive)** | **Yes. The redesign needs a mobile nav pattern and a table strategy (scroll wrapper or stacked rows)** |
| body-text-viewport-edge (Rules phone) | structural, but derived from overflow | Resolves with the overflow fix |
| Touch targets <24px at phone | structural (a11y) | Yes, needs a check after the redesign |

## 7. Skipped / failed steps

- URL detector scan of authenticated pages: skipped. The CLI has no cookie/session option, so only `/login/` was scanned.
- `detect --cdp`: failed. Not supported in 4.6.0 (`cannot access 9333`).
- `[Human]` visible tab: not possible. No interactive browser tool, so the run was headless.
- First URL scan: failed (no browser found) until `IMPECCABLE_BROWSER` was set.
- Live server started in the background on port 8400 and stopped with `live-server stop --keep-inject`. No project files were injected or modified.
