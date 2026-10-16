# ECharts theming capabilities (vendored build)

Research for #65 (map #59, UI/UX redesign). Throwaway branch, not merged.

Sources: the vendored file `static/vendor/echarts.min.js` itself, and the
apache/echarts source **at tag `5.6.0`** (raw.githubusercontent.com/apache/echarts/5.6.0/...),
plus zrender at tag `5.6.1`. ECharts 6 facts come from the 6.0.0 tag and the
official "What's new in 6" handbook page.

## 1. Version

- `static/vendor/echarts.min.js` is **ECharts 5.6.0** (full build), bundling **zrender 5.6.1**.
  Evidence in the minified file: `t.version="5.6.0"` and `t.dependencies={zrender:"5.6.1"}`.
  5.6.0 was released 2024-12-28 (GitHub releases API).
- Newer releases exist: **6.0.0** (2025-07-30) and **6.1.0** (2026-05-19).
- The full build registers both renderers (`registerPainter("canvas")`, `registerPainter("svg")`),
  the `aria` component and the decal machinery, and the `en`/`zh` locales.

## 2. Themes: `registerTheme`, built-in `dark`, switching

- `echarts.registerTheme(name, themeObj)` just stores the object in a name→theme map
  (`src/core/echarts.ts` L2778). Built-ins registered at load: `'light'` and `'dark'`
  (minified: `bm("light",vy),bm("dark",wy)`).
- A theme is applied **only at `echarts.init(dom, theme, opts)`** (L2654; the constructor
  resolves the name, clones it and stores it in `this._theme`, L397-463).
- **No live switching in 5.6.0.** `ECharts#setTheme()` exists only as a private stub
  that logs `'ECharts#setTheme() is DEPRECATED in ECharts 3.0'` and does nothing
  (L696-698; in the minified build it calls a no-op). Switching the theme in 5.6 means
  `chart.dispose()` + `echarts.init(el, newTheme, …)` + `setOption(…)` again.
- The built-in `dark` theme (`src/theme/dark.ts`) sets `darkMode: true`,
  `backgroundColor: '#100C2A'` (navy, opaque), text/axis `#B9B8CE`, split lines `#484753`
  and its own 9-colour palette. It would not match our page background, so we'd override
  `backgroundColor` (e.g. `'transparent'`) anyway.
- **ECharts 6 adds real `chart.setTheme(theme, opts)`** (6.0.0 `src/core/echarts.ts` L729;
  registers `'default'` and `'dark'` so you can switch back). The 6.0 release note pitches it
  for following `prefers-color-scheme` without dispose/re-init (which replays the intro
  animation). v6 also ships a new default look; a `v5.js` theme is provided for migration.
  Upgrading is optional, see §8.
- **Key caveat for us:** a theme only supplies *defaults*. `dashboard.js` hard-codes every
  colour in the option (INK2, MUTED, GRID, AXIS, PALETTE, IN/OUT/NET/OTHERS, sankey node
  colours), and explicit option values beat the theme. So neither `registerTheme('dark')`
  nor v6 `setTheme` would recolour our charts by itself. What actually re-themes them is
  rebuilding the option with new colours and calling
  `chart.setOption(newOption, { notMerge: true })`, which works fine in 5.6 with **no
  dispose**. The bits still coming from the theme (tooltip box, legend page buttons,
  `backgroundColor`, emphasis label contrast) can be set explicitly in the option too.

## 3. Colours from CSS custom properties

- ECharts does not resolve `var(--x)`: colours are parsed by zrender's colour parser for
  emphasis lightening, opacity, gradients and label auto-contrast. With the SVG renderer a
  plain `var(--x)` string can pass straight through to the `fill` attribute
  (zrender 5.6.1 `src/svg/helper.ts` `normalizeColor` only rewrites `rgba(...)`), but derived
  colours (hover lift, sankey `'gradient'`, `darkMode` label contrast) silently break. The
  canvas renderer can't use it at all. **Don't pass `var()` strings.**
- Approach that works: read tokens in JS and feed concrete values in.
  ```js
  const css = getComputedStyle(document.documentElement);
  const token = name => css.getPropertyValue(name).trim();   // e.g. '#52514e'
  ```
  Build the option from those values. On theme change (a `matchMedia('(prefers-color-scheme: dark)')`
  `change` event, or our own toggle flipping `data-theme`), re-read the tokens and
  `setOption(build(data), { notMerge: true })` on each mounted chart.
- Set top-level `darkMode: true` in the option when dark. It's what the `dark` theme sets,
  and ECharts uses it to pick contrasting colours for labels drawn inside shapes.

## 4. Sankey styling (5.6.0 `src/chart/sankey/SankeySeries.ts`, `SankeyView.ts`)

- Node: `itemStyle` (colour, `borderColor`, `borderWidth`, `borderRadius`) per series, per node
  (`data[i].itemStyle`), or per depth via `levels: [{ depth, itemStyle, lineStyle, label }]`.
  Series-level `color: [...]` palette. Layout: `nodeWidth` (default 20), `nodeGap` (8),
  `nodeAlign: 'justify'|'left'|'right'`, `orient`, `draggable`, `layoutIterations`.
- Links: `lineStyle.color` accepts a colour or the keywords **`'source'`, `'target'`,
  `'gradient'`**. `'gradient'` builds a `LinearGradient` from source to target node colour
  and **only when both are plain string colours** (SankeyView `applyCurveStyle`). Also
  `opacity` (default 0.2) and `curveness` (default 0.5). Per-link `links[i].lineStyle`.
- Labels: `label` (default shown, `position: 'right'`, fontSize 12) with `formatter`, rich
  text, etc.; `edgeLabel` (default hidden) labels the links.
- Interaction: `emphasis.focus: 'adjacency' | 'trajectory'` (we use `'adjacency'`).
- Default link colour `#314656` @ 0.2 opacity is dark-on-light; ours (`'gradient'`, 0.35)
  works in both themes as long as node colours have enough contrast on the dark background.

## 5. Line chart styling (5.6.0 `src/chart/line/LineSeries.ts`)

- `lineStyle` (colour, width, `type: 'solid'|'dashed'|'dotted'`, shadow), `itemStyle`
  (symbols), `symbol`/`symbolSize`/`showSymbol`.
- `areaStyle` (fill under the line; `origin: 'auto'|'start'|'end'|number`). Colours can be
  `new echarts.graphic.LinearGradient(x0,y0,x1,y1,[{offset,color},…])` or the plain object
  form `{ type: 'linear', x, y, x2, y2, colorStops: [...] }`. That's the usual
  "fade to transparent" area.
- `smooth` (bool or 0-1), `smoothMonotone`, `step: 'start'|'middle'|'end'`, `connectNulls`,
  `sampling`.
- `endLabel` puts a label at the line's last point, which helps the Trends chart if we
  drop the legend on phones. `emphasis.focus: 'series'` (already used) dims the other lines.
- Top-level `visualMap` can colour a line by value (e.g. red below zero for "net").

## 6. Accessibility: `aria` and decals

- `aria: { enabled: true }` makes ECharts set `role="img"` and an auto-generated
  `aria-label` on the chart's container dom (5.6.0 `src/visual/aria.ts` L142-249). The text
  comes from the locale (`en` is built in; strings like *This is a chart about "{title}"*).
  `aria.label.description` replaces the generated text with our own, which is more useful
  for a money summary, and it's a natural place for a translated string from the template.
  Off by default.
- `aria.decal.show: true` overlays per-series/per-item patterns (dots, stripes) so colour
  isn't the only differentiator (default decal palette is in the light theme; minified
  `aria:{decal:{decals:[…]}}`). Per item: `itemStyle.decal = { symbol, dashArrayX,
  dashArrayY, rotation, color, … }`. Decals work in the SVG renderer we use (zrender 5.6.1
  SVG painter emits `<pattern>`s), and sankey links inherit the node decal with
  `'source'`/`'target'` link colours. They're visually noisy, so they suit an opt-in
  ("patterns" setting) or bar/sankey only.
- Not provided: keyboard navigation of data points. A real accessible alternative is a
  data table / the drill-down list, which we'd build ourselves.

## 7. Resizing

- ECharts 5.6 **does not watch its container**. The minified file has zero `ResizeObserver`
  and no `window` `resize` listener. You call `chart.resize(opts?)`, where `opts` is
  `{ width?, height?, animation?: { duration, easing }, silent? }` (`ResizeOpts`, L226-231).
  It errors if called during the main process (i.e. from inside a `setOption`).
- `dashboard.js` already does the right thing: one `ResizeObserver` per chart element
  calling `chart.resize()`, disconnected on unmount. That covers window resize, sidebar
  collapse/expand and phone rotation, since all of them change the element's box, provided
  the element's size comes from CSS (it must have a non-zero height; ECharts reads
  `clientWidth/Height` at init).
- Considerations for the redesign:
  - An animated sidebar collapse fires the observer every frame, so each frame does a full
    re-layout (SVG). Fine for 5 small charts. If it gets janky, coalesce with
    `requestAnimationFrame`, or resize once on `transitionend`.
  - A chart initialised inside a hidden container (`display:none` tab or collapsed panel)
    gets 0×0. The observer fires when it becomes visible, so the current setup self-heals.
  - Phone rotation: also consider changing option *content* by width (legend position,
    `right` margin of the sankey for labels, fewer axis labels). ECharts 5 has
    `media` queries in `baseOption`/`media: [{ query: { maxWidth: 500 }, option }]`, which
    are re-evaluated on `resize()`. Or recompute in JS.

## 8. How `static/dashboard.js` initialises charts today (actionable)

- `echarts.init(el, null, { renderer: 'svg' })`: default (light) theme, SVG renderer.
- Colours are module-level hex constants (INK2 `#52514e`, MUTED `#898781`, GRID `#e1e0d9`,
  AXIS `#c3c2b7`, a 9-colour PALETTE keyed by Category id, IN/OUT/NET/OTHERS,
  `#fcfcfb` segment borders). `NET = '#0b0b0b'` and `#fcfcfb` would disappear on a dark
  background.
- Five option builders (`spending`, `cashflow`, `trends`, `per_member`, `money_flow`),
  each a pure `data => option`. That makes a theme change easy: rebuild with new tokens and
  `setOption(…, { notMerge: true })`.
- Mount/unmount hooks on `DOMContentLoaded`, `htmx:beforeSwap` (dispose),
  `htmx:afterSettle`, `htmx:historyRestore`; a `ResizeObserver` per chart.
- Suggested shape for the redesign (stays on 5.6.0, no vendor upgrade needed):
  1. Define chart colours as CSS custom properties alongside the UI tokens (light + dark).
  2. Replace the hex constants with a `tokens()` function using `getComputedStyle`;
     pass tokens into each option builder; add `darkMode`, explicit `tooltip`
     `backgroundColor`/`borderColor`/`textStyle`, and `backgroundColor: 'transparent'`.
  3. Keep the parsed `data` per mounted chart (e.g. in the existing `WeakMap`) and on a
     theme change re-run the builder plus `setOption(opt, { notMerge: true })`. No dispose.
  4. Optionally `aria: { enabled: true, label: { description } }` per chart.
- Upgrading to ECharts 6 would buy `setTheme` and a refreshed default look, but since all
  our colours are explicit it adds little for theming and means re-checking the v5→v6
  default changes. Not needed for this redesign.
