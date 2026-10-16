# UX critique of the current app (pre-redesign)

The findings for the [UX critique of the current app](https://github.com/jprevc/pursegraph/issues/61) ticket on the [UI/UX redesign map](https://github.com/jprevc/pursegraph/issues/59). It records where the app fails its users **independently of its look**: flows, hierarchy, states, feedback, copy, accessibility and phone layout. The current colours and fonts are being replaced, so findings about them are left out, except where they set a floor for the new palette.

Already filed and not repeated here: [#51](https://github.com/jprevc/pursegraph/issues/51), [#53](https://github.com/jprevc/pursegraph/issues/53), [#54](https://github.com/jprevc/pursegraph/issues/54), [#57](https://github.com/jprevc/pursegraph/issues/57).

## How it was run

- **Data:** the app ran locally at `f0240ff` (`main` plus PRODUCT.md) on a throwaway database holding a fictional Household (Maja, an admin, and Luka, a Member). It covers April–October 2026 with 4 Accounts, one of them an "Other" savings Account. One gap is deliberate: Luka's N26 has no July Statement. It has 22 Transactions in the Review queue and 5 Rules. No real Statements were used.
- **Method:** `/impeccable critique`, dual-agent. The design review (A) and the detector and browser evidence (B) ran in isolation from each other. `/impeccable audit` ran as a third, independent agent.
- **Browser:** headless Chromium via Playwright at 1440×900 and 390×844 (mobile emulation with touch), plus 720 px (200% zoom) and 320 px (reflow). The audit also used axe-core 4.10.2 and keyboard probes; their POSTs were intercepted, so no data changed.
- **Not tested:** a real screen reader, Firefox or Safari, or a physical phone.
- **Raw reports** are in [`ux-critique/`](ux-critique/): [design review](ux-critique/design-review.md), [detector evidence](ux-critique/detector.md) and [technical audit](ux-critique/audit.md). Screenshot paths in them point at the session's scratch directory and were not kept.

## Scores

| Measure | Result |
|---|---|
| Nielsen heuristics (design review) | **21/40, Acceptable.** 2 on every heuristic except Help (3) |
| Cognitive load | **High.** 5 of 8 checks fail: single focus on a phone, chunking, visual hierarchy, minimal choices, working memory |
| Technical audit | **10/20, Acceptable.** Accessibility 2, Performance 3, Theming readiness 2, Responsive 1, Implementation integrity 2 |
| Detector (`impeccable detect`) | **0 findings on templates, but a false negative.** It reads Django partials one at a time and never sees the linked CSS. In-page, the overlay found 62 findings on 5 pages, almost all from three low-contrast colour pairs in the current palette |

**Specificity verdict:** the domain is specific to this product, but the shell is generic.

- **What's specific:**
  - "Awaiting review" is counted in every view, so totals are never quietly incomplete.
  - Transfers are kept out of spending, and there's a Joint bucket.
  - The Money flow chart balances.
  - Import has a Coverage timeline and reconciliation diagnostics.

  No finance template does these.
- **What's generic:**
  - The container is a flat 13-item sidebar that mirrors the code's modules, not the Household's two jobs: the driver's import then review, and the reader's "where did it go last month?".
  - Each screen is the same shape: a heading, a table and a panel.
  - The trust signals (Coverage, review state) stay on the screens that produce them and never reach the Dashboard, where trust is needed.

## Priority findings

Ranked across all screens. **Lands in** names the map ticket or redesign slice the finding belongs to.

### P0: blocking

1. **The outcome select saves on every arrow key, then focus drops to `<body>`.**
   - **Where:** `templates/ledger/_transaction_row.html:7-8`, with `hx-trigger="change"` and the row swapped in place. Used in the Review queue, Transactions and the drill-down.
   - **What happens:** in Chromium and Firefox, a closed `<select>` fires `change` on each ArrowDown. So a keyboard user saves the first wrong Subcategory, then has to tab back through the sidebar and every earlier row.
   - **The same pattern** swaps the whole view on the Dashboard's Period and Member selects.
   - **Fix:** commit only on an explicit action (Accept/Save, or Enter). Restore focus to the same row after the swap, and move it to the next row after Accept.
   - **WCAG:** 3.2.2, 2.4.3, 2.1.1.
   - **Lands in:** the shared Transaction-row component (Review queue slice).

### P1: major

2. **Coverage gaps and partial periods are invisible on the Dashboard.**
   - Luka's missing July Statement makes Food look about 25% lower in July (659 against about 900) and Leisure 0.
   - Months before any Statement are drawn as real zeros.
   - The running month is plotted like a complete one: in Category trends, Home falls to 0 and Awaiting review jumps to 2,148.
   - Nothing in `dashboard/` reads Coverage. This breaks PRODUCT.md's "Trust the numbers", and the result is exactly the argument the product exists to prevent.
   - **Fix:**
     - The view header states how complete the period is ("Luka's N26 has no Statement for 1–31 Jul").
     - Charts mark months without data and the partial current month as such, not as 0.
     - The period stepper stops at the first Coverage date.
   - **Lands in:** the Dashboard slice. It adds behaviour and isn't only a restyle (see Open questions).

3. **On a phone, the screens that must work on a phone don't.**
   - **Sideways scrolling:** at 390 px, 8 of 16 screens scroll sideways.

     | Screen | Width (px) |
     |---|---|
     | Category trends | 984 |
     | Review queue | 767 |
     | Transactions | 767 |
     | Rules | 767 |
     | Spending after tapping a Category (drill-down) | 707 |
     | Accounts | 628 |

     The browser then zooms the whole page out, and Accept starts past the right edge.
   - **Root cause:** one CSS line, `static/pursegraph.css:33` (`.shell { grid-template-columns: 1fr }` at ≤900 px, which lacks `minmax(0,1fr)`), plus `.stack`. Data tables also have no phone layout.
   - **Navigation:** it becomes a wrapped wall of 13 links plus the month figures, so content starts at y=417 of 844.
   - **Fix:**
     - Use `minmax(0,1fr)` tracks.
     - Below about 600 px, show each Transaction as a stacked card: description and amount, then date and Account, then the outcome control at full width.
     - Use compact phone navigation.
   - **WCAG:** 1.4.10.
   - **Lands in:** App shell and navigation, then the Review queue and Dashboard slices.

4. **The sidebar's "This month" contradicts the Dashboard.**
   - The sidebar always shows the current month so far (`dashboard/queries.py:556`), labelled only "This month".
   - The Dashboard opens on the last complete month (`dashboard/periods.py:70`).
   - So the default landing shows "Spent 2661.37" (October, 81% of it Awaiting review) next to "Total 2626.01" (September).
   - **Fix:** take the figures out of the global shell. The Dashboard header carries the headline for its own period, including how complete it is.
   - **Lands in:** App shell and navigation.

5. **A template comment shows as text on every signed-in page.**
   - `templates/_sidebar.html:1-2` uses a `{# … #}` comment over two lines, and Django's `{# #}` only works on one.
   - So "{# The sidebar. Its links carry… #}" is the first thing on every screen. It is also the first thing a screen reader reads, and it would appear in README screenshots.
   - **Fix:** use `{% comment %}`, and add a test that rendered pages contain no `{#`.
   - **A live bug** on `main`, which can be fixed now, independently of the redesign.

6. **The drill-down has no title, opens out of sight and uses fake buttons.**
   - **Off-screen:** `#drill` is appended after the whole view (`_view.html:22`). On a phone, a tapped Category's Transactions render about 340 px below the fold and the page doesn't scroll.
   - **No context:** there is no heading (mark, period, count, sum), no selected state on what was tapped, and no close.
   - **Fake buttons:** the rows are `<tr tabindex=0 hx-get>` with no role, name or `aria-expanded`. Only Enter on `keyup` opens them, and Space scrolls the page.
   - **Inconsistent:** Subcategory rows open a drill-down in Per Member and Money flow, but not in Spending.
   - **Fix:**
     - Make the drill-down a titled panel: a bottom sheet on a phone, a side panel on desktop. Move focus into it and announce it.
     - Use real `<button>`s or links with `aria-expanded`/`aria-controls`.
   - **Lands in:** the Dashboard slice.

7. **The outcome control doesn't say which Category.**
   - Eight catch-alls are all named "Other", and the "Other" Category's catch-all is "Miscellaneous".
   - A closed select shows only the Subcategory, so a Review queue row reading "Other" hides the very thing the driver is deciding.
   - **Fix:** always show "Category › Subcategory". In the picker, offer search and put the Household's most-used outcomes first.
   - **Lands in:** the Transaction-row component.

8. **No HTMX swap moves focus or announces anything.**
   - This covers switching views, stepping the period, filters, the drill-down, row saves and the Review queue count.
   - Across 16 screens there are 0 `aria-live`, `status` or `alert` regions, and `document.title` stays "Dashboard · Pursegraph" for all five views.
   - **Fix:** one `htmx:afterSwap` convention, not per-template patches:
     - focus the new heading;
     - announce through a polite live region;
     - update the title from the partial.
   - **WCAG:** 4.1.3, 2.4.3, 2.4.2.
   - **Lands in:** App shell and navigation (foundation).

9. **Charts rely on colour alone and have no accessible name.**
   - Category trends draws 8 lines told apart only by colour, and the stacked segments in Per Member and Cashflow are the same.
   - ECharts `aria` is off, and the SVG has no name.
   - The palette repeats every 9 Categories (`dashboard.js:15`, `% 9`), so a 10th Category gets the same colour as Food.
   - Animation ignores `prefers-reduced-motion`.
   - On a phone, the Money flow labels collide and the Per Member legend paginates ("1/3").
   - **Mitigation:** every chart has a full data table beside it.
   - **Fix:** direct labels, decals or dashes, stable per-Category colours, and `role="img"` with a summary.
   - **WCAG:** 1.4.1, 1.1.1, and a PRODUCT.md requirement.
   - **Lands in:** Chart styling.

10. **Numbers and dates aren't locale-aware, and they disagree with each other.**
    - The same figure shows as `1187.92` in a table, `€1,188` in the chart beside it (the browser's locale via `toLocaleString(undefined…)`) and `4520.00` in the sidebar. Dates are ISO `2026-10-02`, which wraps to two lines on a phone.
    - There are 36 hand-written `floatformat` and `date:` calls.
    - **Fix:** one money and date formatter on the server (sl-SI `1.234,56 €` once translated), with the chart JSON using the same one.
    - **Lands in:** the foundation slice, before the redesign spreads `floatformat` further.

### P2: minor, workaround exists

| # | Finding | Lands in |
|---|---|---|
| 11 | **Saves are instant, silent and can't be undone.** Reading surfaces (drill-down, Transactions) commit on select change, so a mis-tap on the reader's phone sets a Manual outcome. A failed save (400) is not swapped, so nothing visible happens. Fix: show the outcome as text with "Change" on reading surfaces, an inline "Saved as … · Undo", and an inline error state | Transaction-row component |
| 12 | **The Review queue never ends.** Resolved rows stay in place, and the "Accept all 21" count goes stale. Bulk accept is all or nothing, including 51%-sure guesses, and rows are sorted by date, not confidence. There is no "queue clear" end state. A row lacks context: owner, counterparty, and the last outcome used for the same description. Ambiguous Transfer pairings are buried as an option group in the select | Review queue slice |
| 13 | **Destructive actions run on one click.** Delete Rule, Delete Category or Subcategory (which silently moves its Transactions and Rules to the catch-all), Deactivate or Make admin on Members, and "Re-suggest the Review queue". Statement and Account deletes already confirm, so this is inconsistent | per-screen slices |
| 14 | **Flows don't connect.** The import summary says "N waiting for review" but doesn't link to the Review queue. A gap ("No Statement covers … yet") offers no action. A multi-file import shows no progress. After a bulk accept or Apply Rule, nothing links to the affected Transactions | Import, Review queue slices |
| 15 | **Empty and dead-end states.** The empty Dashboard is one button inside a live nav that leads to more empty pages, and it doesn't say who imports or that Accounts are created at import. A month before any data says "No spending in this period" instead of "no Statements cover this period". Locked out doesn't say that an admin's reset link also clears the lockout | Login, empty and first-run states (fog) |
| 16 | **Import rejection copy is written for the developer.** "Please keep this file: it is needed to fix the parser" shows even for the wrong file, and "Σ rows" and "non-completed row" are jargon. Fix: lead with the cause and the action, with the reconciliation diagnosis behind a disclosure | Import slice |
| 17 | **The IA follows code modules.** Five Dashboard views are siblings of Rules and Members. "Review queue (22)" and Rules sit in the reader's nav as a pending-work count, which is close to a nudge. Suggestion: 3–4 destinations (Dashboard with the views as an in-page switcher, Review queue, Transactions, More), with admin under More | App shell and navigation |
| 18 | **The period control has no clear model.** It is ‹ › arrows, a label, and an unlabelled select of units (Month / Quarter / Year / Last 12 months / Custom). ‹ steps back forever. Default periods differ (Trends uses 12 months, the others last month), and Cash flow opens on a single month, a degenerate view with a lone "Net" dot. The period arrows are 22×24, below the 24 px target | Dashboard slice |
| 19 | **Filters commit in different ways.** Member applies on change. Accounts needs Apply inside a `<details>` that doesn't close on Escape or an outside click and can cover the period controls. The disabled Member select on Per Member explains itself only through a `title`, which can't be reached on touch | Dashboard slice |
| 20 | **The answer isn't first.** Spending lists all about 25 Subcategory rows expanded, about 1,100 px on a phone before the hint. No view leads with the period's headline. Category trends is 13 columns of numbers on a phone | Dashboard slice |
| 21 | **Money flow's "Saved" overclaims.** It is computed as in minus spending (`queries.py:499`), money not spent, which isn't money moved to savings. Fix: rename it ("Left over"), or back it with Transfers to the savings Account | Dashboard slice |
| 22 | **Headings, landmarks and keyboard.** The only `h1` is the brand, and page titles are `h2`. The current item is marked only by `.on`, with no `aria-current`. There's no skip link (13–16 tab stops before content), and the Transactions page has two unlabelled `<nav>`s | App shell and navigation |
| 23 | **Touch targets and fixed sizing.** Every Review queue control is under 44 px (about 28–30). "Make a Rule" and the Edit and Delete links are 17–20 px. The CSS has 162 `px` values and no `rem`, so a browser font-size setting does nothing. Fixed tracks (220/340/420 px, `nowrap`) won't fit Slovenian strings | foundation tokens |
| 24 | **Rules give no feedback before saving.** There is no live "matches N Transactions" preview. "Make a Rule" pre-fills store-specific strings ("HOFER 2201") and doesn't show the source Transaction. The Rules list has no per-Rule effect count | Rules slice |
| 25 | **Transactions is one long page.** It runs 50 rows at about 5,600 px, with no date, Member, Category or amount filter. The Dashboard can't deep-link into it, and the source labels Rule/LLM/IBAN/Manual are unexplained | Transactions slice |
| 26 | **Categories admin is a wall of controls.** About 60 inline Rename, ↑/↓ and Delete controls are visible at once. The last Subcategory's ↓ is enabled, although the catch-all must stay last | admin slice |
| 27 | **The LLM settings use units that don't match.** The threshold is entered as "0 to 1" while the queue says "% sure". The page doesn't show model status, reachability or how many Transactions wait | admin slice |
| 28 | **Theming readiness.** The sidebar uses 8 hard-coded hex values and `#fff` appears 5×. `dashboard.js` holds 18 colour literals read once at init. There's no `color-scheme`, and tokens named `--good`/`--bad` contradict "Describe, don't judge" | Light/dark theme switching, Chart styling |
| 29 | **The full ECharts bundle** is 1.03 MB (334 KB gzipped) for bar, line and sankey. A custom build would be about a third of the size, which matters for the first Dashboard visit over VPN on a phone | Chart styling |

### P3: polish

- Owners show as usernames on Accounts but as names on the Dashboard. Saving an Account shows no confirmation, and Delete is missing on Accounts with Statements without saying why.
- The Coverage bar on Import is empty `<span>`s with a `title`. Give it text for screen readers and touch.
- Members: the current user isn't marked, and the Admin column mixes a state with an action. The invite link page has no Copy button, should give the expiry as a date, and should say "shown only now".
- Empty `<th>` in action and drag-handle columns. Login errors aren't linked to their fields (`aria-invalid`, `aria-describedby`). Hints say "Click…", which reads oddly on touch.
- On desktop, keyboard shortcuts for the Review queue (j/k to move, Enter to accept).

## What's working (keep it)

1. **The numbers are honest by construction.** Awaiting review is a bar, line, segment or Sankey node in every view. Transfers are excluded and the Joint bucket is explicit.
2. **Import works as a trust ritual.**
   - Per-file outcomes use the domain counts.
   - The Coverage timeline names its gaps and uses stripes, not just colour.
   - An unknown IBAN can be attached to an Account during import.
   - Rejections show the reconciliation.
   - Deleting a Statement says how many Transactions and manual outcomes are lost.
3. **Dashboard state lives in the URL, and the drill-down closes the loop.** Correcting an outcome in it refreshes the numbers in place. Every chart has an equivalent, drillable table beside it, which is the strongest accessibility decision in the app.
4. **Progressive enhancement is real.** Forms keep a real `method` and `action`, and `<noscript>` adds Submit buttons. i18n markup is thorough, with `blocktranslate count` plurals. axe found no missing labels or empty buttons. Rule reordering has a keyboard alternative.

## Floor for the new palette (from the detector)

- Secondary text and the accent must reach 4.5:1 in both themes. Today `--muted` #898781 is 3.4:1, and white on #2a78d6 is 4.4:1.
- The page `h1` must be larger than section headings. Today the brand `h1` is 18 px and the page `h2` is 22 px.
- Keep a non-colour cue for Coverage gaps: the stripes were flagged by the detector, but on purpose.

## Open questions for the redesign

1. **Should the Dashboard show how complete each period is, and refuse to draw missing months as zeros?** This adds behaviour (Coverage on the Dashboard), not just look. The map's Notes say behaviour stays.
2. **Should the reader see edit controls?** One option is that reading surfaces show outcomes as text with an explicit "Change", or the drill-down stays read-only for non-admins.
3. **Is the Review queue a list, or one card at a time?** Either way it ends by handing the driver the Dashboard for the period they just completed.
4. **Do five Dashboard views earn five nav slots?** Or is Spending home, with Cash flow, Trends, Per Member and Money flow as lenses on the same period?
5. **Should "this month so far" exist anywhere,** given the numbers are only complete after the weekly import and review?
