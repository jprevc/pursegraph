# Swap feedback

A surface section of the design system. Tokens, type, components and Named Rules live in [`DESIGN.md`](../../DESIGN.md); a "see *X*" names another surface in this folder or a section of `DESIGN.md`.

One convention, kept by one shell script on `htmx:afterSettle` and `htmx:historyRestore`, applies to every HTMX swap. Templates don't patch it per page. Swaps are instant: no crossfade, slide or view transition. The loading treatment above is the feedback, and the charts keep their own entrance.

**Focus, by kind of swap.**
- **Page change** (a sidebar or bottom-tab link, or a link into Transactions or the Dashboard from another page): focus moves to the new page's `<h1>` (`tabindex="-1"`), and the page scrolls to the top.
- **In-place control** (a view tab, period ‹ ›, a filter, a facet, the search, the pager, Show resolved): focus stays on the control that was used, and the scroll position stays. The pager still scrolls to the top of the grid. The change is announced instead. If the control isn't in the new content, focus goes to the region's heading.
- **Something opens** (the drill-down, the chip panel, a Review group, a Rule's detail, a sheet): focus moves to its heading or first control, as each component says. Closing it returns focus to the control that opened it. Anything that opens out of sight, the drill-down especially, is scrolled into view (`block: "nearest"`).
- **Back and forward** (`htmx:historyRestore`): focus moves to the `<h1>`.
- Every scroll is instant, never smooth.

**Announcements.** The shell holds one visually hidden polite live region (`role="status"`) that is never swapped out. The server writes the message: a response sets `HX-Trigger: {"announce": "…"}`, and the shell script clears the region, then sets its text. Failures use the same region, and there is no assertive one. A message names the new state, not the action, in the page's own words and without figures (the tables carry those):
- a view tab or the period: "Cash flow, September 2026 (partial)";
- a Dashboard filter: "Spending, September 2026, Maja's Accounts";
- a facet or the search: "142 Transactions", plus " · page 1 of 6" when there are pages;
- the pager: "Page 3 of 8, 51–75 of 192";
- the drill-down: "Food, September 2026, 37 Transactions".

Saves, failures and Undo keep their own wording (see Transaction row and Review queue). A page change announces nothing, because its focused `<h1>` is read anyway.

**The page title.** Every response that changes what a page shows renders a `<title>`, which htmx applies. The most specific part comes first:
- "Cash flow · September 2026 · Pursegraph";
- "Transactions · Food › Groceries · Pursegraph", naming the filters as the summary line does, cut after two;
- "Review queue (7) · Pursegraph", with the count kept current after every decide;
- "Import · Pursegraph".

The drill-down and panels don't change the title.

**Reduced motion.** There is no movement, but every state change still shows. The donut and charts render in their final state, and the chevron flips without rotating. The More and Filter sheets appear without sliding, with at most a 120 ms opacity fade. The loading line is static (see above), and the dim still happens, because it is state, not motion.
