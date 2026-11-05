# Pursegraph

A family finance overview: household members import their bank statements, every transaction is categorized, and the whole household's money flow is shown together.

## Language

### People

**Household**:
The family as a single unit whose combined finances the app shows. There is exactly one per installation.
_Avoid_: Family, group, tenant

**Member**:
One person in the Household who logs in and imports Statements. Some Members are admins. A Member has a name, which is how the Household sees them (such as in Per Member) and which only an admin sets or changes, and a username, which they log in with and which never changes.
_Avoid_: User, family member, owner, display name

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

**Gap**:
A stretch of days for which an Account that receives Statements has none imported, from its first Coverage day up to today: both the days between its Statements and the days since its last one. Days before an Account's first Coverage day aren't a Gap (it isn't tracked yet), and neither are days after today.
_Avoid_: Hole, missing data, outage

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

**Split**:
A Transaction whose outcome is several Parts instead of one Subcategory, because one payment covered several kinds of spending (or of income). Its Subcategories are all spending or all income. It stays one Transaction: one row on its Statement, one amount. Only a Member splits a Transaction; no Rule or Suggestion does. If a re-parse changes the Transaction's amount, the Split is dropped and the Transaction waits in the Review queue again.
_Avoid_: Breakdown, allocation, child transactions

**Part**:
One piece of a Split: an exact amount placed in one Subcategory. A Split has at least two Parts, each in a different Subcategory and in the Transaction's direction (no Part of a purchase is a Refund), and their amounts add up to the Transaction's to the cent. Each Part counts as spending or income in its own Subcategory.
_Avoid_: Share, portion, line, item

**Rule**:
A Member-defined pattern that assigns a Category to matching Transactions, or marks them as Transfers, often created from a manual correction.
_Avoid_: Filter, mapping, auto-label

**Review queue**:
The Transactions that still need a Member to decide their outcome: those with neither a Subcategory nor Transfer status, and the Transfer sides whose pairing is ambiguous because more than one Transaction is equally close to being their other side.
_Avoid_: Inbox, uncategorized list

**Suggestion**:
A Subcategory proposed for a Transaction in the Review queue, with how sure its Categorizer is (0 to 100 %). A Suggestion at least as sure as the auto-accept threshold sets the Transaction's outcome; any other waits in the Review queue, preselected.
_Avoid_: Guess, prediction

**Categorizer**:
A program outside Pursegraph, such as one that asks an LLM, that fetches the Transactions waiting for a Suggestion and sends Suggestions back. Pursegraph ships none; an admin chooses which ones may connect.
_Avoid_: Suggester, LLM, worker, client

**Webhook**:
A URL Pursegraph calls when Transactions are waiting for a Suggestion, so a Categorizer can fetch them. The call says only how many are waiting.
_Avoid_: Wake hook, callback, notification

**Refund**:
A Transaction that reverses an earlier purchase: money coming in, placed in a spending Subcategory, which reduces spending there. It is not income and is not linked to the purchase.
_Avoid_: Return, chargeback, reimbursement

**Transfer**:
A Transaction that moves money between two of the Household's own Accounts, including between different Members' Accounts and to an Account with no Statements. It counts as neither spending nor income. When both Accounts are imported, its two sides (out of one, into the other) are paired; otherwise it has one side.
_Avoid_: Internal transaction, own-account payment
