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

**D · Chosen** is B on a fine pointer. On a coarse pointer (`(pointer: coarse)`, faked on desktop by the bar's **touch**), Change / Choose / Something else / Pick the other side is a native select laid over the button, and a pick saves at once.

**Shared by all of them:**

- **Saved.** An inline "✓ Saved as … · Undo" that disappears after 10 s. In the queue it is followed by "· Make a Rule" ([#54](https://github.com/jprevc/pursegraph/issues/54)).
- **Failed save.** "Couldn't save … Nothing changed. Try again"; focus stays on the row.
- **Focus.** After a save in the Review queue, focus moves to the next Transaction still waiting. Elsewhere it stays on the row.
- **Announcements.** Every save, failure and undo goes to one polite live region.
- **Phone.** Below 600 px each row becomes a stacked card: description and amount, then date, kind and Account, then the control at full width with 44 px targets.

## Findings

**Verdict: B, but use the native select on a phone** (variant D). Every Member can change an outcome on reading surfaces, through an explicit Change. On a phone, a pick from the OS picker saves at once, and Undo covers a mis-pick.

- **Gate on `(pointer: coarse)`, not width.** A touch OS picker fires `change` only when a choice is confirmed, so saving on pick can't repeat the P0. A narrow desktop window still has a keyboard, and Chromium fires `change` on each ArrowDown of a closed select, so it keeps the chip panel.
- **The OS picker can't show hue dots or "% sure".** Every option reads "Category › Subcategory", and a "Suggested" group at the top carries the suggestion.
- **Long outcomes wrap.** "Leisure › Subscriptions & digital services" with "86 % sure" pushes "Something else" onto a second line on desktop. The build should give the actions a stable place in the cell, not let them flow after the label.
- **A's chip looked like a select**, and its quiet reading-surface state hid that it was editable. **C's** Save on every row was noisy, and staging was one tap too many for weekly triage.
- **Make a Rule** fits naturally in the "Saved as … · Undo" line, after a save by hand in the queue.

Shots are in `shots/`: A, B and C at desktop, and D at desktop (light and dark) and on a touch phone.
