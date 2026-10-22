# User guide

How Pursegraph behaves, page by page. The vocabulary (Member, Statement, Transfer, Rule…) is defined in [`CONTEXT.md`](../CONTEXT.md).

## Members

Admins manage the Household's Members on the Members page. There is no email server, so creating a Member gives you a one-time invite link to hand over yourself; through it they choose their own password. A password-reset link works the same way. Both links work once and expire after 7 days. Members are never deleted, only deactivated: they can no longer log in but stay on their Statements and Accounts. The last active admin can't be deactivated or lose the admin flag.

## Importing Statements

The Import page takes Sparkasse SI and N26 PDF Statements and Revolut PDF Statements or CSV exports, several files at once; each file is accepted or rejected on its own, in period order. A PDF's Account is found from the IBAN printed on it; for an IBAN no Account has yet (and for a CSV, which has none) the page asks which Account it goes into, or creates one owned by the importing Member. Each Statement is checked (opening balance + all rows = closing balance, and a PDF's rows against its printed money in/out totals and, where printed, row counts) and rejected as a whole if it doesn't add up. The original files are kept in `data/statement-files/`, so they can be re-parsed after a parser fix (see [Re-parsing Statements](operations.md#re-parsing-statements)).

Statements may overlap the Account's Coverage (the dates already imported). The overlapping rows must match the Transactions already imported for those days (date, amount, and running balance where printed); they are then skipped as Duplicates. If they don't match, or the new Statement's opening balance doesn't continue the Account's running balance, the file is rejected. On the first and last day of the existing Coverage, a Statement may add rows the earlier one didn't have, such as a CSV exported in the middle of a day. The Import page shows each Account's Coverage, with its gaps.

## Accounts

Admins manage the Accounts on the Accounts page, linked from the Import page: their name, bank, owning Members (several make a joint Account) and IBANs (several when the bank re-issued one; each belongs to one Account only). An Account with bank "Other" never receives Statements: it is registered only by its IBANs, so that money moved to it, such as to savings at another bank, is recognised as a Transfer. Adding an IBAN also makes the Transactions already imported that are awaiting review and pay to or from it Transfers. An Account keeps its bank, and can't be deleted, while it has Statements; deleting one also deletes the Rules only for it, after a confirmation that says how many. Deactivated Members are offered as owners only of the Accounts they already own.

## Categories and the Review queue

Every Transaction gets an outcome: a Subcategory of the two-level Category list, or Transfer. A default list is seeded on the first migration; admins edit it on the Categories page. Bank fees that a parser splits off their payment are categorized Finance → Bank fees at import, even after that Subcategory is renamed. Everything else waits in the Review queue, where a Member picks the outcome. On Transactions and in the Dashboard's drill-down, each row names its outcome ("Food › Groceries", and what set it, such as "by Rule"), and Change opens the choices under the row: the Household's five most used outcomes, each Category, and Transfer. On a phone, Change opens the phone's own picker. Only picking an outcome saves it; "Undo" puts the previous outcome back for 10 seconds afterwards.

Transactions no Rule categorizes get a Subcategory suggested by the local LLM in the background. A suggestion at least as confident as the auto-accept threshold (0.90 by default) categorizes its Transaction; the rest wait in the Review queue with the suggestion preselected. Admins change the threshold on the LLM suggestions page. Lowering it offers to accept the queued suggestions that now clear it (as if the LLM had accepted them); raising it leaves outcomes the LLM already set alone. After a model or prompt change, "Re-suggest the Review queue" clears the queued Transactions' suggestions so the LLM is asked again. Deleting a Subcategory clears the suggestions pointing at it, so the LLM is asked again; Transactions it already categorized there move to the catch-all like any others.

## Rules

Rules categorize Transactions at import. Any Member manages them on the Rules page. A Rule has conditions (description contains, ignoring case and accents; counterparty IBAN; direction in or out; Account), every one it sets must hold, and an outcome: a Subcategory or Transfer. At import, each Transaction still awaiting review gets the outcome of the first Rule it matches, in the order the Rules page lists them (drag to reorder). After correcting a Transaction by hand, "Make a Rule" opens a new Rule pre-filled from it; a new Rule goes to the top. Saving a Rule offers to apply it to existing Transactions, changing only those awaiting review or categorized by the LLM or a Rule. Deleting a Subcategory moves its Rules to the catch-all.
