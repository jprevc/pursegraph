# Transaction row

A surface section of the design system. Tokens, type, components and Named Rules live in [`DESIGN.md`](../../DESIGN.md); a "see *X*" names another surface in this folder or a section of `DESIGN.md`.

One row is shared by Transactions and the drill-down. The Review queue decides outcomes in its own detail pane (see Review queue), with the same outcome text, chips and save feedback. The row's columns are Date, Transaction (500, with a muted caption for the kind), Account (pill), Outcome, and Amount (right-aligned, 600, tabular). Rows have hairline dividers and a Raised hover. Every Member can change an outcome on every surface, always through an explicit action.
- **The outcome is text, not a control.** It reads as the Category's hue dot, then "Category › Subcategory", with the Category in Muted, the › in Faint and the Subcategory in Ink at 500. It always names its Category, so the eight "Other" catch-alls never read alike. A Transfer gets a hollow Muted ring, and Awaiting review gets the hatched dot. A muted source caption follows ("by Rule", "by LLM", "by hand", "by IBAN", "paired").
- **Actions on reading surfaces.** Transactions and the drill-down show a "Change" text button in Indigo Ink.
- **Action layout.** The actions keep a fixed place at the end of the cell. A long outcome ("Leisure › Subscriptions & digital services") wraps its own label and never pushes the actions onto a new line.
- **Picking with a fine pointer: the chip panel.** Change opens a panel in a full-width row under the Transaction, on the Raised fill.
  - **Title row:** "Choose an outcome for *description*", with a Cancel text button.
  - **Chips:** "Most used" chips (the Household's five most-used outcomes, each "Category › Subcategory"), then one chip per Category (hue dot and name), then Transfer. A Category chip swaps the chips for its Subcategories, with "‹ All Categories" to go back.
  - **Chip style:** 36px pills with the card fill and a Line Strong border. The current outcome's chip takes Indigo Wash with an Indigo border.
  - **Focus:** only one panel is open at a time. Opening it moves focus to the first chip; Escape or Cancel closes it and returns focus to the button that opened it.
- **Picking with a coarse pointer: the native select.** Under `(pointer: coarse)`, Change is a transparent native `<select>` laid over the button, so a tap opens the OS picker. The select is 16px, so iOS doesn't zoom.
  - **Options:** each reads "Category › Subcategory", in optgroups: Most used, each Category, then Transfer.
  - **Gate:** the pointer, not the width. A narrow desktop window still has a keyboard, so it keeps the panel.
- **What commits.** Only a deliberate choice: Accept (in the Review queue), a tap on a Subcategory, Most used or Transfer chip, a pairing card, or a confirmed pick in the OS picker (a touch picker fires `change` only on confirm). Arrow keys never save. Without JS, each row is a form with a select and a Save button.
- **After a save.** The row swaps in place, and a muted line appears under the outcome: "✓ Saved as Category › Subcategory · Undo". The line goes after 10 s. Undo restores the previous outcome and its source.
- **A failed save.** The row stays as it was and says so in Ink with an alert icon: "Couldn't save *outcome*. Nothing changed. Try again". It uses no red.
- **Focus after a save.** Focus returns to the row's Change. Every save, failure and Undo is announced politely.
- **Phone (≤600px).** Each row is a stacked card:
  - description and amount on the first line;
  - date, kind and Account in a muted caption;
  - the outcome, with Change under it at 44px.
