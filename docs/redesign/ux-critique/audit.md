# Pursegraph: `/impeccable audit` (technical quality)

Scope: Django templates + HTMX, `static/pursegraph.css`, `static/dashboard.js`, vendored ECharts 5.6.1 / htmx. Worktree at `f0240ff` (branch `prototype/62-visual-direction`). Live app on :8765 with the fictional demo Household. Bar: WCAG 2.2 AA, per `PRODUCT.md`. A redesign is coming, so Theming is scored on how ready the code is for it, and contrast on the current palette is only noted briefly. Already-filed issues #51, #53, #54 and #57 are left out.

## How the evidence was gathered

- **Rendered measurements** came from Playwright with Chromium 1234. I scanned 16 authenticated screens as `maja` at 1440×900, at 390×844 (mobile emulation with touch), at 720×450 (200% zoom of 1440) and at 320×640 (the 1.4.10 reflow width). I measured `scrollWidth`, the elements that overflow, the size of every interactive element, headings, landmarks, live regions and `aria-current`, and the accessible names of the charts.
- **axe-core 4.10.2** (vendored into the scratchpad) ran on every screen with the wcag2a/aa, 21a/aa, 22aa and best-practice rules.
- **Keyboard probes.** I tabbed through the Dashboard, pressed Enter and Space on drill-down rows, switched views, stepped the period with the keyboard, used Escape on the Accounts filter, pressed ArrowDown on an outcome `<select>` and pressed Accept in the Review queue. **Every POST was intercepted and answered with the unchanged row, so no demo data was modified.**
- **Detector.** `impeccable detect templates/` returned `[]` because the Django tags don't resolve and the linked CSS can't be read. This build has no `--cdp` mode. So I ran it on rendered DOM snapshots (`scratchpad/audit/dom/*.html`, with the CSS copied next to them) and checked each hit by hand (see Implementation Integrity).
- **Raw data:** `scratchpad/audit/measure.json` and `scratchpad/audit/keyboard.json`. New screenshots are in `scratchpad/shots-c/`.
- **Not tested:** a real screen reader (NVDA/VoiceOver), Firefox and Safari, a physical phone, and browser text-size settings beyond reading the CSS units.

## Audit Health Score

| # | Dimension | Score | Key Finding |
|---|-----------|-------|-------------|
| 1 | Accessibility | 2 | The outcome `<select>` saves on every arrow key and focus then drops to `<body>`; no live regions on any screen; no focus management after any HTMX swap |
| 2 | Performance | 3 | Full ECharts bundle (1.03 MB, 334 KB gzipped) loads for five chart types; everything else is lean and deferred |
| 3 | Theming | 2 | Tokens exist, but the sidebar (8 hex values), `#fff` (5×) and all 18 chart colours in `dashboard.js` are hard-coded; no `color-scheme`; charts can't follow a theme change |
| 4 | Responsive Design | 1 | 8 of 16 screens scroll sideways at 390 px, including the **Review queue** (767 px) and the Dashboard drill-down (707 px). The cause is one CSS line |
| 5 | Implementation Integrity | 2 | A broken Django comment is printed as text at the top of every signed-in page; chart colours collide from the 10th Category; number formats disagree between chart and table |
| **Total** | | **10/20** | **Acceptable (significant work needed)** |

## Implementation Integrity Verdict

**Fail (narrowly).** The structure is coherent and specific to this product. The vocabulary is used consistently, every chart has a drillable table beside it, forms have real `action`s and `<noscript>` fallbacks, and plurals use `blocktranslate count`. Four verified problems pull the score down:

1. **A template comment shows on every signed-in page.** `templates/_sidebar.html:1-2` opens a `{# … #}` comment that runs over two lines. Django's `{# #}` comment is single-line only, so the text "{# The sidebar. Its links carry the dashboard's period and filters; a view swapped in by HTMX swaps it (`swap_nav`), so that they carry the view's. #}" is printed above the brand on every shell page. It is in all 16 DOM snapshots and in the existing phone screenshots. It is also the first thing a screen reader reads, and the accessible name `<body>` gets whenever focus is lost (see P0).
2. **Category colours collide.** `PALETTE[Number(key) % 9]` (`dashboard.js:15`) gives the 10th Category (id 10) the same colour as Food (id 1). The demo uses ids 1-7, so it doesn't show today.
3. **Number formats disagree.** The same figure appears as `1187.92` in a table (`floatformat:2`) and as `€1,188` in the chart (`toLocaleString(undefined, …)`, which uses the browser locale). See P1-6.
4. **The CSS was added to piecemeal.** There are four separate `@media (max-width: 900px)` blocks (lines 32, 114, 126, 129), and rules for one component are spread across the file (for example `.split` at 104, 114, 127 and 129). This doesn't break anything yet, but it explains how the responsive blow-out in P1-2 got through.

**Detector results, verified:**

| Rule | Hits | Verdict |
|---|---|---|
| `low-contrast` (warning) | 25 | **True.** `--muted` `#898781` on `--page` is 3.4:1 |
| `low-contrast` (advisory) | 127 | **True.** White on `--accent` `#2a78d6` is 4.41:1 |
| `flat-type-hierarchy` | 2 | **True.** The sidebar `h1` (18 px) is smaller than each page's `h2` (22 px), and the largest step is 1.22:1 |
| `marquee` | 16 | **False positive.** It matched the axe-core source I injected (`marquee:{type:"structure"…`), not the app |
| `repeating-stripes-gradient` | 16 | **False positive in intent.** It is `.coverage .gap`, a deliberate way to show Coverage gaps without relying on colour. Keep it |

## Executive Summary

- **Score:** 10/20 (Acceptable).
- **Issues:** 1 P0, 6 P1, 8 P2, 3 P3.
- **Top issues:**
  1. **[P0]** In the Review queue, Transactions and drill-down, ArrowDown on an outcome `<select>` saves that outcome immediately. The row is swapped and focus falls to `<body>`, so a keyboard user can't do the weekly routine.
  2. **[P1]** At 390 px the Review queue is 767 px wide and the drill-down 707 px. The phone browser zooms out the whole page (the layout viewport measured 1531 px tall). The cause is `.shell { grid-template-columns: 1fr }` at ≤900 px.
  3. **[P1]** No HTMX swap moves focus or announces anything. There are 0 `aria-live`, `status` or `alert` regions across 16 screens, and the drill-down loads off-screen without a word.
  4. **[P1]** Drill-down rows are fake buttons: `tr tabindex=0` with no role, name or expanded state, opened only by Enter on `keyup`. Space scrolls the page instead.
  5. **[P1]** The broken template comment prints on every page (see the verdict above).
- **Next steps:** fix the select-commit and focus loss (harden), the single `1fr` → `minmax(0,1fr)` line plus table strategy on phones (adapt), and live regions and focus targets for every HTMX swap (harden). Put number and date formatting behind one locale-aware filter before the redesign spreads `floatformat` further.

## Detailed Findings by Severity

### P0 Blocking

**[P0] The outcome `<select>` saves on every keystroke, then drops focus to `<body>`**
- **Location:** `templates/ledger/_transaction_row.html:7-8`: `hx-trigger="change, submit" hx-target="closest tr" hx-swap="outerHTML"`. It is used by the Review queue, Transactions and the Dashboard drill-down.
- **Category:** Accessibility.
- **Evidence:** I focused the first Review-queue select and pressed ArrowDown once. That immediately sent `POST /transactions/237/outcome/` (intercepted). After the swap, `document.activeElement` was `<body>`. Pressing Accept with Enter did the same: one POST, then focus went to `<body>`. In Chromium and Firefox on Windows and Linux, a closed `<select>` fires `change` on each arrow key.
- **Impact:** A keyboard user who arrows through the Subcategories to find the right one saves the first wrong one. Then they lose their place and must tab back through 13 sidebar stops and every earlier row. In the drill-down, each accidental save also re-fetches `#numbers`. This makes the weekly routine ("clear the Review queue in minutes") impossible without a mouse.
- **The same pattern** appears without data loss in the dashboard **Period** select (`_period.html:6`, `hx-trigger="change"`) and the **Member** select (`_filters.html:2`). One arrow key swaps the whole view, and focus is lost again.
- **WCAG:** 3.2.2 On Input (A), 2.4.3 Focus Order (A), 2.1.1 Keyboard (A).
- **Recommendation:**
  - Don't save on `change` from the keyboard. Either save on an explicit Save/Accept button, or trigger on `change` only when the last input was a pointer, plus an Enter key.
  - After the swap, restore focus to the same control in the new row. `hx-swap="outerHTML focus-scroll:false"` isn't enough on its own: re-focus by id in `htmx:afterSwap`, or swap only the `<td>` contents.
  - After Accept, move focus to the next row's select so the queue can be cleared from the keyboard alone.
- **Suggested command:** `/impeccable harden`

### P1 Major

**[P1-1] A broken template comment prints on every signed-in page**
- **Location:** `templates/_sidebar.html:1-2`.
- **Category:** Implementation Integrity / Accessibility.
- **Impact:** The comment is visible above the brand on desktop and phone (`shots/phone-review-queue.png`). It is the first text a screen reader reads, and it would appear in README screenshots.
- **WCAG:** 1.3.2 Meaningful Sequence (indirect).
- **Recommendation:** Use `{% comment %}…{% endcomment %}`, or keep the comment on one line. Add a test that rendered pages don't contain `{#`.
- **Suggested command:** `/impeccable polish`

**[P1-2] Horizontal overflow on phones: one CSS line breaks 8 of 16 screens, including the Review queue and drill-down**
- **Location:** `static/pursegraph.css:33`, `@media (max-width:900px){ .shell { grid-template-columns: 1fr; } }`. A `1fr` track has an `auto` minimum, so a wide table stretches the whole column, the sidebar included. `.stack` (line 115) has the same problem and makes Trends 984 px wide even though its table is inside `.scroll`.
- **Category:** Responsive.
- **Evidence:** `scrollWidth` at 390 px:

  | Screen | Width (px) |
  |---|---|
  | Trends | 984 |
  | Review queue | 767 |
  | Transactions | 767 |
  | Rules | 767 |
  | Accounts | 628 |
  | Members | 454 |
  | Categories | 402 |
  | Account edit | 398 |
  | Spending after tapping a Category (drill-down) | 707 |

  With `is_mobile` set, the browser then zooms the whole page out to fit (`innerHeight` went from 844 to 1531), so all text shrinks. The Review queue's outcome select and Accept button start past the right edge (`shots-c/phone-review-fold.png`). At 320 px, Cashflow, Import and Account edit also overflow.
- **Impact:** The Review queue and Dashboard drill-down are the two screens `PRODUCT.md` says must be genuinely good on a phone. Both pan sideways, and Accept is off-screen.
- **WCAG:** 1.4.10 Reflow (AA).
- **Recommendation:**
  - Use `grid-template-columns: minmax(0,1fr)` in the 900 px block, and give `.stack` an explicit `minmax(0,1fr)` column.
  - Wrap every data table in an `overflow-x:auto` region with a label, as a minimum.
  - For the Review queue and drill-down specifically, lay each Transaction out as a stacked card below roughly 600 px: date and amount on one line, description, then the outcome control at full width. A 5-column table can't reflow to 320 px.
- **Suggested command:** `/impeccable adapt`

**[P1-3] HTMX swaps never move focus or announce what changed**
- **Location:**
  - `dashboard/_nav.html` (view links)
  - `_period.html` (‹ › and the selects)
  - `_filters.html`
  - every drill-down row (`hx-target="#drill"`)
  - `_transaction_row.html` (row swap)
  - `#review-queue-count` (out-of-band update)
- **Category:** Accessibility.
- **Evidence:**
  - Switching view from the keyboard (Cashflow link, Enter) left focus on `<body>`, and `document.title` stayed "Dashboard · Pursegraph". The ‹ period step did the same.
  - Pressing Enter on the Home row filled `#drill` (18 KB of HTML) with its top at y=898 in a 900 px viewport, which is off-screen. Focus stayed on the row, and `#drill` has no `aria-live`, role, `tabindex` or heading.
  - Across 16 screens there are 0 `[aria-live]`, `[role=status]` or `[role=alert]` elements.
- **Impact:** Screen-reader users get no feedback that a view, period or drill-down changed. Sighted keyboard users also lose their place on every view switch.
- **WCAG:** 4.1.3 Status Messages (AA), 2.4.3 Focus Order (A), 2.4.2 Page Titled (A).
- **Recommendation:**
  - After a view or period swap, focus the view's `h2` (`tabindex="-1"`) and set `document.title` from the swapped content. htmx updates the title if the partial includes a `<title>`.
  - Give the drill-down a heading ("Transactions in Home, September 2026") and focus it, or announce "N Transactions loaded" through a polite live region, and scroll it into view.
  - Make the Review-queue count an `aria-live="polite"` status.
- **Suggested command:** `/impeccable harden`

**[P1-4] Drill-down table rows are fake buttons**
- **Location:** `dashboard/_spending.html:9`, `_cashflow.html:10`, `_trends.html:11`, `_per_member.html:9,14` and `_money_flow.html:8,13`: `<tr tabindex="0" hx-get … hx-trigger="click, keyup[key=='Enter']">`.
- **Category:** Accessibility.
- **Evidence:**
  - The focused row reports `role: null`, so it is announced as a table row with no hint that it acts.
  - Space did nothing to `#drill` and scrolled the page (`scrollY` 91).
  - No row has `aria-expanded` or `aria-controls`, and the open row isn't marked.
  - Spending's Subcategory rows aren't drillable (`_spending.html:14`), but those in Per Member and Money flow are.
  - The only `:focus` styling (`pursegraph.css:107,124`) changes the background from `#fcfcfb` to `#f9f9f7` (about 1.0:1). Visibility depends entirely on the browser's default `outline:auto`, which Chromium draws (`shots-c/desktop-row-focus.png`) but other engines render unreliably on `<tr>`.
- **WCAG:** 4.1.2 Name, Role, Value (A), 2.1.1 Keyboard (A), 2.4.7 Focus Visible (AA).
- **Recommendation:**
  - Put a real `<button>` (or an `<a href>` to the drill URL, which also helps progressive enhancement) in the first cell, give it `aria-expanded` and `aria-controls="drill"`, and keep `tr:hover` for pointer users only.
  - Make Subcategory drill-down consistent across views.
- **Suggested command:** `/impeccable harden`

**[P1-5] Charts rely on colour alone and have no accessible name**
- **Location:** `static/dashboard.js` options (lines 17-99) and `_view.html:12`.
- **Category:** Accessibility.
- **Evidence:**
  - All five chart containers have no `role` or `aria-label`, and the SVG renderer outputs an unnamed `<svg>`. ECharts `aria` isn't enabled (only its decal defaults are present).
  - Trends draws 8 solid lines told apart only by colour. Cashflow's In and Out bars and Per Member's stacked segments are also colour-only.
  - The one non-colour cue is the dashed "To/from other Members" line.
  - The palette wraps at 9 (see the verdict above).
  - ECharts animation stays `'auto'` with `prefers-reduced-motion: reduce`.
- **Mitigation:** every view has a full data table beside the chart, which is a real text equivalent. That's why this is P1 and not P0.
- **WCAG:** 1.4.1 Use of Color (A), 1.1.1 Non-text Content (A). It is also an explicit `PRODUCT.md` requirement.
- **Recommendation:**
  - Give each chart `role="img"` and an `aria-label` that summarises it and points to the table, or hide it with `aria-hidden="true"` and say that the table is the accessible version.
  - Add direct end-of-line labels to Trends and per-segment labels or decals to stacked bars. ECharts `aria: { enabled: true, decal: { show: true } }` gives patterns for free.
  - Stop the palette colliding: assign colours by sort order, or store a colour per Category.
  - Set `animation: !matchMedia('(prefers-reduced-motion: reduce)').matches`.
- **Suggested command:** `/impeccable colorize` (encoding), then `/impeccable harden`

**[P1-6] Numbers and dates aren't formatted by locale, and they disagree with each other**
- **Location:** 36 uses of `floatformat` and hard-coded `date:"…"` across the templates, for example `_sidebar.html:21-23`, every `dashboard/_*.html`, `_transaction_row.html:5` (`{{ t.amount }}` is a raw Decimal and the date is `"Y-m-d"`), `import.html` (`"j M Y"`) and `dashboard.js:7` (`toLocaleString(undefined, …)`).
- **Category:** Implementation Integrity / i18n.
- **Evidence:** Table cells show `1187.92` with no € and no grouping. The chart shows `€1,188` (the browser locale, en-US here). The sidebar shows `4520.00`. In Slovenian, `floatformat:2` would become `1187,92`, still without grouping, while the chart would follow the viewer's browser and not the app's language.
- **Impact:** This works against "Trust the numbers": one figure is rendered three ways. It also doesn't meet the `1.234,56 €` sl-SI convention in `PRODUCT.md`. Fixed `Y-m-d` dates won't follow a later locale switch either.
- **Recommendation:**
  - Add one template filter, for example `|money`, that returns a locale-formatted EUR string (Babel, or Django's `number_format` with `USE_THOUSAND_SEPARATOR`). Use `SHORT_DATE_FORMAT` and `DATE_FORMAT` instead of literals.
  - In JS, pass `document.documentElement.lang`, or a `data-locale` set by the server, to `Intl.NumberFormat`, and never `undefined`.
- **Suggested command:** `/impeccable harden`

### P2 Minor

**[P2-1] Heading, landmark and title structure**
- **Location:** `_sidebar.html` and `shell.html`.
- **Evidence:**
  - The only `h1` is the "Pursegraph" brand in the sidebar on every page; each page's real heading is an `h2`.
  - All five Dashboard views are titled "Dashboard · Pursegraph".
  - The current nav item is marked only by the `.on` class, with no `aria-current`.
  - Only the five view links sit inside a `<nav>`. Transactions, Import and the other links are bare inside `<aside>`.
  - Two unlabelled `<nav>`s on Transactions trigger axe `landmark-unique`.
  - There's no skip link, so there are 13 tab stops before the content.
- **WCAG:** 1.3.1, 2.4.1, 2.4.2, 2.4.6.
- **Recommendation:**
  - Make the page heading the `h1`, with the brand as a link or plain text.
  - Use per-view `<title>`s and `aria-current="page"`.
  - Use one labelled `<nav aria-label="Main">`, and a "Skip to content" link.
- **Suggested command:** `/impeccable harden`

**[P2-2] Touch targets**
- **Evidence at 390 px:**
  - Below the 24 px AA minimum:
    - Previous/Next period ‹ ›: 22×24
    - `button.link` (Deactivate, Make admin): 20 px tall
    - "Make a Rule": 69×17
    - Edit and Delete text links in tables: 19-20 px tall
    - Move ↑ and ↓: 23×26
  - Every control on the Review queue (57 of 57) and Dashboard is under 44 px. The Review queue selects and Accept buttons measure about 28-30 px.
- **WCAG:** 2.5.8 Target Size (Minimum) (AA) for the sub-24 px cases; 44 px is the product's own phone goal.
- **Recommendation:** Have the redesign tokens set a minimum control height of 44 px on coarse pointers (`@media (pointer: coarse)`). Make the period arrows real buttons of at least 44×44.
- **Suggested command:** `/impeccable adapt`

**[P2-3] Sizes are fixed in px, so text scaling and longer strings break the layout**
- **Evidence:**
  - The CSS has 162 `px` values and no `rem` or `em`; `body` is `15px`. A browser default-font-size setting has no effect.
  - Fixed tracks and widths: sidebar `220px`, table column `340px` and `420px` (`.split`, `.split.wide`), `white-space: nowrap` on `.split.wide` cells and account-filter labels, and outcome select `max-width:260px`.
  - Labels are long already ("Transfer, one-sided", "Pair with 2026-10-05 · Joint Revolut · …"), and Slovenian will be longer.
  - On phones the sidebar flattens into a wrapped header of 12 links plus the month figures, about 215 px of chrome before any content.
- **WCAG:** 1.4.4 (zoom does pass: no overflow at 720 px except tables), 1.4.12.
- **Recommendation:** Use rem-based type and spacing tokens, and `minmax()` and `ch`-based tracks. Below 900 px, put the navigation behind a compact menu, and keep the month figures to the Dashboard.
- **Suggested command:** `/impeccable layout`

**[P2-4] Theming readiness**
- **Location:** `pursegraph.css:16-23, 72, 133-134` and `dashboard.js:4-10, 72`.
- **Evidence:**
  - There are 9 `:root` tokens, but the sidebar uses 8 hard-coded hex values (`#1d1d1b`, `#e8e7e2`, `#c3c2b7` ×3, `#2c2c2a`, `#f0efec`, `#3a3a37`, `#0b0b0b`).
  - Inputs, buttons and the filter popover use `#fff` 5×, plus one raw `rgb()` shadow.
  - `dashboard.js` holds 18 colour literals, including the segment border `'#fcfcfb'`, which duplicates `--surface`. These are read once at `echarts.init`.
  - There's no `color-scheme` and no dark tokens.
  - The tokens `--bad` and `--good` are named as judgements, which runs against "Describe, don't judge".
- **Impact:** A theme toggle would leave the sidebar and every chart in the light palette. Charts need their colours read from CSS custom properties, plus a re-`setOption` on `prefers-color-scheme` or toggle change.
- **Recommendation:**
  - Move all colours into role tokens (surface, ink, nav-bg, nav-ink, chart-1…n, series-in, series-out, grid, axis).
  - Have `dashboard.js` read them through `getComputedStyle(document.documentElement)` and re-apply them on a `matchMedia` or toggle event.
  - Rename the tokens to `--danger` and `--success`, or to neutral roles.
- **Suggested command:** `/impeccable colorize` (as part of the redesign)

**[P2-5] Full ECharts bundle**
- **Location:** `static/vendor/echarts.min.js`.
- **Evidence:** 1,034,102 B raw and 334,372 B gzipped, for bar, line, sankey and the SVG renderer only. Load is otherwise fast (DCL about 50 ms locally). The dev server sends no compression or cache headers, but production uses WhiteNoise `CompressedManifestStaticFilesStorage`, so hashed, compressed and cacheable files there are fine.
- **Impact:** Matters mainly for the first Dashboard visit on a phone over VPN.
- **Recommendation:** Vendor a custom ECharts build (bar, line, sankey, grid, tooltip, legend, aria, SVGRenderer), roughly a third of the size.
- **Suggested command:** `/impeccable optimize`

**[P2-6] The Accounts filter popover**
- **Location:** `dashboard/_filters.html:14-21`.
- **Evidence:** The `<details>` doesn't close on Escape (it was still open afterwards) or on an outside click. Its absolutely positioned panel can cover the period controls.
- **WCAG:** 1.4.13 (by analogy), 2.1.2.
- **Recommendation:** Close it on Escape and on focus-out, and return focus to the summary.
- **Suggested command:** `/impeccable harden`

**[P2-7] Destructive actions run immediately**
- **Location:** Rule Delete (`rules.html:28`), Category and Subcategory Delete (`categories.html:21,40`), Deactivate a Member (`members.html:19`).
- **Evidence:** One click posts, with no confirmation and no undo. Statement and Account deletes do have confirmation pages, so this is inconsistent.
- **Recommendation:** Add a confirm step, or an undo notice in a live region.
- **Suggested command:** `/impeccable harden`

**[P2-8] Contrast on the current palette (brief, since the redesign replaces it)**
- **Evidence:** `--muted` `#898781` is 3.4:1 on the page and 3.49:1 on panels. It is used for hints, help text, "Suggested · N% sure" and Category kinds (axe flagged 139 nodes on Transactions alone). White on `--accent` is 4.41:1, and `button.link` is 4.18:1.
- **WCAG:** 1.4.3 (AA).
- **Recommendation:** The new tokens should reach at least 4.5:1 for every text role in both themes.
- **Suggested command:** `/impeccable colorize`

### P3 Polish

- **[P3-1]** In `categories.html:38`, the Subcategory "Move down" button is never disabled on the last item; the Category one is.
- **[P3-2]** Action and drag-handle columns have empty `<th>` (axe `empty-table-header` on Accounts, Rules and Members). Add visually hidden "Actions" text. The ⠿ handle is correctly `aria-hidden`, and ↑/↓ give keyboard users a way to reorder.
- **[P3-3]** On login and set-password, error messages aren't linked to their fields (`aria-invalid`, `aria-describedby`). Hints also say "Click…", which reads oddly on touch; "Select…" or "Tap or click…" works for both.

## Patterns and Systemic Issues

- **HTMX is used without accessibility handling.** Every swap (view, period, filter, drill-down, row, count) skips focus restore, announcement and title update. Add one small `htmx:afterSwap` handler and a live-region convention for all of them, not per-template patches.
- **Saving on `change` is the default interaction.** Outcome, Period and Member selects all act on `change`. That is fine for a mouse and breaks keyboard use (3.2.2).
- **Grid tracks without `minmax(0, …)`.** The desktop shell has it, but the phone breakpoint and `.stack` don't. Each wide table then breaks the page width.
- **Formatting is spread across templates.** There are 36 hand-written `floatformat` and `date:` calls plus one JS formatter with a different locale. The i18n and "Trust the numbers" requirements need one formatting function on each side.
- **Colours live in two places.** CSS has partial tokens and JS has its own literals; the redesign should make CSS the single source.

## Positive Findings

- `<html lang>` is set. axe found **no** missing form labels, empty buttons or bad ARIA on any screen. Icon-only controls (↑ ↓ ‹ ›) have `aria-label`s.
- **Every chart has a full, drillable data table**, the strongest accessibility decision in the app. The disabled Member select on Per Member also explains itself in visible text, not only in a `title`.
- **Progressive enhancement is real.** HTMX forms keep a real `method` and `action`, `<noscript>` adds Submit buttons, and the drill-down and nav links are real URLs with `hx-push-url`.
- **Drag-to-reorder Rules has a keyboard alternative** (↑/↓ buttons), and the handle is `aria-hidden`.
- **Coverage gaps use stripes, not just red**: a non-colour cue in the spirit of the product's own requirement.
- **i18n markup is thorough.** Everything uses `translate`/`blocktranslate`, with correct `count` plurals, so it is ready for Slovenian once the formatting is centralised.
- **Assets are lean and self-hosted.** Scripts use `defer`, there's no build step, CSS is 8.7 KB, `dashboard.js` cleans up its `ResizeObserver` and chart instance on swap, and history restore re-mounts charts.
- `font-variant-numeric: tabular-nums` on amounts, `confine: true` on tooltips, and no gratuitous motion in the CSS.

## Recommended Actions

1. **[P0] `/impeccable harden`**: stop the outcome, Period and Member selects from saving on arrow keys. Restore focus to the same control after a row swap, and move to the next row after Accept.
2. **[P1] `/impeccable polish`**: fix the multi-line `{# #}` in `_sidebar.html`, and add a "no `{#` in rendered HTML" test.
3. **[P1] `/impeccable adapt`**: make the phone shell `minmax(0,1fr)` and fix `.stack`; lay out the Review queue and drill-down as stacked cards below about 600 px; use labelled scroll regions for the other tables.
4. **[P1] `/impeccable harden`**: an HTMX accessibility layer, covering focus to the view heading or drill-down heading, a polite live region, per-view `<title>`, a live Review-queue count, and real buttons with `aria-expanded` in drill-down rows.
5. **[P1] `/impeccable colorize`**: chart encoding beyond colour (direct labels, decals, dashes), stable per-Category colours, and chart `role="img"` and labels. Then `/impeccable harden` for reduced-motion handling in the charts.
6. **[P1] `/impeccable harden`**: one locale-aware money and date formatter in templates and JS.
7. **[P2] `/impeccable layout`**: rem-based scale, flexible tracks for Slovenian strings, compact phone navigation, and the heading, landmark and skip-link structure.
8. **[P2] `/impeccable adapt`**: 44 px controls on coarse pointers and real period buttons.
9. **[P2] `/impeccable colorize`**: full role tokens, charts reading CSS variables and re-applying on theme change, `color-scheme`, and AA contrast in both themes.
10. **[P2] `/impeccable optimize`**: a custom ECharts build.
11. **[P2] `/impeccable harden`**: Escape and outside-click close for the Accounts filter, and confirm or undo for destructive actions.
12. **`/impeccable polish`**: final pass, including the P3 items.

> You can ask me to run these one at a time, all at once, or in any order you prefer.
>
> Re-run `/impeccable audit` after fixes to see your score improve.
