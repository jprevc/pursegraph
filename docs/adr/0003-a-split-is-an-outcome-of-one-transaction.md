---
status: accepted
---

# A Split is an outcome of one Transaction, not several Transactions

One payment sometimes covers several kinds of spending, such as a hypermarket receipt that is partly Food › Groceries and partly Home › Household goods (#174). We let a Member **split** it: the Transaction stays one Transaction, one row on its Statement with one amount, and its outcome is either one Subcategory, Transfer, or a **Split** into **Parts**, each an exact amount in its own Subcategory, adding up to the Transaction's amount to the cent. The bank fact and the Household's reading of it stay apart: Duplicates, Transfer pairing, re-parse, Rules and Suggestions keep working on whole Transactions, and only what counts as spending or income reads the Parts.

## Considered Options

- **Child Transactions replacing the original.** Rejected because a Transaction is what a Statement lists: children that no Statement lists would break Duplicate matching on re-import and re-parse, and every count of Transactions would have to skip the hidden original.
- **Copies with partial amounts, as bank fees are split off at import.** Rejected for the same reason, and because a bank fee is a separate bank fact, while a Split is only the Household's decision about one.
- **Percentages instead of amounts.** Rejected because rounding would make the Parts drift from the Transaction's amount.

## Consequences

- Every aggregate of spending or income reads a Split's Parts instead of the Transaction's Subcategory, so there are two places a Transaction's money can be counted from.
- Only a Member makes a Split. A Rule or a Categorizer still sets one Subcategory, a Split is a manual outcome they never overwrite, and Split Transactions aren't sent to Categorizers as examples, since one Subcategory can't describe them.
- Parts must stay consistent with their Transaction: deleting a Subcategory merges Parts that end up in the same catch-all (a Split left with one Part becomes a plain outcome), and a re-parse that changes the amount drops the Split and puts the Transaction back in the Review queue.
