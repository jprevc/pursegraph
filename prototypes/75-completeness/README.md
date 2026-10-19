# PROTOTYPE: #75 Period completeness (throwaway, never merge)

**Question:** can the Dashboard say how complete a period's numbers are (Gaps, the running month, months before any Coverage) without being loud, in light and dark? The design is DESIGN.md's *Period completeness* section on `feature/75`.

Built on `prototype/64-chart-styling` (variant A, classic axes), so it runs on the real Dashboard views against a scratch database:

```sh
docker compose -f compose.test.yaml up -d      # if the test PostgreSQL isn't already up (port 5433)
prototypes/75-completeness/run.sh              # → http://127.0.0.1:8075/  ana / prototype
```

The seed gives Coverage that shows every month state. Ana's Sparkasse and Marko's N26 are covered from 1 Jan 2026, and the Joint Revolut from 1 Feb, all up to today. Marko's N26 has no Statement for July. So:

| Where | Shows |
|---|---|
| `/cashflow/?period=last12-2026-10`, `/trends/?period=last12-2026-10` | Not tracked Nov–Dec 2025 (no marks, Faint labels, "—" in the table), a Partly tracked January band, a Partial July band, a "So far" October band, and the header line |
| `/spending/?period=2026-01` | Partly tracked on a single month: "Joint Revolut is tracked from 1 Feb 2026" |
| `/trends/` | The new default: the 12 months ending with the last full month |
| `/spending/?period=2026-07` | The header line on a single-month view |
| `/spending/?period=2026-07&member=1` | The same month under Ana's Bucket: complete, so no line |
| `/spending/?period=2026-01` | ‹ disabled at the Household's first Coverage day |

What's prototype-only: `dashboard/completeness.py` (the month states), `_prototype_75` in `dashboard/views.py`, `dashboard/templatetags/proto75.py`, `static/prototype-75/skin.css`, and the `PROTOTYPE (#75)` parts of `static/prototype-64/charts.js` and the templates.

## Findings

- **Raised is invisible as a band** on the white card. Hover is the quietest fill that still reads, in both themes.
- **A `markArea` from a month to itself has no width** on a category axis. The bands are full-height bars on hidden axes of their own, so they don't join Cashflow's bar groups and survive hiding a legend entry.
- **Category trends needs month columns** (`boundaryGap: true`, where #64 had points on the edges) so a band can sit behind a month.
- **January 2026 read Complete but wasn't:** the Joint Revolut isn't tracked until February, so Home was 0 and Money out about half, and nothing flagged it (days before an Account's first Coverage day aren't a Gap). Settled with a fifth state, **Partly tracked**, now shown here.
- **"(partly tracked)" widens the Cashflow table** past its card at 1440 px. The build should let the qualifier wrap under the month.
