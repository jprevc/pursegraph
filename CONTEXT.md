# Pursegraph

A family finance overview: household members import their bank statements, every transaction is categorized, and the whole household's money flow is shown together.

## Language

### People

**Household**:
The family as a single unit whose combined finances the app shows. There is exactly one per installation.
_Avoid_: Family, group, tenant

**Member**:
One person in the Household who logs in and imports Statements.
_Avoid_: User, family member, owner

### Money

**Account**:
One bank account, owned by one Member or jointly by several.
_Avoid_: Bank account, wallet

**Statement**:
One imported bank-statement file (PDF or CSV) covering a period of one Account.
_Avoid_: Import, upload, file

**Transaction**:
A single movement of money into or out of an Account, as listed on a Statement.
_Avoid_: Item, entry, line, movement

**Category**:
The kind of spending or income a Transaction represents, such as Food or Income. A Transaction is always categorized at Subcategory level; a Transfer has no Category.
_Avoid_: Expense type, label, tag

**Subcategory**:
A finer division of a Category, such as Utilities under Home. Categories have exactly two levels, and every Category has a catch-all Subcategory.
_Avoid_: Child category, sub-type

**Rule**:
A Member-defined pattern that assigns a Category to matching Transactions, often created from a manual correction.
_Avoid_: Filter, mapping, auto-label

**Review queue**:
The Transactions that still need a Member to confirm or choose their Category.
_Avoid_: Inbox, uncategorized list

**Refund**:
A Transaction that reverses an earlier purchase. It carries that purchase's Category and reduces spending there; it is not income.
_Avoid_: Return, chargeback, reimbursement

**Transfer**:
A Transaction that moves money between two of the Household's own Accounts. It counts as neither spending nor income.
_Avoid_: Internal transaction, own-account payment
