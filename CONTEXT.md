# Pursegraph

A family finance overview: household members import their bank statements, every transaction is categorized, and the whole household's money flow is shown together.

## Language

### People

**Household**:
The family as a single unit whose combined finances the app shows. There is exactly one per installation.
_Avoid_: Family, group, tenant

**Member**:
One person in the Household who logs in and imports Statements. Some Members are admins.
_Avoid_: User, family member, owner

### Money

**Account**:
One bank account, owned by one Member or jointly by several, identified by its IBAN (occasionally several, when the bank re-issued it). A Member may own many Accounts. An Account may have no Statements at all (such as a Member's savings account at another bank) and exists then only so that money moved to it is recognised as a Transfer.
_Avoid_: Bank account, wallet

**Bucket**:
The Accounts the dashboard shows as one Member's, in the Per Member view and the Member filter: the Accounts that Member owns alone. Every Account with several owners is in a single Joint bucket instead, never shared out among its owners. A Member who owns no Account alone has no bucket, so is neither offered by the Member filter nor shown in Per Member.
_Avoid_: Share, portion

**Statement**:
One imported bank-statement file (PDF or CSV) covering a period of one Account.
_Avoid_: Import, upload, file

**Coverage**:
The dates of an Account for which Statements have already been imported.
_Avoid_: Imported range, history

**Transaction**:
A single booked movement of money into or out of an Account, as listed on a Statement. Pending, reverted and declined card payments are not Transactions. Its date is the booking date: the day the bank applied it to the balance (Revolut's "Completed" date), not when it was started or its value date. The same Transaction can appear on several Statements of its Account. A bank fee is always a Transaction of its own, even when the bank lists it alongside the payment it belongs to.
_Avoid_: Item, entry, line, movement

**Duplicate**:
A Transaction on a newly imported Statement that falls inside the Account's Coverage and matches one already imported. Duplicates are skipped. Identical-looking Transactions on the same Statement are never Duplicates of each other.
_Avoid_: Double, repeat, overlap

**Category**:
The kind of spending or income a Transaction represents, such as Food or Income. Each Category is either a spending or an income Category. A Transaction is always categorized at Subcategory level; a Transfer has no Category.
_Avoid_: Expense type, label, tag

**Subcategory**:
A finer division of a Category, such as Utilities under Home. Categories have exactly two levels, and every Category has a catch-all Subcategory.
_Avoid_: Child category, sub-type

**Rule**:
A Member-defined pattern that assigns a Category to matching Transactions, or marks them as Transfers, often created from a manual correction.
_Avoid_: Filter, mapping, auto-label

**Review queue**:
The Transactions that still need a Member to decide their outcome: those with neither a Subcategory nor Transfer status, and the Transfer sides whose pairing is ambiguous because more than one Transaction is equally close to being their other side.
_Avoid_: Inbox, uncategorized list

**Refund**:
A Transaction that reverses an earlier purchase: money coming in, placed in a spending Subcategory, which reduces spending there. It is not income and is not linked to the purchase.
_Avoid_: Return, chargeback, reimbursement

**Transfer**:
A Transaction that moves money between two of the Household's own Accounts, including between different Members' Accounts and to an Account with no Statements. It counts as neither spending nor income. When both Accounts are imported, its two sides (out of one, into the other) are paired; otherwise it has one side.
_Avoid_: Internal transaction, own-account payment
