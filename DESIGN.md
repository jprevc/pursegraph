---
name: Pursegraph
description: A household finance dashboard in the category standard, done impeccably: light sidebar, white cards, one indigo accent.
colors:
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
  accent: "#4f46e5"
  accent-ink: "#ffffff"
  accent-soft: "#eef2ff"
  accent-text: "#4338ca"
  focus: "#6366f1"
  awaiting: "#9ca3af"
colorsDark:
  ground: "#0e1014"
  card: "#171a20"
  raised: "#1d2128"
  hover: "#222731"
  ink: "#f3f4f6"
  ink-2: "#d1d5db"
  muted: "#9ca3af"
  faint: "#6b7280"
  line: "#262b34"
  line-strong: "#343a46"
  accent: "#5850ec"
  accent-ink: "#ffffff"
  accent-soft: "#1e1b4b"
  accent-text: "#a5b4fc"
  focus: "#818cf8"
  awaiting: "#6b7280"
categoryColors:
  light: ["#4e79a7", "#59a14f", "#f28e2b", "#b07aa1", "#76b7b2", "#edc948", "#ff9da7", "#9c755f", "#e15759", "#a0cbe8"]
  dark: ["#6b9bd1", "#6cc05f", "#f5a04d", "#c697b8", "#8fd0ca", "#f1d45e", "#ffb3bb", "#b8917a", "#ef7a7b", "#b5d6ef"]
typography:
  page-title:
    fontFamily: "Inter, system-ui, -apple-system, 'Segoe UI', sans-serif"
    fontSize: "24px"
    fontWeight: 600
    letterSpacing: "-0.01em"
  stat-value:
    fontFamily: "Inter, system-ui, sans-serif"
    fontSize: "28px"
    fontWeight: 600
    letterSpacing: "-0.02em"
  card-title:
    fontFamily: "Inter, system-ui, sans-serif"
    fontSize: "15px"
    fontWeight: 600
  body:
    fontFamily: "Inter, system-ui, sans-serif"
    fontSize: "14px"
    fontWeight: 400
    lineHeight: 1.5
  small:
    fontFamily: "Inter, system-ui, sans-serif"
    fontSize: "13px"
    fontWeight: 400
  label:
    fontFamily: "Inter, system-ui, sans-serif"
    fontSize: "12px"
    fontWeight: 500
rounded:
  card: "14px"
  row: "10px"
  control: "8px"
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
  card:
    backgroundColor: "{colors.card}"
    rounded: "{rounded.card}"
    shadow: "0 1px 2px rgb(16 24 40 / .05), 0 1px 3px rgb(16 24 40 / .06)"
  button:
    backgroundColor: "{colors.card}"
    textColor: "{colors.ink}"
    border: "1px solid {colors.line-strong}"
    rounded: "{rounded.control}"
    height: "36px"
  nav-item-active:
    backgroundColor: "{colors.accent-soft}"
    textColor: "{colors.accent-text}"
    rounded: "{rounded.control}"
  badge:
    backgroundColor: "{colors.accent}"
    textColor: "{colors.accent-ink}"
    rounded: "{rounded.pill}"
---

# Design System: Pursegraph

Decided in [#62 Visual direction](https://github.com/jprevc/pursegraph/issues/62). The reference build is the prototype at `prototypes/62-visual-direction/` on the `prototype/62-visual-direction` branch: the Dashboard's Spending view and the app shell, in light and dark. Product context and voice are in `PRODUCT.md`, and domain terms are in `CONTEXT.md`.

## 1. Overview

**North Star: "The category standard, done impeccably."**

Pursegraph deliberately looks like a polished personal-finance dashboard, and the bar for its craft is Monarch Money. It has a cool grey ground, white cards with a soft shadow, a light 240px sidebar, Dashboard stat tiles, a Category donut and one indigo accent. The convention is played straight. Familiarity serves the less technical reader, so there is no world costume and no quirk smuggled in. This was chosen over more distinctive directions (see the #62 decision).

**Key characteristics**
- Cool-grey ground (`--ground`) under white cards (`--card`). In dark mode, the ground is near-black and the cards are raised graphite.
- Inter everywhere, with tabular figures for every amount.
- One indigo accent, used only for the active state, badges, links and focus.
- Ten Category hues. A Category keeps the same hue in every view and chart.
- 1.5px-stroke line icons at 16–18px.
- Calm density: generous card padding and a 14px base size.

## 2. Colours

Every colour is a CSS custom property on `:root`. Templates never use raw hex values.

### Neutrals
- **Ground** `--ground`: the page background, and the track behind progress bars.
- **Card** `--card`: cards, the sidebar, buttons and the phone top bar.
- **Raised** `--raised`: table-row hover and pills.
- **Hover** `--hover`: nav and Category row hover.
- **Ink / Ink-2 / Muted / Faint**: primary text, secondary text, labels and meta, then chevrons and disabled.
- **Line / Line-strong**: hairlines and table rules / control borders and chart leader lines.

### Accent
- **Accent** `--accent` (#4f46e5): badge fills and the brand tile. It is never used for a large surface.
- **Accent-soft / Accent-text**: the active nav item, the open Category row, the avatar and links.
- **Focus** `--focus`: the focus ring.

### Data
- **Category hues** `--cat-0` … `--cat-9`: assigned to Categories in a stable order. The dark-mode set is the same hues with lightness raised.
- **Awaiting** `--awaiting`: Awaiting-review spending. It is always drawn **hatched** (45° stripes, or an ECharts decal), never as a flat colour, so it can't be mistaken for a Category.

### Theming
- `data-theme` on `<html>` takes `light`, `dark` or `system`. `system` follows `prefers-color-scheme`. The dark token block is repeated under `:root[data-theme="dark"]` and under `@media (prefers-color-scheme: dark) { :root[data-theme="system"] }`.
- Charts read their colours from `getComputedStyle` tokens and are rebuilt with `setOption(notMerge)` when the theme changes (see #65).

### Rules
- **One-accent rule.** Indigo is the only brand colour, and it marks state, not decoration.
- **No judging colours.** Spending is never red and saving is never green. Category hues carry identity, not sentiment (see `PRODUCT.md`: never a budgeting nag).

## 3. Typography

**Inter** (OFL), weights 400/500/600/700, with `font-feature-settings: "cv11", "ss01"`. The prototype loads it from Google Fonts. The real app **must self-host** the woff2 files under `static/`, because the app uses no CDN. The fallback stack is `system-ui, -apple-system, "Segoe UI", sans-serif`.

| Role | Size | Weight | Notes |
|---|---|---|---|
| Page title (`h1`) | 24px (20px on phone) | 600 | -0.01em |
| Stat value | 28px (15px on phone) | 600 | -0.02em, tabular |
| Donut centre value | 24px (17px on phone) | 600 | tabular |
| Card title (`h2`) | 15px | 600 | |
| Body | 14px / 1.5 | 400–500 | |
| Small / meta | 13px | 400 | muted |
| Label / table header / nav group | 12px | 500 | muted, sentence case, no uppercase tracking |

- **Numbers:** every amount uses `.num` (`font-variant-numeric: tabular-nums`) and is formatted with `Intl.NumberFormat('sl-SI', {style: 'currency', currency: 'EUR', useGrouping: 'always'})`, for example `4.210,00 €`. One format everywhere. This fixes the inconsistent number formats the critique found (#61).
- **Wordmark:** "Purse" in ink plus "graph" in `--accent-text` 600, 17px 700, -0.02em, set beside the mark.

## 4. Elevation

Two shadows, and borders only where needed:
- `--shadow` sits under every card, tile and the pressed segment of a segmented control.
- `--shadow-pop` is for overlays: the phone sidebar drawer and popovers.
- In dark mode the shadows deepen and add a 1px white rim at 3–5% opacity, so cards keep their edge.
- Cards have no border. Controls do have one (`--line-strong`), plus a 1px hairline shadow.

## 5. Layout and shell

- **Desktop (above 900px):** a two-column grid with a sticky 240px sidebar and fluid content. `main` has a max width of 1360px and padding of 24px top and 32px sides.
- **Sidebar**, top to bottom:
  - the mark and wordmark;
  - nav groups "Dashboard" (five views), "Ledger" (Transactions, Import, Review queue with a count badge, Rules) and "Admin" (Categories, LLM suggestions, Members);
  - a footer holding the three-way theme switch (light / system / dark) and the Member, with a log-out button.
  - #63 may still change this.
- **Phone (900px and below):**
  - The sidebar becomes a 280px off-canvas drawer with a scrim.
  - A sticky 56px top bar is translucent and blurred, and holds the mark, a Review shortcut with its badge, and the menu button.
  - The Dashboard views become a row of horizontally scrolling pills.
  - The page itself never scrolls sideways.
- **View bar:** the title, the period stepper (prev / label with "so far, to 16 Oct" / next, with next disabled at the present), the period unit select, and the Member and Account filters.
- **Spending view:**
  - three tiles (Spent, Money in, Net), each comparing with the previous period in plain words;
  - a donut card (5fr) beside a ranked Category list card (7fr);
  - a drill-down card that opens below them, titled with the Category's dot and name.

## 6. Components

- **Card:** `--card`, 14px radius, `--shadow`, 20px padding. The card head has a 15px/600 title, with meta pushed right.
- **Button:** 36px tall, 8px radius, a `--line-strong` border, `--card` fill and 500 weight. The **ghost** variant has no border or fill and muted text. **Icon-only** buttons are 36×36 and always have an `aria-label`. Native `<select>` elements take the button style, with a chevron drawn as a background SVG.
- **Nav item:** 7px × 8px padding, 8px radius, ink-2 text. Hover uses `--hover`. The active item is `accent-soft` with `accent-text` and `aria-current="page"`.
- **Badge:** a pill filled with `--accent`, 12px/600, tabular, with an `aria-label` that names the count.
- **Segmented control** (theme switch): `--ground` track, and the pressed segment is `--card` with `--shadow`, using `aria-pressed`.
- **Category row:**
  - grid columns are chevron, dot and name, a 6px pill bar, share %, then amount;
  - hover uses `--hover` and the open row uses `accent-soft`;
  - subcategories expand beneath the row.
  - On phone, the bar is hidden.
- **Table** (drill-down / Transactions):
  - 12px muted headers, 12px × 20px cells and `--line` rules;
  - the description sits over muted small meta.
  - On phone, each row collapses into a two-column card and the table header is hidden.
- **Pill:** for an Account or Member tag. `--raised` fill, a `--line` border, 12px/500.
- **Icons:** inline SVG `<symbol>` sprite, 24 viewBox, 1.5 stroke, round caps and joins.

## 7. Charts (ECharts)

- Use the SVG renderer. Colours come from tokens, and the tooltip uses `--card`, `--line` and `--ink` with Inter.
- **Donut:** radius 56–78% (47–66% when narrower than 420px), `padAngle` 1.5, segment radius 5. The centre label shows the period total.
- **Labels:** outside labels on desktop. When narrow, only Categories at 5% or more get a label.
- **Two-way highlight:** hovering or focusing a list row highlights its segment, and the reverse. Opening a Category greys the other segments to `--line-strong`.
- **Accessibility:** every chart has `role="img"` and an `aria-label`, and a table or list with every figure sits beside it. Colour is never the only way to tell series apart: Awaiting review is hatched.
- **Motion:** a single 700ms `cubicOut` sweep when the page loads. Re-renders don't animate.
- #64 settles the styling of the other views.

## 8. Motion

Sparse. The drawer slides in over 250ms, the chevron rotates over 200ms, and both use `cubic-bezier(.16,1,.3,1)`. Then there is the donut sweep. Every transition is turned off under `prefers-reduced-motion: reduce`.

## 9. Accessibility

WCAG 2.2 AA (see `PRODUCT.md`).
- A visible `:focus-visible` ring: 2px `--focus`, 2px offset.
- Text tokens meet AA on their surfaces in both themes. `--faint` is for decoration and disabled states only, never for information.
- Drill-down swaps are `aria-live="polite"`.

## 10. Brand

- **Mark:** a two-segment donut (white and `#c7d2fe`) on an 8px-radius indigo (`#4f46e5`) tile. It is `favicon.svg` in the prototype, and it is also the sidebar logo at 28px.
- **Wordmark:** "Purse**graph**" in Inter (see Typography).

## 11. Do's and don'ts

**Do**
- Use tokens for everything, and theme both modes from the same component CSS.
- Keep each Category's hue identical across every view and chart.
- Put the figures in a table or list beside every chart.
- Write copy that is calm and factual and uses the `CONTEXT.md` terms.

**Don't**
- Use red or green to judge spending, or add streaks, goals or nudges.
- Use a second accent colour, gradients, glassmorphism (beyond the phone top bar's blur) or neon in dark mode.
- Load fonts or scripts from a CDN in the app.
- Leave Awaiting review unhatched, or draw it in a Category hue.
