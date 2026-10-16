# PROTOTYPE: #64 Chart styling (throwaway, never merge)

**Question:** how do the Dashboard charts look and behave in the new direction (DESIGN.md)? This covers the palette per Category, axes and gridlines, tooltips, number formatting, the Money flow Sankey, the cashflow and trend lines, and how the charts react to a theme switch.

The prototype runs on the real Dashboard views, with real queries and drill-downs, against a scratch database of synthetic data. Run it like this:

```sh
docker compose -f compose.test.yaml up -d      # if the test PostgreSQL isn't already up (port 5433)
prototypes/64-chart-styling/run.sh             # → http://127.0.0.1:8064/  ana / prototype
```

`run.sh` drops and re-creates `pursegraph_proto64_wipe_me`, migrates it, seeds it with `seed.py`, and serves the app with DEBUG on. With DEBUG on, the Dashboard loads `static/prototype-64/charts.js` and `skin.css` in place of `dashboard.js`. The skin is just enough of DESIGN.md's tokens to judge the charts on the new grounds; the shell itself is #63's job.

Switch variants with `?variant=A|B|C`, the ← / → keys, or the floating bar. The bar also switches the theme between Light, System and Dark. Cashflow needs a longer period to say anything: use `?period=last12-2026-10`.

| | A · Classic axes | B · Direct labels | C · Small multiples |
|---|---|---|---|
| Cashflow | Grouped In/Out bars and a Net line, with a legend and a shaded axis tooltip table | Diverging bars (In above zero, Out below it), Net as labelled dots, no legend | Net as neutral bars, with In and Out as area lines it's the gap between |
| Trends | Every line on one chart, with a legend and a sorted axis tooltip with a total | Every line on one chart, each named at its end (only lines with ≥ 4 % of the spending), hover isolates a line | One small area chart per Category, all on one shared scale |
| Per Member | Stacked bars per Member, with a legend | Stacked bars with segment names inside them, a total at each bar's end, no axis | Categories down the side, Members side by side in neutral shades, Joint hatched |
| Money flow | Gradient links, thin nodes, "name amount" labels | Links in the target's hue (incoming links in the source's), thick nodes, two-line labels | Vertical, neutral links that take the target's hue on hover, shares as % |
| Spending | The settled donut from #62 in every variant, as the colour anchor | | |

These are shared by every variant: hue = `cat-((Category id − 1) mod 10)`, with Income Subcategories wearing Income's hue; Awaiting review in grey plus a hatch, or dashed as a line; sl-SI figures (`1.234,56 €` in tooltips, whole euros or compact on axes); a card-styled tooltip; and charts that rebuild from the CSS tokens with `setOption(notMerge)` on every theme or system-scheme change.
