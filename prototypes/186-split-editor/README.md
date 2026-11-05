# PROTOTYPE: #186 Split editor and Part rows (throwaway, never merge)

**Question:** how do the Split editor and the Part rows look and behave, on desktop and on a phone? (Map: #185; settled rules in ADR 0003.)

```sh
python3 -m http.server 8186 --bind 127.0.0.1     # from the repo root
# → http://127.0.0.1:8186/prototypes/186-split-editor/?variant=A&page=transactions
```

It uses the app's own `static/pursegraph.css`. Changes stay in memory. The black bar switches the variant (‹ ›, or ← / → while nothing has focus), the host page (Transactions, Review queue, Drill-down), a 390px phone frame that behaves as a touch screen (Change is the native select), the theme, and a reset. The Outcome facet on Transactions shows the filtered emphasis.

| Variant | Editor | Remainder | Part rows |
|---|---|---|---|
| **A · Inline lines** | In the chip panel (and the Review queue's decide box): one line per Part, a Subcategory button that opens the chips under it (a native select on touch), an amount | The last Part is never typed: it is always "the rest" | A tree line from the Transaction, "Part 1 of 2", outcome and amount in their own columns; split icon on the Transaction |
| **B · Subcategories, then amounts** | Step 1 toggles Subcategories with the same chips (a tray shows the picks); step 2 types every amount. A bottom sheet on touch | Big "€X left of €T"; each Part offers "Add the €X left" | Compact lines under the description; the matching Part takes Indigo Wash; a pie dot on the Transaction |
| **C · A dialog with a bar** | A modal dialog (a full sheet on a phone) with a stacked bar in the Parts' hues, a native select and an amount per Part | The last Part fills itself with the rest until you type in it | The Part's hue as a rule; non-matching Parts fade; a mini bar on the Transaction |

**Shared by all three:**

- Split is a dashed "Split into Parts…" chip after Transfer; on touch it is the last option of the native select ("Edit the Split…" on a Split). Change on a Split opens its editor directly.
- Part 1 starts as the current outcome (or the Suggestion in the Review queue).
- Save is never silently disabled: the line beside it says why ("31,50 € left to put in a Part.", "Choose a Subcategory for Part 2.", "Parts 1 and 2 are both Food › Groceries…").
- Only Subcategories of the Transaction's kind; a Subcategory used by another Part is disabled ("Already Part 1").
- In the Review queue, Split is offered only for a group of one; a saved Split has Undo but no "Make a Rule".
- In the drill-down the Transaction's full amount is muted and the matching Part's amount is the counted one.

## Findings

**Verdict: C**, with two changes from the user's review:

- The "€" now sits inside the amount field on every row, the auto-filled one included: the "the rest" caption had widened the column and pushed the "€" outside the field.
- Split is no longer a chip next to the Categories. It has its own row under the outcome chips, past a hairline: a "Split into Parts…" button and "Spread it over two or more Subcategories." The Review queue's decide box has the same row.

Recorded in `docs/design/split-editor.md`.
