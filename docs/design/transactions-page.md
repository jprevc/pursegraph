# Transactions page

A surface section of the design system. Tokens, type, components and Named Rules live in [`DESIGN.md`](../../DESIGN.md); a "see *X*" names another surface in this folder or a section of `DESIGN.md`.

Every Transaction, narrowed by facets, read 25 at a time. The page answers "find that one" and "show me all of these", and the Dashboard links into it.
- **Header.** The title row, then a 36px search field (300px) for the description, then a summary line. The summary reads "**142 Transactions** · 1.234,50 € out · 2.410,00 € in". When filters are active, it names them ("· September 2026, Food › Groceries") and ends with a "Clear filters" text button. Out and in leave Transfers aside, as the Dashboard does.
- **Layout.** A two-column grid with a 16px gap: the facet rail as a 252px card, and the table card. The rail sticks 16px from the top and scrolls on its own when it is taller than the window.
- **The facet rail.** These groups each have a muted 12px heading, with a "Clear" text button on the right while it is set:
  - Period: All time, then each month newest first, the running one "(so far)".
  - Member: Everyone, then each Bucket (Members, then Joint).
  - Account: All Accounts, then each Account.
  - Outcome: Any outcome, Awaiting review (hatched dot), Transfer (hollow ring), then each Category with its hue dot. A chosen Category opens its Subcategories beneath it, indented 26px.
  - Decided by: Anything, then Rule, Categorizer, Member, IBAN and Pairing, each read as completing the heading. Anything also counts what nothing decided yet and the bank fees set at import. Each option has a one-line muted explanation under its name ("A Rule matched it. Rules are patterns a Member set up, often from a correction."), hidden until the info toggle by the heading (a ghost icon button, 28px, 44px on a phone, `aria-expanded`, "About how each was decided") shows them all; it stays as set across picks. Without JS the explanations show and the toggle doesn't. The summary line names a chosen way "Decided by Member".
  - Amount: a Money segmented control (Any / Out / In), then "Amount between" two inputs.
- **Facet options.** Each is a full-width 14px row (Ink 2) with its count on the right (12px, Muted, tabular). The count is how many Transactions that option would give with every other facet held. Hover takes the Hover fill. The chosen option takes Indigo Wash and Indigo Ink, with `aria-pressed="true"`. A group has one choice; picking the chosen option again clears it, except a chosen Subcategory, which goes back to its Category. An option with a count of 0 is faded to 45% but stays pickable.
- **Applying.** A pick applies at once: HTMX swaps the page, the URL updates, and paging goes back to page 1. The search applies as you type, debounced. A Transaction changed with Change stays in view until the filters change, even if it no longer matches.
- **The table.** Transaction rows, newest first unless sorted otherwise (see Transaction row). The source caption carries the specific reason as its `title` ("Matched the Rule “HOFER” → Food › Groceries", "Maja chose it on 8 Oct").
- **Sorting.** Six sort orders: Newest first (the default), Oldest first, Largest first, Smallest first, A–Z and Z–A. Largest and Smallest go by the size of the amount the row shows, whichever way the money went, so a big payment and a big salary sit together. A–Z and Z–A go by the description, ignoring case and accents. Ties go newest first.
  - **Headers.** Date, Transaction and Amount each have an up and a down arrow after their name (14px icons on 22px ghost targets, Faint): up for Oldest first, A–Z and Smallest first, down for Newest first, Z–A and Largest first. Each arrow is a link labelled "Sort by Amount, Largest first". The chosen arrow takes Indigo Wash and Indigo Ink with `aria-current`, and its header is Ink, with `aria-sort`. Account and Outcome don't sort.
  - **Not a filter.** A sort applies like a pick, back on page 1. Picks, the search, the pager and Clear filters keep it. The summary line, the active-filter badge and the breadcrumb leave it out.
- **Pages.** There are 25 rows a page. A pager at the card's foot over a hairline holds:
  - "‹ Previous" (a 36px button);
  - the page numbers: first, last, and the current one ±1, with "…" between;
  - "26–50 of 192" in Muted;
  - "Next ›".
  The current page takes Indigo Wash and `aria-current="page"`. The ends disable at the first and last page. Changing page keeps the filters and scrolls to the top of the grid.
- **Deep links.** Transactions reads the Dashboard's own query parameters (`period`, `member`, `account`) plus `q`, `outcome` (`unresolved`, `transfer`, `category-<id>`, `subcategory-<id>`), `source`, `dir`, `min`, `max`, `sort` (`oldest`, `largest`, `smallest`, `a-z`, `z-a`; left out for Newest first, and anything else reads as it) and `page`. A link from the Dashboard adds a breadcrumb above the title: "Dashboard › Spending · Food · September 2026". The Dashboard part links back with the same period and filters. The breadcrumb goes once the period, Member or Outcome changes. The Review queue's "See them in Transactions" arrives filtered to the Transactions it just decided: the summary line names that filter "Decided just now · 3", and Clear filters removes it.
- **Empty.** "No Transactions match." with a "Clear the filters" text button. With no Transactions at all, the page keeps today's "Import your first Statement".
- **Phone (≤900px).** The rail leaves the grid.
  - **Sticky bar:** the search field and a "Filter" button with the active-filter count badge, 44px, on the 92% ground tint with a backdrop blur.
  - **Filter sheet:** the button opens the rail as a bottom sheet, like More: 18px top corners, a grip, up to 90vh, scrolling. It is titled "Filter", with "Clear all" on the right, which keeps the sort. Its foot is a sticky full-width 44px primary button, "Show 142 Transactions", which closes it. Picks apply live underneath.
  - **Header bar (≤600px):** the rows are stacked cards there, but the header row stays above them as a bar of the three sortable names and their arrows, spread across, with 26 × 44px arrow targets. Below 380px each pair stacks, up over down.
  - **Pager:** centred, with 40px page buttons; the "26–50 of 192" range is hidden.
