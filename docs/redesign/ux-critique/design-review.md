# Assessment A: Design Review (Pursegraph, pre-redesign)

Scope: structure, IA, flows, states, feedback, copy/vocabulary, accessibility semantics, phone layout. Palette, type and visual style are ignored because the redesign replaces them. Already-filed issues #51, #53, #54 and #57 are excluded.

Evidence: source in the worktree (`templates/`, `static/`, `dashboard/`, `ledger/views.py`, `members/views.py`), the provided screenshots, and new Playwright probes against the live demo. New captures are in `scratchpad/shots-a/`. The probes found:
- Phone `scrollWidth`: `/review/` 767, `/transactions/` 767, `/trends/` 984 (the viewport is 390). Spending, Cash flow, Money flow and Per Member fit at 390.
- Phone: `main` starts at y=417 on the dashboard views, so the navigation fills the top half of an 844px screen.
- Desktop: it takes 16 Tab presses to reach the first dashboard control (the period select). There is no skip link.
- Phone: after tapping a Category the page does not move, and the drill-down's top sits at y=1182 in a viewport 844 tall.

---

## Design-specificity verdict (structure and IA, not palette)

**Partly specific, held back by a generic shell.** The data model is unusually well grounded, and you can see it in the UI:
- the Coverage timeline with gaps on Import;
- an "Awaiting review" bucket included in every spending view, so totals are never quietly incomplete;
- the Joint bucket in Per Member;
- Transfers kept out of spending;
- the Money flow Sankey that balances to "Saved / From savings";
- reconciliation diagnostics on a rejected import.

No generic finance template does these, and they carry PRODUCT.md's principle "Trust the numbers".

The **container** is generic. It is a flat 13-item admin sidebar where five dashboard views, a ledger, three weekly-routine tasks, a month summary widget and three admin pages all sit at the same level. Each screen is then "h2, a table, a panel". The two weekly routines (the driver's import-then-review, the reader's "where did it go last month?") are not modelled as flows anywhere. They are destinations the user has to string together alone. The IA mirrors the code's modules (dashboard / ledger / members), not the Household's two jobs. On a phone the shell is worse than generic: it is a wrapped wall of links taking half the screen.

The biggest missed opportunity is that the domain's trust signals stay on the screens where they were produced (Coverage on Import, review state on the Review queue) instead of reaching the screen where trust is spent: the Dashboard.

---

## Nielsen heuristics

| # | Heuristic | Score | Key issue |
|---|-----------|-------|-----------|
| 1 | Visibility of system status | 2 | Saving an outcome gives no feedback, and a failure is silent (a 400 response is not swapped). The drill-down loads off-screen on a phone. The Dashboard never says whether a period is fully covered by Statements. The sidebar "This month" figures don't name the month. |
| 2 | Match system / real world | 2 | Eight catch-alls are all named "Other", plus a Category called "Other", and a closed select shows only "Other". The confidence threshold is "0 to 1" while rows say "76% sure". Copy includes "Σ rows", "non-completed row", "needed to fix the parser". Dates are ISO and amounts are bare `1187.92` instead of sl-SI `1.187,92 €`. |
| 3 | User control and freedom | 2 | No undo anywhere. Rule, Category and Subcategory deletes, and Member deactivate/admin toggles, post with no confirmation. Bulk accept is all or nothing. The drill-down cannot be closed. |
| 4 | Consistency and standards | 2 | At least four commit models: a select that saves on change, Accept, Apply inside a popover, and a Filter button. Subcategory rows open a drill-down in Per Member and Money flow but not in Spending. Owners appear as usernames (`maja`) on Accounts but as names (`Maja`) on the Dashboard. Charts say `€1,188` while the table next to them says `1187.92`. |
| 5 | Error prevention | 2 | Picking a select option commits immediately, with no undo, including in the reader's drill-down. "Accept all 21" includes 51%-sure guesses. A Rule's substring match has no preview before saving. "Make a Rule" pre-fills a store-number-specific string ("HOFER 2201"). |
| 6 | Recognition rather than recall | 2 | The drill-down has no title saying what was clicked or for which period. A Rule made from a Transaction doesn't show that Transaction. A closed "Other" doesn't say which Category it belongs to. |
| 7 | Flexibility and efficiency | 2 | No keyboard flow for the Review queue. Bulk accept can't take a subset. Good: multi-file import, the period and filters carry across views, Rule reordering by drag or ↑↓. |
| 8 | Aesthetic and minimalist design (structural) | 2 | On a phone the nav fills half the viewport. Spending lists every Subcategory expanded (25 rows). The Categories admin is a wall of about 60 Rename/↑/↓/Delete controls. Transactions is one 5,600px page. |
| 9 | Error recognition and recovery | 2 | Import rejections are excellent for the driver (balance diagnosis, mismatch table) but tell a reader to "keep this file to fix the parser" even for a wrong file. "Locked out" is a dead end. The login form has no "ask an admin for a link" path. |
| 10 | Help and documentation | 3 | The inline hints are precise and use the CONTEXT.md terms ("Every condition a Rule sets must hold", "Joint Accounts form their own Joint bucket"). What's missing is help for the reader at the moment of confusion: what "Awaiting review" is, why a month looks low. |
| **Total** | | **21/40** | **Acceptable**: the foundation is sound, but significant flow and state work is needed. |

---

## Cognitive load

The checklist has 5 failures, which counts as **high**.

- **Single focus: fails on a phone.** About 13 nav links and the In/Spent/Net widget come before any content (main starts at y=417).
- **Chunking: fails.** Spending's table shows 7 Categories and 18 Subcategories all expanded. Trends shows 13 columns of numbers on a phone.
- **Grouping: passes, mostly.** The sidebar separators group content, routine and admin.
- **Visual hierarchy: fails.** Every screen has the same weight ("h2, then everything"). Nothing says "this is the answer" (for example the period's total) or "this is the next step" (for example, after an import).
- **One thing at a time: passes in the Review queue** (row by row), **fails in the drill-down**. It opens under the whole view with edit controls in every row, so reading and editing are mixed.
- **Minimal choices: fails.**
  - The phone nav offers 13 options at once.
  - The outcome select has roughly 45 options, including 8 called "Other".
  - Each Review queue row offers select, Accept, the source label and "Make a Rule".
  - The Categories admin shows about 4 controls per Subcategory, all visible at once.
- **Working memory: fails.** The drill-down has no heading, so you must remember what you tapped. Rule form ← "Make a Rule" doesn't show the source Transaction. Sidebar "This month" (October) appears next to a September view.
- **Progressive disclosure: partial.** Accounts and Statements in Import use `<details>` well, but Subcategories, the edit controls and the full ledger are always fully disclosed.

Decision points with more than 4 visible options:
- the phone/desktop nav (13);
- the outcome select (about 45);
- the period-unit select (5) next to ‹ › arrows, the Member filter and the Accounts filter, which together make 4 controls in one bar;
- the Categories admin.

---

## Emotional journey

- **Driver, weekly:** Import gives reassurance at the right moment. The per-file summary (imported, Duplicates skipped, Transfers paired, gaps) is the best "peak" in the product. Then the journey **drops**: the summary says "N Transactions waiting for suggestions or review" but offers no link onward, so the driver has to find the Review queue in the sidebar. The queue is a 22-row table of selects. Accepting a row leaves it in place, and the "Accept all 21" count goes stale. There's no "queue cleared, the numbers for October are now complete" ending. **The peak-end rule is violated: the routine ends on a table, not on a sense of done.**
- **Reader, casual, on a phone:** they open the app and the first thing on screen is a leaked template comment `{# The sidebar. Its links carry… #}`, then half a screen of links. They scroll to "Spending by Category · September 2026". The sidebar says "Spent 2661.37" while the total says 2626.01, and nothing explains the mismatch. That is the worst possible moment for a product whose purpose is "the same numbers instead of arguing about them". They tap "Food" and nothing visibly happens (the drill-down is 340px below the fold).
- **High-stakes moments with no reassurance:**
  - deleting a Subcategory, which silently moves its Transactions to the catch-all;
  - "Accept all";
  - deactivating a Member;
  - "Re-suggest the Review queue".

  None of these confirms or reports what changed, except bulk accept, which reports "N suggestions accepted".

---

## Strengths

1. **Honest numbers by construction.** Unresolved money is never hidden: "Awaiting review" is a bar, a line, a segment and a Sankey node in every view (`dashboard/queries.py:5`, `:224`, `:333`). Transfers are excluded and the Joint bucket is explicit. This is the hardest part to get right, and it is right.
2. **Import as a trust ritual.**
   - Per-file outcomes use precise domain counts (`templates/ledger/import.html:13-25`).
   - The Coverage timeline marks the gap ("Gap 1 Jul 2026 – 31 Jul 2026").
   - The "Choose the Account" step lets an unknown IBAN be attached during import.
   - Rejections show the opening/rows/closing reconciliation and a per-day mismatch.
   - Delete-Statement confirmation says how many Transactions go and how many manual outcomes are lost (`delete_statement.html:9-14`).
3. **Dashboard state lives in the URL, and drill-down closes the loop.** Period and filters carry across views via `hx-push-url`. Each view pairs its chart with an equivalent, keyboard-focusable table (`tabindex="0"`, Enter). Correcting an outcome in the drill-down refetches the numbers in place (`static/dashboard.js:130-136`). Reading leads to fixing, which leads to the updated picture, with no page change.

---

## Per-screen findings

### Global shell / navigation

**[P1] A template comment leaks onto every page.**
- `templates/_sidebar.html:1-2` uses a two-line `{# … #}`, and Django's `{# #}` only spans one line. So "{# The sidebar. Its links carry the dashboard's period and filters… #}" is the first text every user sees, on every screen, and it takes the top 100px on a phone.
- Fix: switch to `{% comment %}`.
- For the redesign: add a test that renders the shell and asserts no `{#` appears in the output.

**[P1] The phone nav takes half the screen and has no hierarchy.**
- At ≤900px the sidebar becomes a wrapped row of 13 links plus the figures and Log out (`static/pursegraph.css:32-38`). `main` starts at y=417 of 844.
- Fix: split the IA by job.
  - A bottom bar or top tabs with 3–4 destinations: **Dashboard** (with the 5 views as an in-page view switcher), **Review queue (n)**, **Transactions**, **More**.
  - "More" holds Import, Rules and the admin pages.
  - The five views should be a segmented control in the Dashboard's header, not siblings of Rules and Members in the global nav.

**[P1] The sidebar "This month" figures contradict the Dashboard.**
- The sidebar always shows the current month so far (`dashboard/queries.py:556-567`), labelled only "This month". The Dashboard defaults to the last complete month (`dashboard/periods.py:70-73`).
- On the default landing, the reader sees "Spent 2661.37" (October) next to "Total 2626.01" (September). The October figure is also 81% "Awaiting review" (2148.19 of 2661.37), which the sidebar doesn't say.
- Fix: drop the global figures widget, or name the month ("October so far") and show the unreviewed share.
- Better: make the Dashboard's own header carry the period's headline (spent, in, net, and coverage/review completeness). The sidebar shouldn't hold a second, competing truth.

**[P2] No skip link, and 15 tab stops before content.**
- An `<h1>` "Pursegraph" in the sidebar is the only h1. The page title is an h2.
- Fix: add a skip link, put the page h1 in `main`, and keep the brand outside the heading outline.

**[P2] Number and date locale.**
- Tables use `floatformat:2` with no currency or grouping (`1187.92`). Charts use `toLocaleString(undefined, …)`, which gives `€1,188` in an en browser (`static/dashboard.js:7`). Rows use ISO `2026-10-02`, which wraps to two lines on a phone. The `j M Y` format is used elsewhere.
- PRODUCT.md asks for sl-SI conventions.
- Fix: one server-side money and date formatter, also used by the chart JSON, so a figure reads identically in chart, table, sidebar and drill-down.

### Dashboard (all views)

**[P1] Coverage gaps are invisible on the Dashboard.**
- Luka's N26 has no Statement for July 2026. Category trends shows Food dropping to 659.32 in July (against about 900 in other months) and Leisure at 0.00 in July. A reader will conclude "we spent less on food in July". The real cause is missing data.
- Months before any Statement (Nov 2025–Mar 2026) are drawn as genuine 0.00 points and rows.
- Nothing in `dashboard/` references Coverage. `grep -i "gap\|coverage" dashboard/queries.py` finds nothing.
- Fix:
  - The view header states completeness for the period ("All 3 Accounts covered" / "Luka's N26 has no Statement for 1–31 Jul").
  - Trends and Cash flow mark uncovered months (hatched or broken line, "no data", not 0).
  - Periods before the first Statement are not offered or are labelled as such.
  - This is PRODUCT principle 2 and the single most important structural addition.

**[P1] The drill-down has no title and loads out of sight on a phone.**
- `#drill` is appended after the whole view (`templates/dashboard/_view.html:22`). On a phone, tapping a Category at y≈790 renders the Transactions at y≈1520+, and the page doesn't scroll.
- There is no heading ("Home · September 2026 · 4 Transactions · 1,187.92"), no selected state on the tapped row or bar, and no close.
- Fix:
  - Make the drill-down a titled panel: a bottom sheet on a phone, a side panel on desktop.
  - Show the mark, period, filter, count and sum, with a close control.
  - Move focus into it and announce it (`aria-live` or focus the heading).
  - Mark the source row as selected (`aria-current` or a pressed state).

**[P1] The drill-down and the Transactions list overflow horizontally on a phone.**
- The row template is a 5-column table with an inline select, Accept, the source and "Make a Rule" (`templates/ledger/_transaction_row.html`). Phone width becomes about 707–767px.
- Fix: a stacked row layout on narrow screens. Line 1 is the description and amount. Line 2 is the date, Account and outcome chip. Tapping the outcome opens the editor.
- One component should serve the Review queue, Transactions and the drill-down.

**[P2] Reading surfaces commit edits instantly.**
- The drill-down and Transactions rows save on select `change` (`_transaction_row.html:8`). For the reader scrolling on a phone, a mis-tapped select permanently re-categorizes a Transaction as "Manual", with no confirmation and no undo. The only feedback is the source label changing.
- Fix:
  - On reading surfaces, show the outcome as text with an explicit "Change" action.
  - After a change, show an inline "Saved as Groceries · Undo" for a few seconds.
  - Show an inline error state when the POST fails. Today a 400 from `transaction_outcome` (`ledger/views.py:300-306`) is simply not swapped, so nothing happens.

**[P2] Default periods disagree between views, and Cash flow defaults to a degenerate view.**
- Spending, Cash flow, Per Member and Money flow open on last month. Trends opens on the last 12 months (`dashboard/views.py:32-36`).
- Cash flow with a single month draws one pair of bars and a meaningless lone "Net" dot (`shots/desktop-dashboard-cashflow.png`). Cash flow exists to compare months.
- Fix: give Cash flow a multi-month default like Trends. Then state each view's period prominently in the header, as a range, so switching views never silently changes the timeframe.

**[P2] The period control is three controls with no clear model.**
- There are ‹ ›, a label, and an unlabelled select whose options are units ("Month / Quarter / Year / Last 12 months / Custom range"). It reads like a value but changes the granularity.
- ‹ steps back forever, into months before any data, where the only message is "No spending in this period." (`shots-a/phone-spending-jan-empty.png`).
- Fix: a single period picker (unit tabs plus stepper) with a visible label, ‹ disabled before the first Coverage date, and an empty message that distinguishes "no Statements cover this period" from "nothing spent".

**[P2] Filters have inconsistent commit models.**
- The Member filter applies on change. The Accounts filter needs Apply inside a `<details>` popover (`templates/dashboard/_filters.html:2,14-21`). The popover has no close/Escape handling beyond `<details>`.
- On Per Member, the disabled Member select explains itself only via `title`, which can't be reached on touch.
- Fix: one filter sheet with one apply behaviour, plus an always-visible summary chip ("Maja · 2 Accounts · ✕").

**[P2] Spending and Trends are always fully expanded and don't show the answer first.**
- Spending lists all Subcategories expanded. On a phone that's about 1,100px of table before the hint.
- Fix:
  - Lead with the headline (period total, and the change from the previous period, described neutrally).
  - Then Categories, collapsed, with Subcategories on expand.
  - Make Subcategory rows clickable in Spending as they are in Per Member and Money flow (inconsistent today: `_spending.html:14` vs `_per_member.html:13`).

**[P2] Category trends is unreadable on a phone and the current month is misleading.**
- Phone `scrollWidth` is 984. The `.stack` grid lacks `minmax(0,1fr)`, so the 13-column `.scroll` table forces the page wide. It's the same for Cash flow's `.split.wide` at narrow widths.
- The running month (October) is plotted as a regular point, so Home falls to 0 and Awaiting review jumps to 2,148, which looks like a crash.
- Fix: on a phone show one Category's trend at a time (select a Category, then a 12-month sparkline and a list), and mark the partial month as partial (open point or dashed segment, "so far").

**[P2] Money flow labels collide and "Saved" overclaims.**
- On a phone, the "Salary €4,520" and "Household €4,520" labels overlap (`shots/phone-dashboard-money-flow.png`).
- "Saved" is computed as in + others − spending (`dashboard/queries.py:499-500`). That is money not spent, not money moved to savings.
- Fix: rename it (e.g. "Not spent" / "Left over") or show it only when it is backed by Transfers to the "Other" savings Account. On a phone, move labels outside or use a vertical Sankey.

**[P2] Charts rely on colour for identity.**
- Per Member's stacked segments and Trends' 8 lines are told apart only by colour. On a phone the Per Member legend paginates ("1/3"), so most Categories have no visible key.
- ECharts `aria` isn't enabled, so the SVG has no text alternative (the adjacent table mitigates this).
- Fix: direct labels on segments and line ends, highlight one Category at a time, and enable `aria`. PRODUCT.md requires charts not to rely on colour alone.

**[P3] Per Member hint copy.** "Joint Accounts form their own Joint bucket" is accurate but abstract for the reader. Something like "Joint: spending from Accounts you share" would be clearer.

### Empty dashboard (`templates/dashboard/empty.html`)

**[P2] It is a dead end that doesn't teach the routine.**
- The page says "There is nothing to show yet." with one button. The full sidebar (5 views, "This month 0.00", Review queue (0), Rules) stays live around it, and every one of those leads to more empties.
- For a reader on a fresh install it doesn't say who should import, or that Accounts are created during import.
- Fix: a first-run panel showing the 3 steps (import Statements, review, read the Dashboard), with the views hidden or disabled until data exists. For a non-admin it should also say "Ask <admin> to import, or import a Statement yourself".

### Review queue

**[P1] It is not usable on a phone, although PRODUCT.md requires it to be.**
- Phone `scrollWidth` is 767 on a 390 viewport. Descriptions wrap to 9 lines (`shots/phone-review-queue.png`).
- Fix: a card per Transaction. Show the description and amount large, the date, Account and Member small, and the suggested outcome as a large chip showing **Category › Subcategory**. Primary "Accept" sits in the thumb zone and "Change" opens a searchable sheet. After acting, the card collapses away and the next one takes its place.

**[P1] The outcome control is ambiguous.**
- Each Category's catch-all is named "Other" (8 of them), and there is also a Category "Other" with catch-all "Miscellaneous" (`shots/desktop-categories.png`). A closed `<select>` shows only the Subcategory name (`_transaction_row.html:17`).
- So "Other" or "Miscellaneous" in a row doesn't say which Category, and that's exactly what the driver is deciding.
- Fix: always render the outcome as "Category › Subcategory". In the picker, offer search and the Household's most-used outcomes first.

**[P2] Resolved rows stay in place and the bulk count goes stale.**
- Accepting or changing a row swaps it for its resolved version, so it stays in the queue (`hx-target="closest tr"`, `_transaction_row.html:8`). "Accept all 21 suggestions" keeps its server-rendered count. Only the sidebar count updates (`:44`).
- Fix: remove a resolved row with a short "Groceries · Undo" toast, update the bulk control live, and show an end state ("Queue clear. October's numbers are complete." with a link to the Dashboard for the affected period).

**[P2] Bulk accept is all or nothing, with no view of confidence.**
- "Accept all 21" includes suggestions at 51–59%. Rows are sorted by date, not by confidence, and no subset can be selected.
- Fix: group the queue into "Confident (≥80%)", "Check these", and "No suggestion / pick the other side". Bulk accept applies per group, and each row has a checkbox, checked by default in the confident group. Ambiguous Transfer pairings deserve their own explanatory card ("Which Transaction is the other side?"), not an option group buried in a select (`_transaction_row.html:21-27`).

**[P2] The row gives too little context to decide.**
- There's no Member or owner, no counterparty IBAN, and no "you categorized similar Transactions as X before".
- Fix: show the Account owner and counterparty, and the last outcome used for the same description, in the card.

**[P3] Driver efficiency.** Add keyboard shortcuts on desktop (j/k to move, Enter to accept, / to change) and keep focus on the next row after acting.

### Transactions

**[P2] One long page, no date or amount filter, phone overflow.**
- 50 rows per page at about 5,600px. Filters are search, Account and outcome only, applied with a Filter button. There's no date range, Member, Category roll-up or amount filter. Phone width is 767.
- Fix: a sticky filter summary, date/period and Category filters (sharing the Dashboard's period model, so the Dashboard can deep-link into it), month group headers, and the same stacked rows as the Review queue.

**[P3] The source labels "Rule", "LLM", "IBAN" and "Manual" are unexplained.** Make them a tappable chip that says why ("Categorized by Rule 'spar'" with a link to the Rule).

### Import / Accounts / Coverage

**[P2] Import ends without a next step.**
- The summary lists "N Transactions waiting for suggestions or review" (`import.html:21`) but offers no link. "No Statement covers … yet" is shown with no action.
- Fix: end each import result with a primary "Review N Transactions", and give a gap a "Import a Statement for 1–31 Jul" affordance.
- Show an upload-in-progress state for multi-file PDF imports. Today it is a plain form POST with no indicator.

**[P2] The rejection copy assumes the driver.**
- "Please keep this file: it is needed to fix the parser." is shown even for an obviously wrong file (`shots/desktop-import-rejected.png`). That is developer-facing for a reader who occasionally imports.
- Fix: two tiers.
  - Lead with the user-level cause and action ("This isn't a Sparkasse, N26 or Revolut Statement we can read. Check you picked the Statement PDF/CSV.").
  - Put the diagnosis (balances, Σ rows, mismatch) behind a disclosure for the admin.
- "Σ rows" and "non-completed row" need plain words.

**[P3] Accounts list.**
- Owners appear as usernames (`maja, luka`) where the Dashboard uses Member names.
- Saving an Account gives no confirmation message (`ledger/views.py:172-174` redirects silently).
- "Delete" appears only for Accounts with no Statements, without explaining why it is missing on the others.

**[P3] The Coverage bar on Import is visual only.** It is a `role="list"` of empty spans with a `title`. The legend text carries the gap, which is good, but the timeline itself gives nothing to screen readers or touch users. Add per-segment text, or an `aria-label` on the list.

### Rules (+ rule form, apply rule)

**[P2] No match preview before saving, and weak pre-fill.**
- The form gives no live "matches N Transactions (examples…)". The count appears only after saving, on Apply Rule.
- "Make a Rule" pre-fills the full description, including store numbers ("HOFER 2201"), which matches one branch only. The form doesn't show which Transaction it came from, and Cancel goes to Rules rather than back.
- Fix: a live preview list under the conditions, a pre-fill that suggests the stable token ("HOFER"), the source Transaction shown at the top, and a return to the origin.

**[P2] Delete Rule has no confirmation, no message and no undo** (`rules.html:28-30`, `ledger/views.py:522-524`). Rules are hand-tuned, so add an undo toast.

**[P3] The Rules list doesn't show each Rule's effect.** There's no count of Transactions it categorized and no "last matched". That would show which Rules are dead or too greedy (`spar` is a short substring).

**[P3] Apply Rule copy.** "outcomes set by hand, by IBAN, by pairing or by the parser stay" is accurate but dense. A per-source breakdown would be clearer ("12 will change; 3 set by hand stay").

### Login / locked out / set password / invite link

**[P2] Locked out is a dead end.**
- `registration/locked_out.html` says only "Try again in an hour." Yet a password-reset link from an admin also clears the lockout (`members/views.py`, `reset(username=…)` in `SetPasswordView.form_valid`).
- Fix: say so ("Or ask an admin for a password-reset link"). The login form should offer the same "Forgot your password? Ask an admin for a link" line, since there's no email.

**[P3] Invite / reset link page.** The link sits in a readonly input with select-on-focus. Add a Copy button, and show the expiry as a date ("valid until 23 Oct"), which is easier to pass on in person than "7 days".

### Admin: Categories

**[P2] The page is a wall of controls with unconfirmed destructive actions.**
- About 60 inline Rename forms, ↑/↓ pairs and Delete buttons are all visible at once (`categories.html`).
- Deleting a Subcategory moves all its Transactions and Rules to the catch-all immediately, with no confirmation and no count (`ledger/categories.py:67-73`).
- The ↓ on the last movable Subcategory is enabled even though the catch-all must stay last (`categories.html:38`, no `disabled`).
- Fix: a list with per-item edit mode, a delete confirmation that names the impact ("14 Transactions and 1 Rule move to Home › Other"), and drag or ↑↓ limited to valid positions.

**[P2] Catch-all naming.** The defaults ("Other" × 8 plus a Category "Other") are themselves an IA problem that feeds the Review queue ambiguity above. Use "Other Food" style names, or always display the parent.

### Admin: LLM suggestions

**[P2] Threshold units and status.**
- The threshold is entered as "0 to 1" (`ledger/forms.py:300-307`) while the queue shows "% sure". The page doesn't show the model, whether the LLM is reachable, or how many Transactions are waiting for a suggestion. The sidebar's "Suggestions unavailable" only appears on failure.
- "Re-suggest the Review queue" clears suggestions without confirmation.
- Fix: a percentage input, plus a status block (model, reachable, queue state). Ideally also a preview: "At 80%, 9 of the 21 current suggestions would have been accepted automatically".

### Admin: Members

**[P3] Unconfirmed toggles and an unclear table.**
- Deactivate, Make admin and Remove admin are one-click posts with no confirmation or success message. The last-admin guard exists, which is good.
- The current user isn't marked ("you").
- The Admin column mixes a state word and an action ("Admin  Remove admin" vs a bare "Make admin").
- Fix: state columns plus a per-row actions menu, and a confirmation for deactivation that says the Member's sessions end.

---

## Persona red flags

**Alex (power user, here the driver on desktop)**
- No keyboard path through the Review queue. Every row needs a mouse on a select plus Accept.
- Bulk accept is all or nothing. There's no "accept the ones I trust".
- The Rule form has no match preview, so it's trial and error via the Apply Rule page.
- Transactions has no date filter and no deep-link from a Dashboard mark (the drill-down is a fragment with no URL of its own).
- Good: multi-file import, period and filters carried in the URL, drag or ↑↓ Rule order.

**Sam (screen reader / keyboard)**
- No skip link: 15 sidebar stops before the first dashboard control.
- Clickable `<tr tabindex=0 hx-get>` rows are announced as table rows, not as buttons or links, and nothing says that pressing Enter opens Transactions.
- The drill-down and outcome saves have no live region. Focus doesn't move into the drill-down, and a failed save is silent.
- Charts have no text alternative (ECharts `aria` is off), and series are distinguished by colour only. The tables mitigate this.
- The Coverage timeline is empty spans with `title` only.
- The disabled Member filter explains itself only via `title`.

**Casey (distracted phone user, here the reader)**
- The first screen is a leaked code comment and a wall of links. Content starts mid-screen.
- Tapping a Category appears to do nothing (the drill-down renders about 340px below the fold).
- The Review queue, Transactions and Trends scroll sideways (767–984px wide).
- Selects in the drill-down commit on change, so a mis-tap while scrolling re-categorizes data.
- Two different "Spent" figures sit on the landing screen.

**Project persona: "Luka", the less technical reader** (from PRODUCT.md: reads the Dashboard on a phone, occasionally imports)
- **Profile:** a Member, not an admin. He wants "where did our money go last month?" in under a minute and doesn't know how the data got there.
- **Behaviours:** opens the default view, scrolls, taps the biggest bar, compares with the month before. Rarely changes filters. Imports a Statement maybe once a month.
- **Red flags:**
  1. July Food looks about 25% lower than usual, and nothing says his own N26 Statement for July is missing. He draws the wrong conclusion. This is exactly the argument the product exists to prevent.
  2. October shows "Awaiting review 2,148", the biggest bar, with no explanation of what it means or that Maja's queue will resolve it.
  3. His nav shows "Review queue (22)" and "Rules", driver tasks that read as a pending-work count aimed at him. That's close to a nudge, which PRODUCT.md rules out.
  4. If he imports the wrong file, he is told to keep it "to fix the parser".
  5. Saved/"From savings" in Money flow reads as a claim about his savings Account.

---

## Minor observations

- The Spending chart label shows rounded `€1,188` and the table shows `1187.92` side by side. Pick one precision per surface.
- `Period.default` is "last complete month", which is a good choice for the reader. But the header never says why it opened on September; "Last full month" as a label would help.
- The Cash flow "To/from other Members" column only appears under a Member filter. The header should explain it when it appears.
- "Accept 1 suggestion" vs "Accept all N suggestions": the singular has no "all", which is fine. But the form carries hidden IDs captured at render time, so it is also stale after per-row actions. The server-side "decided since" guard handles that safely.
- After a bulk accept or an Apply Rule, the success message doesn't link to the affected Transactions.
- `members/link.html` "Back to Members" is the only way out after creating a Member, and leaving loses the link (it is shown only once). Say so: "This link is shown only now".
- "Statement files:" label plus the native file input. Drag-and-drop of several files on desktop would suit the weekly batch.
- The login page has no product framing, which is fine for a private LAN app. But on the phone keyboard, check `autocomplete="username"` / `current-password` (Django's form provides these) and add `autocapitalize="none"`.

## Provocative questions

1. Should the Dashboard refuse to show a number it can't fully back up? For example, a period with a Coverage gap or a big Awaiting-review share could render as "partial" first and numbers second.
2. Is the Review queue a list at all, or a one-card-at-a-time flow that ends by handing the driver the Dashboard for the month they just completed?
3. Should the reader ever see edit controls? If the drill-down were read-only for non-admins (with "Suggest a correction"), would the product feel safer to hand to Luka?
4. Do the five Dashboard views earn five nav slots? Could Spending be the home view, with Cash flow, Trends, Per Member and Money flow as different lenses on the same period inside it?
5. Should "This month so far" exist anywhere, given the routine produces complete numbers only after the weekly import and review? Or should the product only ever talk about weeks or months that are reviewed?
