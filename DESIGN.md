---
name: Pursegraph
description: The whole Household's money in one private picture, as a polished personal-finance dashboard.
colors:
  accent: "#4f46e5"
  accent-text: "#4338ca"
  accent-soft: "#eef2ff"
  accent-ink: "#ffffff"
  focus: "#6366f1"
  mark-segment: "#c7d2fe"
  ground: "#f4f5f7"
  card: "#ffffff"
  raised: "#f9fafb"
  hover: "#f3f4f6"
  ink: "#111827"
  ink-2: "#374151"
  muted: "#6b7280"
  faint: "#9ca3af"
  line: "#e5e7eb"
  line-strong: "#d1d5db"
  awaiting: "#9ca3af"
  cat-0: "#4e79a7"
  cat-1: "#59a14f"
  cat-2: "#f28e2b"
  cat-3: "#b07aa1"
  cat-4: "#76b7b2"
  cat-5: "#edc948"
  cat-6: "#ff9da7"
  cat-7: "#9c755f"
  cat-8: "#e15759"
  cat-9: "#a0cbe8"
  accent-dark: "#5850ec"
  accent-text-dark: "#a5b4fc"
  accent-soft-dark: "#1e1b4b"
  focus-dark: "#818cf8"
  ground-dark: "#0e1014"
  card-dark: "#171a20"
  raised-dark: "#1d2128"
  hover-dark: "#222731"
  ink-dark: "#f3f4f6"
  ink-2-dark: "#d1d5db"
  muted-dark: "#9ca3af"
  faint-dark: "#6b7280"
  line-dark: "#262b34"
  line-strong-dark: "#343a46"
  awaiting-dark: "#6b7280"
  cat-0-dark: "#6b9bd1"
  cat-1-dark: "#6cc05f"
  cat-2-dark: "#f5a04d"
  cat-3-dark: "#c697b8"
  cat-4-dark: "#8fd0ca"
  cat-5-dark: "#f1d45e"
  cat-6-dark: "#ffb3bb"
  cat-7-dark: "#b8917a"
  cat-8-dark: "#ef7a7b"
  cat-9-dark: "#b5d6ef"
typography:
  display:
    fontFamily: "Inter, system-ui, -apple-system, Segoe UI, sans-serif"
    fontSize: "28px"
    fontWeight: 600
    lineHeight: 1.5
    letterSpacing: "-0.02em"
    fontFeature: "\"tnum\", \"cv11\", \"ss01\""
  headline:
    fontFamily: "Inter, system-ui, -apple-system, Segoe UI, sans-serif"
    fontSize: "24px"
    fontWeight: 600
    lineHeight: 1.5
    letterSpacing: "-0.01em"
    fontFeature: "\"cv11\", \"ss01\""
  title:
    fontFamily: "Inter, system-ui, -apple-system, Segoe UI, sans-serif"
    fontSize: "15px"
    fontWeight: 600
    lineHeight: 1.5
    letterSpacing: "-0.01em"
    fontFeature: "\"cv11\", \"ss01\""
  body:
    fontFamily: "Inter, system-ui, -apple-system, Segoe UI, sans-serif"
    fontSize: "14px"
    fontWeight: 400
    lineHeight: 1.5
    letterSpacing: "normal"
    fontFeature: "\"cv11\", \"ss01\""
  body-sm:
    fontFamily: "Inter, system-ui, -apple-system, Segoe UI, sans-serif"
    fontSize: "13px"
    fontWeight: 400
    lineHeight: 1.5
    letterSpacing: "normal"
    fontFeature: "\"cv11\", \"ss01\""
  label:
    fontFamily: "Inter, system-ui, -apple-system, Segoe UI, sans-serif"
    fontSize: "12px"
    fontWeight: 500
    lineHeight: 1.5
    letterSpacing: "normal"
    fontFeature: "\"cv11\", \"ss01\""
  wordmark:
    fontFamily: "Inter, system-ui, -apple-system, Segoe UI, sans-serif"
    fontSize: "17px"
    fontWeight: 700
    lineHeight: 1.5
    letterSpacing: "-0.02em"
rounded:
  inner: "6px"
  ctl: "8px"
  row: "10px"
  card: "14px"
  pill: "999px"
spacing:
  s-1: "4px"
  s-2: "8px"
  s-3: "12px"
  s-4: "16px"
  s-5: "20px"
  s-6: "24px"
  s-8: "32px"
components:
  button:
    backgroundColor: "{colors.card}"
    textColor: "{colors.ink}"
    typography: "{typography.body}"
    rounded: "{rounded.ctl}"
    padding: "0 12px"
    height: "36px"
  button-hover:
    backgroundColor: "{colors.hover}"
  button-ghost:
    backgroundColor: "transparent"
    textColor: "{colors.muted}"
    rounded: "{rounded.ctl}"
    height: "36px"
  button-ghost-hover:
    backgroundColor: "{colors.hover}"
    textColor: "{colors.ink}"
  card:
    backgroundColor: "{colors.card}"
    rounded: "{rounded.card}"
    padding: "20px"
  nav-item:
    backgroundColor: "transparent"
    textColor: "{colors.ink-2}"
    rounded: "{rounded.ctl}"
    padding: "7px 8px"
  nav-item-hover:
    backgroundColor: "{colors.hover}"
    textColor: "{colors.ink}"
  nav-item-active:
    backgroundColor: "{colors.accent-soft}"
    textColor: "{colors.accent-text}"
  count-badge:
    backgroundColor: "{colors.accent}"
    textColor: "{colors.accent-ink}"
    typography: "{typography.label}"
    rounded: "{rounded.pill}"
    padding: "0 7px"
    height: "20px"
  category-row:
    backgroundColor: "transparent"
    textColor: "{colors.ink}"
    rounded: "{rounded.row}"
    padding: "10px 12px"
  category-row-hover:
    backgroundColor: "{colors.hover}"
  category-row-open:
    backgroundColor: "{colors.accent-soft}"
  account-pill:
    backgroundColor: "{colors.raised}"
    textColor: "{colors.ink-2}"
    typography: "{typography.label}"
    rounded: "{rounded.pill}"
    padding: "2px 8px"
  view-tab:
    backgroundColor: "transparent"
    textColor: "{colors.muted}"
    typography: "{typography.body}"
    padding: "8px 0 10px"
  view-tab-active:
    textColor: "{colors.accent-text}"
    borderColor: "{colors.accent}"
  tab-bar-item:
    textColor: "{colors.muted}"
    typography: "{typography.label}"
  tab-bar-item-active:
    textColor: "{colors.accent-text}"
  outcome-chip:
    backgroundColor: "{colors.card}"
    textColor: "{colors.ink-2}"
    typography: "{typography.body}"
    rounded: "{rounded.pill}"
    padding: "0 12px"
    height: "36px"
  outcome-chip-hover:
    backgroundColor: "{colors.hover}"
    textColor: "{colors.ink}"
  outcome-chip-current:
    backgroundColor: "{colors.accent-soft}"
    textColor: "{colors.accent-text}"
    borderColor: "{colors.accent}"
---

# Design System: Pursegraph

## Overview

**Creative North Star: "The Household Ledger, Done Straight"**

Pursegraph deliberately looks like a polished personal-finance dashboard: a light sidebar, white cards on a cool grey ground, stat tiles, a Category donut and a single indigo accent. Monarch Money's craft is the bar. The convention is the point, because familiarity serves the least technical Member reading the Dashboard on a phone. Nothing quirky is smuggled in. Distinction comes from execution: exact figures, steady Category hues, quiet type and soft lift.

The density is calm, not terminal-like. A view shows a few large figures, one chart and one ranked list, and detail opens on request (drill-down) rather than up front. Copy and colour describe and never judge. A comparison reads "523,55 € less than September" in muted grey, with no red or green verdict. Dark mode is the same world at night: a near-black ground, raised graphite cards, and the same Category hues lifted in lightness so they keep their identity.

The real app is server-rendered Django templates with HTMX, hand-written CSS custom properties and no build step. ECharts draws the charts. Every asset is self-hosted, including Inter as an OFL variable woff2 under `static/fonts/`, because the app runs offline from the internet on the LAN or a VPN.

**Key Characteristics:**
- Cool grey ground, white 14px cards with soft ambient shadow, one indigo accent used only for chrome.
- Inter throughout, with tabular figures on every amount, and sl-SI number formatting ("1.234,56 €").
- Ten Category hues (Tableau-10-derived), keyed by Category id and identical in every view, with a lifted set for dark.
- Charts that never rely on colour alone: directly labelled donut segments, and a hatch for Awaiting review.
- 1.5px stroke icons, sentence-case labels, no uppercase tracking.
- Light, System and Dark themes, with the system as the default.

## Colors

A neutral cool-grey interface carrying one indigo accent for chrome, plus a separate ten-hue Category palette that is the only colour data ever wears.

### Primary
- **Household Indigo** (accent; accent-dark in dark): the single interface accent. It fills the Review queue count badge, the mark's tile, and (as Indigo Ink) the active navigation, links and the "graph" half of the wordmark. Dark mode lifts it slightly so white text still clears AA.
- **Indigo Ink** (accent-text / accent-text-dark): accent text on light surfaces, such as the active nav item, links, the avatar initial and the wordmark's "graph". In dark it becomes a pale periwinkle.
- **Indigo Wash** (accent-soft / accent-soft-dark): the selected-state ground for the active nav item, the open Category row and the avatar. (The active view tab is an Indigo Ink label over a 2px Household Indigo underline, not a wash.)
- **Focus Indigo** (focus / focus-dark): the 2px focus ring only.
- **Mark Periwinkle** (mark-segment): the smaller segment of the donut mark. It is used in the mark only.

### Neutral
- **Cool Ground** (ground / ground-dark): the page background behind cards. It is also the track of bar meters and of the theme switch.
- **Card White / Graphite** (card / card-dark): cards, the sidebar, controls and tooltips.
- **Raised** (raised / raised-dark): Transaction-row hover and the Account pill fill.
- **Hover** (hover / hover-dark): the hover ground for nav items, buttons and Category rows.
- **Ink** (ink / ink-dark): headings, figures and primary text.
- **Ink 2** (ink-2 / ink-2-dark): nav labels, Subcategory rows, donut labels and secondary body text.
- **Muted** (muted / muted-dark): labels, meta text, comparisons, table headers and control icons.
- **Faint** (faint / faint-dark): disclosure chevrons only.
- **Line / Line Strong**: hairline dividers (line), and control borders, label lines and dimmed donut segments (line-strong).

### Category palette
- **cat-0 … cat-9** (and their `-dark` counterparts): ten Tableau-10-derived hues. A Category's hue is `cat-((id − 1) mod 10)`, so it is fixed by its Category id, never by its rank or the view it appears in. It colours the donut segment, the row dot, the share bar and the drill-down dot.
- **Awaiting Grey** (awaiting / awaiting-dark): the neutral fill for Transactions in the Review queue. It is always paired with a 45° hatch.

### Named Rules
**The One Indigo Rule.** Indigo belongs to the interface: active state, count badge, links, focus, the wordmark and the mark. It is never a data colour, never a chart series and never a Category.

**The Fixed Hue Rule.** A Category wears the same hue in every view, chart and theme step (lifted in dark, never re-assigned). Hues are keyed by Category id, never by sort order.

**The Neutral Wait Rule.** Awaiting review is neutral grey plus a 45° hatch, everywhere it appears (dot, bar and donut segment). It never borrows a Category hue.

**The No Verdict Rule.** No red/green good/bad colouring. Comparisons are muted text that describes the difference, and Net is plain ink with its sign. A Category hue that happens to be red or green (cat-8, cat-1) carries no meaning beyond its Category.

## Typography

**Display Font:** Inter (with system-ui, -apple-system, Segoe UI, sans-serif)
**Body Font:** Inter (same stack)

**Character:** One neutral, highly legible grotesque does every job, with weight and size alone setting hierarchy. The `cv11` (single-storey a) and `ss01` (open digits) features are on globally, and every figure is set in tabular numerals so columns of amounts align. Production self-hosts Inter as a variable woff2 under `static/fonts/` (OFL). The prototype's Google Fonts link is for the prototype only.

### Hierarchy
- **Display** (600, 28px, −0.02em): stat-tile figures (Spent, Money in, Net). It drops to 15px on phones so three tiles fit one row.
- **Headline** (600, 24px, −0.01em): the view title, and the donut's centre figure (at −0.02em). On phones they are 20px and 17px.
- **Title** (600, 15px): card titles ("Share by Category", "Categories", the drill-down title).
- **Body** (400 or 500, 14px, 1.5): Category names (500), Transaction descriptions (500), controls (500), nav items (500) and amounts (600).
- **Body small** (400, 13px): card meta, comparisons, shares, Subcategory rows, the donut centre's caption and the drill-down footnote.
- **Label** (500, 12px): nav group headings, table headers, the count badge (600) and the Account pill. It is sentence case and never uppercased or tracked.
- **Wordmark** (700, 17px, −0.02em): "Purse" in ink and "graph" at 600 in Indigo Ink, set beside the mark (16px in the phone brand row).

### Named Rules
**The Tabular Figures Rule.** Every amount, share, count and date figure uses `font-variant-numeric: tabular-nums`.

**The Locale Figure Rule.** Amounts format with `Intl.NumberFormat('sl-SI', { style: 'currency', currency: 'EUR', useGrouping: 'always' })`, giving "1.234,56 €". Shares are whole percent with a space ("26 %"). Net carries an explicit sign.

## Layout

The desktop layout is a two-column shell: a sticky, full-height white sidebar (232px, with a right hairline), then the page. The main column is padded 24px top and 32px sides, up to 1360px wide.

**Page header.** Every page opens with a title row: the page title (Headline) on the left and the page's one primary action, if any, on the right ("New Rule", "Accept 5 suggestions"). The Dashboard's title is "Dashboard", not the view's name. Under it, the five views are an in-page row of underline tabs (Spending, Cash flow, Category trends, Per Member, Money flow) over a Line hairline: they are lenses on the same period, not separate destinations. Under the tabs, a sticky filter bar holds the period stepper (‹ period ›, with "so far, to 16 Oct" muted) and the period unit select on the left, and the Member and Account filters pushed to the right, all 36px high. The bar sticks to the top on scroll on a 92% ground tint with a backdrop blur, so the period stays in view beside the figures. Transactions has its own layout instead: a search field, a summary line and a facet rail (see Transactions page). Other pages have the title row only. Below the Dashboard's filter bar, three equal stat tiles (16px gap). They carry the headline figures for the chosen period. There is no global "this month" figure anywhere in the shell. Then a two-card grid, with the donut card at 5fr (min 340px) and the ranked Category list at 7fr. The drill-down card opens full width beneath. Spacing follows a 4px base (4, 8, 12, 16, 20, 24, 32). Cards pad 20px, and the gap between cards is 16px.

**Phone (≤900px).** The sidebar is replaced by a fixed 64px bottom tab bar with four items: Dashboard, Transactions, Review (with its count badge) and More. Each is a 22px icon over an 11px label, muted, and Indigo Ink when active. The bar is a 94% card tint with a backdrop blur and a top hairline, and it pads for the safe area. More opens a bottom sheet (18px top corners, a grip, the Pop shadow) over a 35% black scrim, closing on the scrim or Escape. It holds Import, the Manage links, the theme switch, and the Member's name and role with Log out. Import sits under More because Import needs only work on desktop. A plain 52px row above the content carries the mark and wordmark (it does not stick). The main column pads 16px and leaves room for the tab bar. The view tabs scroll sideways. In the sticky filter bar, the period stepper takes a full row, and the Month, Member and Account controls share the next row (their icons hidden, labels truncating with an ellipsis). Tiles keep three columns at 8px gaps and drop their comparison line. The grid stacks. The Category list drops its share bar. Transaction rows stack as cards (see Transaction row). On Transactions, the facet rail moves into a sheet behind a Filter button (see Transactions page).

## Elevation & Depth

The system uses soft ambient lift with tonal layering. Cards float on the grey ground through a faint two-layer shadow, with no border in light. In dark, the same role is a deeper black shadow plus a 3% white hairline ring, so graphite cards read as raised. Overlays (the phone More sheet, the account popover and the Account filter) use a larger "pop" shadow. Controls carry a barely-there 1px shadow under their border.

### Shadow Vocabulary
- **Card** (`0 1px 2px rgb(16 24 40 / .05), 0 1px 3px rgb(16 24 40 / .06)`; dark: `0 1px 2px rgb(0 0 0 / .4), 0 0 0 1px rgb(255 255 255 / .03)`): every card, and the pressed segment of the theme switch.
- **Pop** (`0 4px 8px -2px rgb(16 24 40 / .08), 0 12px 24px -4px rgb(16 24 40 / .10)`; dark: `0 8px 24px -4px rgb(0 0 0 / .6), 0 0 0 1px rgb(255 255 255 / .05)`): the phone More sheet, popovers and other overlays.
- **Control** (`0 1px 2px rgb(16 24 40 / .04)`): buttons, selects and the period stepper.

### Named Rules
**The Soft Lift Rule.** Depth is diffuse and ambient, never a hard offset. Cards are borderless in light. Hairlines divide content inside cards, not cards from the ground.

## Shapes

The corners are gently rounded, nested from outside in: cards 14px, Category rows 10px, controls and nav items 8px, inner segments and the focus ring 6px. Counts, Account pills and share bars are full pills. The phone More sheet has 18px top corners. Dots and the avatar are circles. Donut segments have a 5px corner radius and a 1.5° gap between them. The mark is an 8px-radius (on 32) indigo tile carrying a two-segment donut, white for the larger arc and Mark Periwinkle for the smaller. It stays the same in both themes.

## Components

### Buttons
Quiet, bordered and solid. They are never filled with indigo.
- **Shape:** gently rounded (8px), 36px high (32px inside table rows), 12px horizontal padding. Icon-only buttons are 36px squares.
- **Default:** a card fill, a Line Strong border, Ink text at 500, a muted 16px icon and the control shadow.
- **Hover / Focus:** the Hover fill. Focus is a 2px Focus Indigo outline at a 2px offset.
- **Ghost:** transparent and borderless, muted text, turning to Ink on Hover (close, log out, menu).
- **Select:** the button style with a 16px muted chevron drawn at the right, and `appearance: none`.

### Period stepper
A single bordered 36px control: previous/next chevron buttons around a 600-weight period label with a muted 400 qualifier. Next is disabled at the current period (35% opacity). Previous is disabled once the period contains the Household's first Coverage day (the earliest of every Account that receives Statements, whatever the filters), so switching a filter never strands the reader. A typed URL for an earlier period still works and shows that period as Not tracked (see Period completeness).

### Cards / Containers
- **Corner Style:** 14px.
- **Background:** card.
- **Shadow Strategy:** Card shadow (see Elevation).
- **Border:** none. Inner hairlines in Line divide the list total and table rows.
- **Internal Padding:** 20px. The card head is 20px with no bottom padding, with a 15px title and optional muted meta at the right.

### Stat tiles
A muted 500 label, a Display figure and a muted 13px comparison sentence. The figure is never coloured by sign. When the period or the one it is compared with isn't Complete (see Period completeness), the comparison reads "Not comparable: July is incomplete" instead, naming the incomplete month (the period's own, if both are).

### Category list (signature)
Ranked rows, largest first, with Awaiting review always last. Each row shows a disclosure chevron, a hue dot and the Category name, a 6px pill share bar (Category hue on a ground track, scaled to the largest), the share percentage and the amount (600). Hover or focus lights the row (Hover fill) and highlights its donut segment. The open row takes Indigo Wash and expands its Subcategories (13px, Ink 2, indented). A Total row closes the card above a hairline. The Awaiting review row carries a "Review N" link to the Review queue.

### Donut (signature)
An ECharts SVG pie, radius 56–78% (47–66% when narrow), with the period total in the centre (Headline figure, muted caption). On hover the centre shows the hovered Category's amount and name. Segments are labelled directly in Ink 2, Inter 500 12px (11px narrow, and only segments of 5% or more when narrow), with Line Strong leader lines. Awaiting review is unlabelled and hatched with 45° white stripes at 45%. Hovering a segment highlights its row (and the reverse), with a 6px emphasis scale. With a Category open, other segments dim to Line Strong. The donut sweeps in once on load (700ms, cubic-out), and not at all under reduced motion. Tooltips use the card fill, a Line border and Ink text. The chart re-themes by rebuilding its options from CSS custom properties (`getComputedStyle`) and calling `setOption` with `notMerge` on theme switch, system scheme change and resize. ECharts 5.6 has no live theme switch.

### Charts (the other Dashboard views)
Classic axes, Monarch-style: every chart sits in a card, has a legend, has quiet axes and a table beside it. All charts are ECharts SVG and are built from the same parts:
- **Legend:** top left, 8px circle icons, Ink 2 Inter 500 12px, 16px between items. It scrolls when it overflows. A hidden series' icon turns Line Strong. Clicking an entry hides its series (Trends, Per Member).
- **Value axis:** labels in whole euros ("1.200 €"), Muted 12px. Solid Line gridlines. No axis line or ticks.
- **Category axis:** a Line Strong baseline, no ticks, Muted 12px labels (the month labels the server sends).
- **Tooltip:** the card fill, a Line border, a 10px radius and the Pop shadow, with Ink 13px text. An axis tooltip is a small table: the month in 600, then one row per series (hue dot, name in Ink 2, amount right-aligned in 600, tabular), sorted biggest first where the series are Categories, with a Total row under a hairline. Amounts in tooltips carry cents ("1.234,56 €"), and Net carries its sign. Bars use a shadow pointer in Hover at 60%, and lines use a Line Strong pointer line.
- **Emphasis:** hovering a series focuses it and blurs the rest (lines to 15% opacity, bar segments to 25%).
- **Motion:** a 600ms cubic-out entrance, and none under reduced motion. `aria.enabled` is on for every chart.

Per view:
- **Cashflow:** grouped bars for Money in (the Income Category's hue) and Money out (Muted, a neutral, since spending as a whole is no Category). The bars are at most 22px wide, with a 4px top radius and a 10% gap. Net is an Ink line, 2px, with 7px circle points ringed in the card colour. Under a Member filter, "To/from other Members" is a dashed Ink 2 line.
- **Category trends:** one 2px line per Category in its hue, with no points until hover (7px circles). Awaiting review is a dashed Awaiting line, since a line can't carry the hatch. The tooltip lists every Category for the month, biggest first, with a Total row.
- **Per Member:** horizontal stacked bars, one per Bucket (at most 28px), Bucket names in Ink 13px 600. Segments are in Category hues with a 1.5px card-coloured border between them, and Awaiting review is hatched. The tooltip lists the Bucket's Categories, biggest first, with a Total row.
- **Money flow (Sankey):** income nodes on the left, Household in the middle, Categories and Saved/From savings on the right. Nodes are 12px wide with a 2px radius and 10px gaps. Income Subcategories wear the Income Category's hue, Household is Ink 2, Saved, From savings and To/from other Members are Muted, and Awaiting review is hatched. Links take a source-to-target gradient at 30% opacity (60% on hover, with adjacency focus). Income node labels sit to the left of their nodes, Household's sits above it, and the rest sit to the right, each as "name amount" (Ink 2 500, then the amount in Muted, whole euros). Labels that would overlap are dropped, and the table beside the chart still lists every node. The edge tooltip reads "Salary → Household", then the amount and its share of money in.

Every chart rebuilds its options from the CSS tokens and calls `setOption(…, { notMerge: true })` on theme switch, on system scheme change and when its width changes (the existing per-chart `ResizeObserver`), as the donut does.

### Period completeness
A missing Statement must never read as less spending. The Dashboard reads Coverage (derived, read-only: no new data, no URL change) and says how complete the period is. It considers only the Accounts the Member and Account filters include, so it never names an Account whose numbers aren't on screen. Accounts that receive no Statements are never considered.

**Month states.** Each month, for the included Accounts, is one of:
- **Complete:** no Gap. Drawn as usual, and a 0 is a real 0.
- **Partial:** at least one included Account has a Gap in it (a missing July; or 16–30 Sep, after a mid-month import).
- **Partly tracked:** before the first Coverage day of some included Account but not of all. It isn't a Gap: Coverage can't tell an Account opened later from one whose earlier Statements were never imported, so the month says what is known without claiming anything is missing.
- **In progress:** the running month, with no Gap up to today. Incomplete by time, not by a Gap.
- **Not tracked:** before the first Coverage day of every included Account. There are no numbers, not zeros.

The running month with a Gap is Partial. A longer period takes the first of Partial, Partly tracked, In progress, Not tracked, Complete that any of its months is. A period that is wholly Not tracked shows the empty state ("No Statements cover this period yet") instead of a view.

**Header line.** One line between the view bar and the stat tiles: Ink 2 13px with a muted 16px info icon, no fill, border or alert colour (the No Verdict Rule). It has up to three parts, joined by "·":
1. **Gaps,** leading with the consequence: "Incomplete: no Statements yet from Luka's N26 for 1–31 Jul". Each Account name links to Import. Past two Accounts the rest collapse into "and 2 more", which expands in place.
2. **Partly tracked,** for each included Account that isn't tracked yet during a part of the period in which another one is: "Joint Revolut is tracked from 1 Feb 2026". No link, because there may be nothing to import.
3. **Awaiting review:** "2.148 € (81 %) still awaiting review", linked to the Review queue, whenever the period's Awaiting review is not zero. It is a statement of fact, not a nudge, and never makes a period incomplete.

The line is absent when neither part applies. In progress alone adds nothing here, because the stepper's "so far, to 17 Oct" already says it. On a phone it wraps and is never truncated.

**Month-axis charts** (Cashflow, Category trends, and any view over several months). The data marks stay as they are, because they are real numbers, only incomplete. The month column carries the state:
- **Partial / Partly tracked / In progress:** a full-height band behind the month in Hover (Raised is invisible on the card), with a muted 11px label at its top, "Partial", "Partly tracked" or "So far". The bands are a bar series of their own on hidden axes, because a `markArea` from a month to itself has no width on a category axis, and on the shared axes they would join Cashflow's bar groups. Category trends draws its points at month centres (`boundaryGap: true`) so that each month is a column a band can fill. The axis label of the running month reads "Oct (so far)". The axis tooltip opens with the reason ("No Statements from Luka's N26 for 1–31 Jul", "Joint Revolut is tracked from 1 Feb 2026", or "So far, to 17 Oct") above its table.
- **Not tracked:** the month keeps its place on the axis with a Faint label, and its data is `null`: no bar, and lines break rather than dropping to 0. Its tooltip reads "No Statements yet".

The bands' text labels are the non-colour cue. The hatch stays reserved for Awaiting review and the dash for Awaiting review as a line, so completeness uses neither.

**Tables** beside the charts carry the same states in text: column headers "Jul (partial)", "Jan (partly tracked)" and "Oct (so far)", and "—" (never 0) in a Not tracked month's cells. A qualifier wraps under the month, in Muted, so it never widens the table.

**Periods.** Every view opens on the last full month, even when that month is Partial (the header line says why), and Category trends opens on the 12 months ending with it. The running month is reached only with ›, as In progress. There is no "this month so far" anywhere else.

### Drill-down
A full-width card titled with the Category's hue dot and "Category · Period", with a ghost close button. When the period isn't Complete, the title carries the same qualifier as the tables: "Food · July 2026 (partial)", "(partly tracked)" or "(so far)". A table of Transaction rows follows (see Transaction row). A muted footnote explains that changing an outcome moves the amount between Categories. The card's foot links to the whole list: "All 37 in Transactions ›", which opens Transactions filtered to that Category, period, Member and Account.

### Transaction row
One row is shared by the Review queue, Transactions and the drill-down. Its columns are Date, Transaction (500, with a muted caption for the kind), Account (pill), Outcome, and Amount (right-aligned, 600, tabular). Rows have hairline dividers and a Raised hover. Every Member can change an outcome on every surface, always through an explicit action.
- **The outcome is text, not a control.** It reads as the Category's hue dot, then "Category › Subcategory", with the Category in Muted, the › in Faint and the Subcategory in Ink at 500. It always names its Category, so the eight "Other" catch-alls never read alike. A Transfer gets a hollow Muted ring, and Awaiting review gets the hatched dot. A muted source caption follows ("by Rule", "by LLM", "by hand", "by IBAN", "paired").
- **Actions on reading surfaces.** Transactions and the drill-down show a "Change" text button in Indigo Ink.
- **Actions in the Review queue.** They depend on the row:
  - with a suggestion: the suggested outcome as text, "86 % sure" in Muted, an Accept button (32px) and a "Something else" text button;
  - without one: "Awaiting review" and a Choose button;
  - an ambiguous Transfer: "Transfer", "other side unknown" and "Pick the other side".
- **Action layout.** The actions keep a fixed place at the end of the cell. A long outcome ("Leisure › Subscriptions & digital services") wraps its own label and never pushes the actions onto a new line.
- **Picking with a fine pointer: the chip panel.** Change, Choose, Something else and Pick the other side open a panel in a full-width row under the Transaction, on the Raised fill.
  - **Title row:** "Choose an outcome for *description*", with a Cancel text button.
  - **Ambiguous Transfer:** the candidate other sides come first, as bordered cards (description, date · Account, amount).
  - **Chips:** "Most used" chips (the Household's five most-used outcomes, each "Category › Subcategory"), then one chip per Category (hue dot and name), then Transfer. A Category chip swaps the chips for its Subcategories, with "‹ All Categories" to go back.
  - **Chip style:** 36px pills with the card fill and a Line Strong border. The current outcome's chip takes Indigo Wash with an Indigo border.
  - **Focus:** only one panel is open at a time. Opening it moves focus to the first chip; Escape or Cancel closes it and returns focus to the button that opened it.
- **Picking with a coarse pointer: the native select.** Under `(pointer: coarse)`, the same buttons are a transparent native `<select>` laid over the button, so a tap opens the OS picker. The select is 16px, so iOS doesn't zoom.
  - **Options:** each reads "Category › Subcategory", in optgroups: the other side of a Transfer, Suggested, Most used, each Category, then Transfer.
  - **Gate:** the pointer, not the width. A narrow desktop window still has a keyboard, so it keeps the panel.
- **What commits.** Only a deliberate choice: Accept, a tap on a Subcategory, Most used or Transfer chip, a pairing card, or a confirmed pick in the OS picker (a touch picker fires `change` only on confirm). Arrow keys never save. Without JS, each row is a form with a select and a Save button.
- **After a save.** The row swaps in place, and a muted line appears under the outcome: "✓ Saved as Category › Subcategory · Undo". After a save by hand in the Review queue it adds "· Make a Rule". The line goes after 10 s. Undo restores the previous outcome and its source.
- **A failed save.** The row stays as it was and says so in Ink with an alert icon: "Couldn't save *outcome*. Nothing changed. Try again". It uses no red.
- **Focus after a save.** In the Review queue, focus moves to the next Transaction still waiting. Elsewhere, it returns to the row's Change. Every save, failure and Undo is announced politely.
- **Phone (≤600px).** Each row is a stacked card:
  - description and amount on the first line;
  - date, kind and Account in a muted caption;
  - the outcome, with its actions under it at 44px (Accept stretches; Change and Something else stay text buttons).

### Transactions page
Every Transaction, narrowed by facets, read 25 at a time. The page answers "find that one" and "show me all of these", and the Dashboard links into it.
- **Header.** The title row, then a 36px search field (300px) for the description, then a summary line. The summary reads "**142 Transactions** · 1.234,50 € out · 2.410,00 € in". When filters are active, it names them ("· September 2026, Food › Groceries") and ends with a "Clear filters" text button. Out and in leave Transfers aside, as the Dashboard does.
- **Layout.** A two-column grid with a 16px gap: the facet rail as a 252px card, and the table card. The rail sticks 16px from the top and scrolls on its own when it is taller than the window.
- **The facet rail.** These groups each have a muted 12px heading, with a "Clear" text button on the right while it is set:
  - Period: All time, then each month newest first, the running one "(so far)".
  - Member: Everyone, then each Bucket (Members, then Joint).
  - Account: All Accounts, then each Account.
  - Outcome: Any outcome, Awaiting review (hatched dot), Transfer (hollow ring), then each Category with its hue dot. A chosen Category opens its Subcategories beneath it, indented 26px.
  - Decided: Any way, then by Rule, by LLM, by IBAN, paired and by hand. Each has a one-line muted explanation under its name: "A Rule matched it. Rules are patterns a Member set up, often from a correction".
  - Amount: a Money segmented control (Any / Out / In), then "Amount between" two inputs.
- **Facet options.** Each is a full-width 14px row (Ink 2) with its count on the right (12px, Muted, tabular). The count is how many Transactions that option would give with every other facet held. Hover takes the Hover fill. The chosen option takes Indigo Wash and Indigo Ink, with `aria-pressed="true"`. A group has one choice; picking the chosen option again clears it. An option with a count of 0 is faded to 45% but stays pickable.
- **Applying.** A pick applies at once: HTMX swaps the page, the URL updates, and paging goes back to page 1. The search applies as you type, debounced. A Transaction changed with Change stays in view until the filters change, even if it no longer matches.
- **The table.** Transaction rows with the Date column, newest first (see Transaction row). The source caption carries the specific reason as its `title` ("Matched the Rule “HOFER” → Food › Groceries", "Maja chose it on 8 Oct").
- **Pages.** There are 25 rows a page. A pager at the card's foot over a hairline holds:
  - "‹ Newer" (a 36px button);
  - the page numbers: first, last, and the current one ±1, with "…" between;
  - "26–50 of 192" in Muted;
  - "Older ›".
  The current page takes Indigo Wash and `aria-current="page"`. The ends disable at the first and last page. Changing page keeps the filters and scrolls to the top of the grid.
- **Deep links.** Transactions reads the Dashboard's own query parameters (`period`, `member`, `account`) plus `q`, `outcome` (`unresolved`, `transfer`, `category-<id>`, `subcategory-<id>`), `source`, `dir`, `min`, `max` and `page`. A link from the Dashboard adds a breadcrumb above the title: "Dashboard › Spending · Food · September 2026". The Dashboard part links back with the same period and filters. The breadcrumb goes once the period, Member or Outcome changes.
- **Empty.** "No Transactions match." with a "Clear the filters" text button. With no Transactions at all, the page keeps today's "Import your first Statement".
- **Phone (≤900px).** The rail leaves the grid.
  - **Sticky bar:** the search field and a "Filter" button with the active-filter count badge, 44px, on the 92% ground tint with a backdrop blur.
  - **Filter sheet:** the button opens the rail as a bottom sheet, like More: 18px top corners, a grip, up to 90vh, scrolling. It is titled "Filter", with "Clear all" on the right. Its foot is a sticky full-width 44px Indigo button, "Show 142 Transactions", which closes it. Picks apply live underneath.
  - **Pager:** centred, with 40px page buttons; the "26–50 of 192" range is hidden.

### Navigation
The shell is organised by the Household's jobs, not by code modules: four destinations, with everything that is maintenance tucked under Manage.
- **Sidebar:** the wordmark and mark at the top. Then four destinations: Dashboard, Transactions, Review queue (with its count badge) and Import. Items are an 18px 1.5px-stroke icon plus a 500 15px label, Ink 2, padded 9px 12px. Hover takes the Hover fill. Active takes Indigo Wash with Indigo Ink and `aria-current="page"`. Dashboard stays active on all five views.
- **Manage:** below the destinations, a collapsible group under a muted 12px "Manage" heading with a rotating chevron. It holds Rules for every Member, then Categories, LLM suggestions, Accounts and Members for admins. Its links are 14px, indented, without a separate Admin heading. The group is closed by default and opens when one of its pages is current.
- **Review queue count:** an Indigo count badge on the Review queue item (sidebar) and on the Review tab (phone), shown to every Member and hidden when the queue is empty. The Dashboard's Awaiting review row also links to the queue ("Review 7").
- **Sidebar foot:** a single account button (avatar, name and role, an up/down chevron). It opens a popover upward holding the theme switch (a three-segment Light / System / Dark control on a ground track, where the pressed segment takes the card fill and Card shadow; it sets `data-theme` on `<html>` and is remembered per browser in `localStorage`) and Log out.
- **Theme switch behaviour:** the three segments are a native radio group (visually hidden `<input type="radio" name="theme">` with labelled segments, each an icon plus its text), so arrow keys move between them and there is one tab stop. The switch stays `hidden` until `static/theme.js` runs, which checks the saved segment on load and again on `htmx:historyRestore`. Only the shell has it, in the account popover (desktop) and the More sheet (phone): login and registration simply honour the saved choice. Radio groups are grouped by `name` across the whole document, so if both are rendered they use distinct names (`theme`, `theme-sheet`) and `theme.js` keeps them in step. `<html>` ships as `data-theme="system"`, and a blocking inline script in `base.html`'s `<head>`, before the stylesheet, applies the saved `theme` (only `light`, `dark` or `system`; anything else, or storage throwing, means `system`) before first paint. HTMX never replaces `<html>`, so swaps cannot flash. On a change, `theme.js` dispatches a `themechange` event on `document`, also when the system scheme changes while System is active, and `dashboard.js` rebuilds each mounted chart's options from it. The switch is instant, with no colour transition.
- **Carried period and filters:** every link back to a Dashboard view carries the chosen period and the Member and Account filters in its URL, from any page. Links into Transactions carry them too, as the same query parameters. The sidebar's Transactions link opens All time. Transactions and the Dashboard views are swapped in by HTMX without a full reload.
- **Phone:** the bottom tab bar and More sheet as described in Layout.

### Icons
Line icons on a 24 grid, 1.5px stroke, round caps and joins, `currentColor`. They are 18px in navigation and 16px in controls. Icons are inline SVG symbols, never glyphs or an icon font.

## Do's and Don'ts

### Do:
- **Do** key every Category's hue to its Category id (`cat-((id − 1) mod 10)`), and use the same hue in every view and chart.
- **Do** label donut segments directly and hatch Awaiting review, so no chart relies on colour alone.
- **Do** set every figure in tabular numerals and format amounts as sl-SI EUR with grouping always on ("1.234,56 €").
- **Do** write comparisons as neutral muted sentences ("523,55 € less than September").
- **Do** define every colour as a CSS custom property, with a `[data-theme="dark"]` block and a `prefers-color-scheme` block for `data-theme="system"`, and rebuild chart options from those properties when the theme changes.
- **Do** set CSS `color-scheme` per theme, so native controls and scrollbars match, and ship `media`-scoped `<meta name="theme-color">` tags for the ground colour, rewritten by JS when the choice is Light or Dark.
- **Do** self-host every asset, including Inter (variable woff2 under `static/fonts/`) and ECharts.
- **Do** show each facet option's count with the other facets held, so a Member sees where a pick leads before making it.
- **Do** commit an outcome only on a deliberate choice (Accept, a chip, a confirmed OS pick), always name it "Category › Subcategory", and offer Undo after every save.
- **Do** turn motion off under `prefers-reduced-motion`. The donut sweep, chevron rotation and the More sheet's slide up (cubic-bezier(.16,1,.3,1)) are the whole motion vocabulary.

### Don't:
- **Don't** save on a `<select>`'s `change` where a keyboard can reach it: Chromium and Firefox fire it on every arrow key.
- **Don't** use the indigo accent as a data colour, a chart series or a Category hue.
- **Don't** give Awaiting review a Category hue, or show it without its hatch.
- **Don't** draw a month without Coverage as 0, or compare a figure with an incomplete month without saying so.
- **Don't** colour spending, Net or comparisons red or green to mean good or bad.
- **Don't** add uppercase tracked labels, kickers or eyebrows above titles. Labels are sentence case.
- **Don't** use hard offset shadows or borders around cards. Lift is soft and ambient.
- **Don't** load fonts, scripts or styles from a CDN in production.
