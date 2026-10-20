# PROTOTYPE: #85 Transactions page (throwaway, never merge)

**Question:** what does the Transactions page become? The ticket asks five things:

- which filters it gets (date, Member, Category, amount);
- paging or "load more";
- how the Dashboard deep-links in;
- how the source labels (Rule, LLM, IBAN, by hand) are explained;
- the phone layout.

It builds on the #83 row: text plus Change.

```sh
python3 -m http.server 8085      # from the repo root
# → http://localhost:8085/prototypes/85-transactions-page/?variant=A&page=transactions
```

The page is static, inside the #63 shell (variant B), and uses the #83 row (variant D). The data is about 190 synthetic Transactions from 1 Jul to 17 Oct 2026, across three Accounts (Maja, Luka, Joint). It has a handful of Awaiting review rows, paired and IBAN Transfers, and Rule, LLM and by-hand outcomes. Saves are stubbed (400 ms). A saved row stays in view until the filters change, even when it no longer matches.

**Navigating it.**

- ‹ › on the black bar, or ← / → while nothing has focus, switch the variant. Filters carry across variants.
- The bar also has **phone** (a 390 × 844 frame), **touch** (fakes a coarse pointer for the #83 native select), the theme and **reset**.
- The sidebar's **Dashboard** is a stand-in for September 2026, with its own Member filter. Each Category, Awaiting review and the Money in tile link into Transactions. That is the deep link.

| | A · Filter bar + Show more | B · Facet rail + pages | C · Search tokens + endless months |
|---|---|---|---|
| **Filters** | The Dashboard's sticky bar grows a period stepper (Month / All time), Member, Account and Outcome (Category or Subcategory, Awaiting review, Transfer). **More** holds Decided by, Money in/out and an amount range. Active filters echo as removable chips, with the count and totals. | A left rail of facets: Period, Member, Account, Outcome (picking a Category opens its Subcategories), Decided by, Amount. Every option shows **how many it would give**, keeping the other filters. A summary line names what's active. | One big search box reads words as filters: `food sep maja over 50 hofer`. The words cover months, Members, Accounts, Categories, one-word Subcategories, `awaiting`, `transfer`, `rule`/`llm`/`iban`/`hand`/`paired`, `in`/`out`, `over N`/`under N` and `>N`/`<N`. The rest is text. The reading is echoed as removable tokens, and typing suggests completions. |
| **Length** | Grouped by day (day header and day net). **Show 50 more**, with "Showing 50 of 192". | A flat table with a Date column, 25 per page, numbered pages (Newer / 1 2 … 8 / Older), and "26–50 of 192". | Month sections, each with a sticky header carrying that month's count and totals. Rows load on scroll, ending with "That's everything". |
| **Deep link** | The same query params as the Dashboard (`period`, `member`), plus `cat` / `dir`. A "‹ Spending · Food · September 2026" link above the title goes back. | The same params. A breadcrumb reads "Dashboard › Spending · Food · September 2026". | The same params, turned into the query words (`food sep`), so you can see and edit what was carried in. |
| **Source labels** | The caption ("by Rule") is a dotted-underline button. It opens a popover saying exactly why: "Matched the Rule “HOFER” → Food › Groceries", "Maja chose it on 8 Oct", or the IBAN/paired account. It links to See the Rule or Make a Rule. | The Decided-by facet explains each source once, in the rail. Captions carry the specific reason as a hover title. | A "How outcomes are decided" legend above the list explains each source once. Captions carry the specific reason as a hover title. |
| **Phone** | Search, then period, then Month + **Filters (n)**, which opens a bottom sheet with "Show N Transactions". The chips scroll sideways. The #83 stacked cards sit under day headers. | Search + **Filter (n)** in a sticky bar. The rail becomes a tall sheet with a sticky "Show N Transactions". The pager is centred. | The search box stays sticky, and tokens wrap under it. Month headers stick below it. |

Totals ("out / in") leave out Transfers, as the Dashboard does.

## Findings

**Verdict: B, the facet rail with numbered pages**, as built. Its DESIGN.md section, *Transactions page*, is on `feature/85`.

- **Filters:** Period, Member, Account, Outcome (Category, then its Subcategories), Decided by and Amount, as a rail. Each option shows its count with the other filters held. There is one choice per facet.
- **Length:** 25 per page, with numbered pages. "26–50 of 192" says where you are.
- **Deep link:** the Dashboard's own query params, plus `outcome`. A breadcrumb leads back.
- **Sources:** the Decided facet explains each one. A caption's hover title gives the specific reason.
- **Phone:** the rail becomes a sheet with "Show N Transactions".

What the other variants raised, as they were left:

- **A's per-row popover** ("Matched the Rule “HOFER”") was the only way to see a specific reason on touch or keyboard. B's hover title isn't reachable there.
- **C's query words** were not taken: discoverability for the least technical Member, and translation.

The questions the review weighed:

- **The filter count.** Is the A bar too crowded at 1,280 px with all four selects and More? Is B's rail worth 252 px of width beside a 5-column row?
- **Per-option counts (B).** Do they earn their cost? They need a count query per facet option on every change.
- **Paging (B) vs Show more (A) vs endless (C).** Consider the back button, and finding "that thing from August".
- **Source explanations.** Is it A's specific popover, the general legend or rail (B, C), or both?
- **C's query words.** Are they discoverable for the least technical Member, and would they need translating (sl)?

Shots are in `shots/`.
