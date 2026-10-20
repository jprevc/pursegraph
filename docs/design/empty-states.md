# Empty states and first run

A surface section of the design system. Tokens, type, components and Named Rules live in [`DESIGN.md`](../../DESIGN.md); a "see *X*" names another surface in this folder or a section of `DESIGN.md`.

An empty page always says why it is empty and what fills it. It never only says that there is nothing.

**First run** (the Household has no Statement yet):
- **Get started page:** the Dashboard is replaced by "Get started", titled "Set up the Household", with the muted line "Four steps to the first Dashboard. This page becomes the Dashboard after the first import." A 6px Household Indigo progress pill shows "N of 4 done". Then an ordered list of step cards, at most 760px wide. Each has a 32px numbered circle, a Title, a sentence in Ink 2, a muted 12px "who" caption, and its action at the right.
  1. "Pursegraph is installed and you are its first admin": always done. Its circle shows a check on Indigo Wash, and its title is Muted 500.
  2. "Import a Statement": "Upload a bank Statement: a Sparkasse or N26 PDF, or a Revolut PDF or CSV. Its Account is created from the IBAN on it, so there's nothing to set up first." Who: "Any Member · usually their own bank". Action: Import.
  3. "Invite the other Members": "Each gets a one-time link to choose their password, then imports their own Statements." Who: "Admins". Action: Invite, which opens Members. Done once a second active Member exists. A Member who isn't an admin doesn't see this step.
  4. "Sort the Review queue": "What no Rule or LLM suggestion could categorize waits for a Member to decide. Available after the first import." Not available yet: no card fill or shadow, a dashed Line Strong border, and muted text.
- **The shell in setup mode.** The sidebar offers only what works yet: Get started, Import, and under Manage, Categories, Accounts and Members (for admins). A muted 13px note under Manage says "Transactions, the Review queue and Rules appear after the first import." The phone tab bar has three items: Get started, Import and More. The first import ends setup mode for everyone, and the full shell and the Dashboard return.

**The empty block.** One centred card, the same on every page:
- a 48px Indigo Wash circle with a 22px Indigo Ink icon;
- a 17px 600 heading;
- a muted sentence, at most 52ch;
- the action buttons, centred.

The page keeps its title row. Its copy, page by page:
- **Accounts, before any:** "No Accounts yet" / "There's nothing to add first: importing a Statement creates its Account from the IBAN printed on it. Add one here only for an Account that never gets Statements, such as savings at another bank, so that money moved there counts as a Transfer." Actions: Import Statements, and the ghost button "Add an Account without Statements".
- **Import's Coverage, before any Account:** "No Accounts yet" / "Each Statement adds its Account the first time, from the IBAN printed on it. A Revolut CSV has no IBAN, so you'll be asked which Account it goes into, or to name a new one. Each Member usually imports their own bank's Statements."
- **Members, with only the first admin:** the table with its one row, then the block "Invite the rest of the Household" / "You're the only Member so far. Invite the others: each gets a one-time link to choose their password, and then imports their own bank Statements." Action: Invite a Member.
- **Rules, before any:** "No Rules yet" / "A Rule categorizes matching Transactions at import, or marks them Transfers. The quickest way to make one is "Make a Rule" after you correct a Transaction in the Review queue." Action: Write a Rule.
- **Review queue, all decided:** "Nothing waiting for review" / "Every imported Transaction has a Subcategory or is a Transfer. Any new ones that need a decision arrive with the next import." Action: See Transactions. It is calm, not a celebration.
- **Categories** is never empty, because the list is seeded.

**A Member's first steps.** A Member who owns no Account alone, and so has no Bucket, sees a card above the stat tiles titled "Your first steps, *name*", with a ghost "Hide" button that is remembered per browser. It has two numbered rows:
1. "Import your own Statements": "Sparkasse, N26 or Revolut. Each adds its Account, and you get your own bucket in Per Member." Action: Import.
2. "Help with the Review queue": "N Transactions wait for a Member to decide." Action: Open. This row is shown only while the queue isn't empty.

**Not tracked** (a period wholly before the first Coverage day of every included Account; see Period completeness). The view is replaced by one card:
- **Title:** "No Statements cover February 2026 yet".
- **Sentence:** "Luka's Revolut is tracked from 1 Mar 2026. Before that there are no numbers, not zeros." With several Accounts it names them all: "… are tracked from …", with the earliest date.
- **Coverage timeline:** one row per included Account (name in 13px 500) and one column per month, from the Household's first Coverage month to the running month. A tracked stretch is a 14px Muted pill. An untracked month is a 2px Line Strong dash. The shown period's column takes Indigo Wash, with its month label in Indigo Ink 600. Under it, a muted legend reads "has Statements · no Statements yet · Showing the Accounts this filter includes." No Category hue, because Coverage isn't data.
- **Actions:** "Go to March 2026", the first tracked period; "Show all Members", only when a filter narrows the Accounts; and the ghost "Import an earlier Statement".
