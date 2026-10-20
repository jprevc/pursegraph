# Review queue

A surface section of the design system. Tokens, type, components and Named Rules live in [`DESIGN.md`](../../DESIGN.md); a "see *X*" names another surface in this folder or a section of `DESIGN.md`.

The driver's weekly job: give every waiting Transaction an outcome, then read the month they just completed. The queue is a master–detail pair of cards. A list of groups sits on the left (about 380px), and the chosen group's detail is on the right.
- **Groups.** Transactions in the queue with an identical description form one group ("Bolt.eu ×3"), across Accounts, and are decided together. A Transaction with a unique description is a group of one. Groups are ordered newest first, by their latest date.
- **Title row.** It reads "Review queue" and, under it, a muted line: "12 Transactions in 9 groups still need an outcome". This line, the sidebar badge and the page `<title>` ("Review queue (12)") stay live after every save.
- **The list.** It is headed by a muted "N waiting" and a "Show resolved (n)" checkbox, which is off by default. Each group is a full-width button with hairline dividers:
  - the description (500), with a muted "×3" for a group;
  - the group's total, right-aligned (600, tabular);
  - a 12px muted caption with the hue dot and "Category › Subcategory · 78 % sure", or "No suggestion", or "Transfer · other side unknown".

  The open group takes Indigo Wash with a 3px Indigo inset at its left edge and `aria-current="true"`. With Show resolved on, decided groups stay in place, muted, with a check and their outcome in the caption.
- **The detail.** It shows the context the decision needs:
  - **Head:** the description (600, 18px), the counterparty and kind (muted), and the group total (600, 22px).
  - **Transactions:** one line per Transaction in the group, with date, Account pill (which carries the owner, or Joint) and amount.
  - **Last time:** the outcome given to the most recent Transaction with this description outside the queue, with its date, source and how often it was used. When the suggestion disagrees, a muted line says "The suggestion differs from what was used last time." A new description says "First time this description is seen."
- **Deciding.** A bordered box on the card fill, with no "Something else" button. A different outcome is always one tap away:
  - **With a suggestion:** "Suggested · 78 % sure" (muted, 12px), the outcome as text, and one primary Accept ("Accept for all 3" for a group). A hairline follows, then "Or choose another outcome" (600, 13px) over the chips, already open.
  - **The chips:** "Used last time" comes first, but only when it differs from the suggestion. Then come Most used (leaving out the suggested outcome), each Category (which leads to its Subcategories, as in the chip panel), and Transfer. They use the Transaction row's chip style, at 44px on a phone.
  - **Without a suggestion:** "Choose an outcome" ("… for all 3" for a group) over the same chips.
  - **An ambiguous Transfer:** "Which is the other side of this Transfer?" over the candidate cards (description, date · Account, amount), then "Or something else" and the chips, ending with "Transfer, one-sided".
  - **On touch:** the chips stay; the native select isn't used here, because the detail has room and the chips show the hue dots.
- **After a save.** The group is saved as a whole. The detail stays on it so the follow-ups are in reach:
  - the outcome and its source;
  - "✓ Saved all 3 as … · Undo · Make a Rule for "Bolt.eu" · See them in Transactions" ("See them" only for a group of more than one);
  - a primary "Next: *description* ›" that opens the next waiting group.

  The group leaves the list unless Show resolved is on. Undo puts the whole group back. See them in Transactions opens Transactions filtered to those Transactions, in the URL. Its summary line names the filter "Decided just now · 3", and Clear filters removes it (see Transactions page). Every save, failure and Undo is announced politely ("Saved 3 × Bolt.eu as Transport › Public transport & car sharing. 9 left to review.").
- **No queue-wide bulk accept.** Bulk is per group only, so a 51 %-sure guess never rides along with a 99 %-sure one.
- **A failed save.** It is the Transaction row's line, inside the decide box, and focus stays on the box.
- **Queue clear.** When nothing is waiting, the detail becomes a centred end state:
  - a 48px Indigo Wash circle with a check;
  - "Queue clear" (600, 20px);
  - a muted sentence: "Every Transaction has an outcome, 15 of them decided just now. September 2026 is now complete." It names the most recent month this review made Complete; if none, the sentence ends after "just now".
  - a primary "See September on the Dashboard", and "October so far" for the month in progress.

  The last group's Next becomes "Queue clear · See September on the Dashboard". An empty queue on arrival shows the same state, without "decided just now".
- **Keyboard.** No shortcuts. The groups and chips are real buttons in a sensible tab order. Opening a group moves focus to its heading, and Next moves it to the next group's heading.
- **Phone (≤900px).** The list and the detail are two views. A group opens full width with a "‹ All groups" text button at the top. The Accept button and the chips are 44px, and Accept stretches to full width.
