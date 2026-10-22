# Charts

A surface section of the design system. Tokens, type, components and Named Rules live in [`DESIGN.md`](../../DESIGN.md); a "see *X*" names another surface in this folder or a section of `DESIGN.md`.

Classic axes, Monarch-style: every chart sits in a card, has a legend, has quiet axes and a table beside it. All charts are ECharts SVG and are built from the same parts:
- **Legend:** top left, 8px circle icons, Ink 2 Inter 500 12px, 16px between items. It scrolls when it overflows. A hidden series' icon turns Line Strong. Clicking an entry hides its series (Trends, Per Member).
- **Value axis:** labels in whole euros ("1.200 €"), Muted 12px. Solid Line gridlines. No axis line or ticks.
- **Category axis:** a Line Strong baseline, no ticks, Muted 12px labels (the month labels the server sends).
- **Tooltip:** the card fill, a Line border, a 10px radius and the Pop shadow, with Ink 13px text. An axis tooltip is a small table: the month in 600, then one row per series (hue dot, name in Ink 2, amount right-aligned in 600, tabular), sorted biggest first where the series are Categories, with a Total row under a hairline. Amounts in tooltips carry cents ("1.234,56 €"), and Net carries its sign. Bars use a shadow pointer in Hover at 60%, and lines use a Line Strong pointer line.
- **Emphasis:** hovering a series focuses it and blurs the rest (lines to 15% opacity, bar segments to 25%).
- **Motion:** a 600ms cubic-out entrance, and none under reduced motion. `aria.enabled` is on for every chart.

Per view:
- **Cashflow:** grouped bars for Money in (the Income Category's hue, darkened until it stands 3:1 off the card, as the light Income hue doesn't) and Money out (Muted, a neutral, since spending as a whole is no Category). The bars are at most 22px wide, with a 4px top radius and a 10% gap. Net is an Ink line, 2px, with 7px circle points ringed in the card colour. Under a Member filter, "To/from other Members" is a dashed Ink 2 line.
- **Category trends:** one 2px line per Category in its hue, with no points until hover (7px circles). Awaiting review is a dashed Awaiting line, since a line can't carry the hatch. The tooltip lists every Category for the month, biggest first, with a Total row.
- **Per Member:** horizontal stacked bars, one per Bucket (at most 28px), Bucket names in Ink 13px 600. Segments are in Category hues with a 1.5px card-coloured border between them, and Awaiting review is hatched. The tooltip lists the Bucket's Categories, biggest first, with a Total row.
- **Money flow (Sankey):** income nodes on the left, Household in the middle, Categories and the balance on the right: "Left over" (money in that wasn't spent, which isn't a claim that it was saved) or "Spent beyond money in". Nodes are 12px wide with a 2px radius and 10px gaps. Each income Subcategory wears its own Income Category's hue, Household is Ink 2, Left over, Spent beyond money in and To/from other Members are Muted, and Awaiting review is hatched. Links take a source-to-target gradient at 30% opacity (60% on hover, with adjacency focus). Income node labels sit to the left of their nodes, Household's sits above it, and the rest sit to the right, each as "name amount" (Ink 2 500, then the amount in Muted, whole euros). Labels that would overlap are dropped, and the table beside the chart still lists every node. When the chart is narrow (a phone), the labels are 11px and Household's shows only its name. The edge tooltip reads "Salary → Household", then the amount and its share of money in.

Every chart rebuilds its options from the CSS tokens and calls `setOption(…, { notMerge: true })` on theme switch, on system scheme change and when its width changes (the existing per-chart `ResizeObserver`), as the donut does.
