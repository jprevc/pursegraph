# Several choices in one Transactions facet

On the Transactions page, each facet group (Period, Member, Account, Outcome, Decided by) holds one choice. Picking an option replaces that group's choice, and picking the chosen option again clears it. Ticking several values in the same group, such as August and September, isn't supported.

## Why this is out of scope

"A group has one choice" is a deliberate rule in `docs/design/transactions-page.md`. The model behind the page is built on it, and allowing several choices would change more than the rail:

- **Period** is one `Period`: a single date range named by one `period` token, which the Transactions page shares with the Dashboard (deep links, the breadcrumb back). A set of months, possibly with gaps between them, has no such token. It would need a new query shape that the Dashboard can't show.
- **Outcome** totals add up the Parts of a Split for *one* Category or Subcategory, so the page agrees with the Dashboard's numbers. With several Categories, or a Category plus one of its own Subcategories, you'd have to decide how a Split with Parts in more than one of them is counted, and those totals would drift from what the Dashboard shows.
- **Member** is the Dashboard's single-bucket filter, and its Transfers-to-other-Members logic depends on there being one bucket.
- How picking works would change from "replace" to "toggle" across the rail and the phone's Filter sheet. The summary line, the counts and the deep links would all need new rules.

All of that touches the Dashboard's filter model and the page's totals. A smaller change can't deliver it, and a "two months" view isn't worth that cost.

Two things already cover most of the need:

- A chosen period of another unit (a quarter or a year, from the Dashboard's stepper) shows on top of the Period group, so neighbouring months can be viewed together.
- The Account filter already accepts several Accounts from a link (`?account=1&account=2`), as the Dashboard's filters do.

Clicking a chosen option to remove it, which the same request asked for, already works: picking the chosen option again clears the group.

## Prior requests

- #212: "Add option to select multiple filtering values in the same group"
