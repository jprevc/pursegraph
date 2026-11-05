# Split editor and Part rows

A surface section of the design system. Tokens, type, components and Named Rules live in [`DESIGN.md`](../../DESIGN.md); a "see *X*" names another surface in this folder or a section of `DESIGN.md`.

A Member splits one Transaction into Parts, each an exact amount in its own Subcategory (ADR 0003). The editor is a dialog with a stacked bar; the Parts then show as rows under their Transaction wherever Transaction rows are shown. Decided in #186, variant C (prototype on branch `prototype/186-split-editor`).

## The way in

- **Its own row, under the outcome chips.** Past a hairline, a bordered 36px "Split into Parts…" button with the split icon, then a muted 13px note: "Spread it over two or more Subcategories." It is not a chip among the Categories.
  - **Where:** the chip panel on Transactions and the drill-down (see Transaction row), and the Review queue's decide box, under "Or choose another outcome" (see Review queue). The row stays while a Category's Subcategories are shown.
  - **A group of more than one** in the Review queue gets "Split all 3 into Parts…", which opens the group's table (see A group in the Review queue).
- **On a coarse pointer**, Change's native select ends with a "Split" optgroup holding "Split into Parts…". On a Split Transaction it reads "Edit the Split…", and the select's shown value is "Split into 2 Parts". Picking it opens the dialog as a sheet; the Review queue keeps its chips and the row above.
- **Editing a Split.** Change on a Split Transaction opens the dialog directly, with its Parts, and no chip panel. To replace the Split with one outcome:
  - **On a phone**, pick any single outcome from the native select.
  - **On desktop**, the dialog's foot has a "Choose one outcome instead…" text link (13px, between the status line and Cancel). It closes the dialog and opens the chip panel, as Change does on any other Transaction; picking an outcome there replaces the Split. It is shown only when editing an existing Split, never for a new one or a group, and not on a coarse pointer, where the select already offers the single outcomes.

## The dialog

- **Frame.** Modal, up to 576px wide, on the card fill with the Pop shadow and 14px corners, over a 35% black scrim. Focus moves into it on open and returns to Change on close. Escape, Cancel or a click on the scrim closes it, and nothing is saved.
- **Head.** "Split into Parts" (600, 18px), under it a muted line: description · date · Account ("Mercator · 31 Oct · Ana's Sparkasse"; the Review queue shows the description only). The Transaction's amount sits right (600, 22px, signed, tabular).
- **The bar.** A 12px stacked bar with 4px corners and 2px gaps on the Line fill: one segment per Part in its Category's hue, as wide as its amount. What's still left is hatched in Line Strong, and an overrun shows as an Ink segment. It is `aria-hidden`; the status line says the same in words.
- **Parts.** One row per Part: the hue dot (the hatched Awaiting dot until a Subcategory is chosen), a native select, the amount field, and a remove button.
  - **Select:** "Choose a Subcategory" until chosen, then optgroups per Category, each option "Category › Subcategory". Only Categories of the Transaction's kind (spending or income); no Transfer. A Subcategory another Part already uses is disabled and reads "… (another Part)".
  - **Amount:** right-aligned, 500, tabular, with "€" as a muted suffix inside the field, `inputmode="decimal"`. Unsigned: the sign follows the Transaction. It accepts "61,20" and "61.20".
  - **Remove:** a ghost × ("Remove Part 2"), shown only when there are more than two Parts.
  - **"+ Add a Part"**, a text button under the rows.
- **Starting Parts.** Two: Part 1 is the current outcome (in the Review queue, the Suggestion), Part 2 is empty. A Split reopens with its own Parts.
- **The rest.** The last Part fills itself with what's left, in Muted italic, with no caption: the italic is the only visual sign it wasn't typed. A screen reader hears it in the field's name ("Amount of Part 2, the rest"). Once the Member types in it, it is an ordinary amount. Adding a Part fixes the old last Part at its current amount, and the new last Part takes the rest.

## A group in the Review queue

A group's Transactions have their own amounts, so a group is split as a table: the Parts' Subcategories are chosen once, and each Transaction gets its own amounts. One Save splits them all. Not prototyped (decided after #186's review); the UI ticket checks it at phone width.

- **Head.** "Split 3 × Bolt.eu into Parts", a muted line "3 Transactions · 21,30 € in total", and the group's total on the right.
- **The bar** shows the group's total per Part, built as for one Transaction.
- **Columns are Parts.** The header row holds one native select per Part (the same choices and rules as above), with its hue dot and, past two Parts, a remove ×. "+ Add a Part" adds a column.
- **Rows are Transactions.** Each has its date, Account pill and amount (600, tabular), then one amount field per Part.
- **Filling in.** The last Part's field fills each row with that row's rest, as above. A typed amount in the first row is offered to the untouched fields under it, in Muted italic, because a group is often the same purchase at the same price. Typing in a field makes it the Member's own.
- **Starting Parts.** Part 1 is the group's Suggestion, Part 2 is empty.
- **Save.** "Save 3 Splits". The status line names the first row with a problem by its date and amount: "1 Nov · 6,90 €: 0,50 € left to put in a Part." Every field must be more than 0,00 €, so each Transaction ends with every Part. Ready reads "All 3 add up."
- **After a save.** "✓ Saved all 3 as Splits into 2 Parts · Undo · See them in Transactions", then Next. Undo puts back the whole group.
- **Phone.** One block per Transaction instead of a table: its date · Account and amount on a line, then one amount field per Part, labelled with the Part's Subcategory. The Subcategory selects come first, full width, one per Part.

## Saving

- **The foot.** Over a hairline: the status line, then Cancel and the primary "Save the Split". When editing a Split on desktop, "Choose one outcome instead…" sits before Cancel (see Editing a Split).
- **Save says why it can't.** It stays in place, dimmed to 35% with `aria-disabled`, and `aria-describedby` the status line. The status line shows the first problem, in Ink 500 with the alert icon, and "(n more)" in Muted. Pressing Save then announces it. The problems, in this order:
  - "31,50 € left to put in a Part." or "The Parts come to 4,20 € more than 127,80 €."
  - "Choose a Subcategory for Part 2."
  - "Parts 1 and 2 are both Food › Groceries. Put that amount in one Part."
  - "Part 2 needs an amount." or "Part 2 can't be 0,00 €."
- **Ready.** The status line reads, in Ink 2 with a check, "2 Parts add up to 127,80 €."
- **After a save.** The row swaps in place with the line "✓ Saved as a Split into 2 Parts · Undo", without "Make a Rule". In the Review queue the decide box shows the Split and its Part lines, the same saved line, and Next. Undo puts back the previous outcome. Every save and Undo is announced, as in Swap feedback.

## Part rows

- **The Split Transaction's row.** The outcome reads "Split" (Ink, 500), then a 40×6px mini bar of the Parts' hues (1px gaps, 3px corners), then the "by hand" caption. The Amount column shows the full amount.
- **One row per Part**, always shown, under its Transaction and before any chip panel. A Part row has no date, Account or Change. Its outcome sits in the Outcome column after a 3px inset rule in its Category's hue: the hue dot and "Category › Subcategory" (13px, 500). Its amount sits in the Amount column (13px, 500, Ink 2, signed like the Transaction). The Transaction and its Parts share one hairline, under the last Part.
- **Filtered to an outcome** (Category or Subcategory): the matching Part keeps Ink and its amount goes to 600; the other Parts fade to 50%.
- **In the drill-down**, the Transaction's amount is Muted 400 with a muted "in total" caption, and the matching Part's amount is the one the period counts. The card's footnote adds "For a Split, only its Food Part counts here."
- **Phone (≤600px).** The Part rows are lines inside the Transaction's card, under Change, indented 32px: the outcome on the left, the amount on the right. The card's hairline follows the last Part.

## Phone (≤600px)

- The dialog is a bottom sheet: up to 92vh, 18px top corners, a grip.
- Each Part's select takes the full width, with its amount field under it. Controls are 44px and fields 16px, so iOS doesn't zoom.
- The foot sticks to the bottom; Cancel and Save the Split share its width.
