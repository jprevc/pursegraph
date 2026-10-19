# PROTOTYPE: #83 Transaction row and outcome control (throwaway, never merge)

**Question:** how should the shared Transaction row and its outcome control look and behave in the new direction? It is used in the Review queue (editing), Transactions and the Dashboard drill-down (reading). The ticket asks about the commit model (the P0), naming each outcome "Category › Subcategory", reading versus editing, save feedback and the phone card.

```sh
python3 -m http.server 8083      # from the repo root
# → http://localhost:8083/prototypes/83-transaction-row/?variant=A&page=review
```

The prototype is a static page inside the #63 shell (variant B). Saves are stubbed: each takes 400 ms, and they all fail while **saves fail** is on.

**Navigating it.** The sidebar switches between the three surfaces. ‹ › on the black bar, or ← / → while nothing has focus, switch the variant. The bar also has:

- **phone**, which loads the same page in a 390 × 844 frame so the real media queries apply;
- **saves fail**, which makes every save fail;
- the theme;
- **reset**.

It also shows the last screen-reader announcement.

| Variant | Outcome shown as | How you change it | What commits |
|---|---|---|---|
| **A · Chip + search picker** | A chip, "● Food › Groceries". A suggestion has a dashed border plus Accept and "% sure". On reading surfaces the chip is quiet: borderless until hover or focus. | A searchable listbox, with sections Suggested, Most used, each Category, then Transfer. Ambiguous pairings come first. On a phone it is a bottom sheet titled with the Transaction. | A click, or Enter. Arrow keys only move the highlight. |
| **B · Text + Change, chip panel** | Text plus its source ("by Rule"). In the queue: Accept / Something else, or Choose. | A panel under the row: Most used chips, then Category chips leading to Subcategory chips. Ambiguous pairings show as cards. | A tap on a Subcategory chip. |
| **C · Native select + Save** | A native select whose options read "Category › Subcategory", with Most used on top. | The OS picker, which is native on a phone. | Save / Accept, or Enter. Changing the select only stages it ("Not saved yet"). Works without JS. |

**Shared by all three:**

- **Saved.** An inline "✓ Saved as … · Undo" that disappears after 10 s. In the queue it is followed by "· Make a Rule" ([#54](https://github.com/jprevc/pursegraph/issues/54)).
- **Failed save.** "Couldn't save … Nothing changed. Try again"; focus stays on the row.
- **Focus.** After a save in the Review queue, focus moves to the next Transaction still waiting. Elsewhere it stays on the row.
- **Announcements.** Every save, failure and undo goes to one polite live region.
- **Phone.** Below 600 px each row becomes a stacked card: description and amount, then date, kind and Account, then the control at full width with 44 px targets.

## Findings

_To be filled in from the session's verdict._
