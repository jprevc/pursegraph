# Import and the Accounts board

A surface section of the design system. Tokens, type, components and Named Rules live in [`DESIGN.md`](../../DESIGN.md); a "see *X*" names another surface in this folder or a section of `DESIGN.md`.

Import is the Household's Accounts on one shared time axis, with Statements dropped onto the page. Results land on the row of the Account they went into. Accounts (under Manage, admins only) is the same board. Both pages are desktop only.

**Choosing files.**
- **Header:** the title row reads "Import", with "Choose files" (an upload icon plus text) as its primary action.
- **Drop strip:** a slim card under the header with a 1.5px dashed Line Strong border. It holds an upload icon, "Drop Statements anywhere on this page." in Ink 600, and the supported formats in Muted ("PDF Statements from Sparkasse SI, N26 and Revolut, and Revolut CSV exports. Several at once.").
- **Drop target:** the whole page.
- **Without JS:** the input stays a real `<input type="file" multiple>` in a form with `method` and `action`, so it posts as today.
- **Staging:** once files are chosen, the strip lists one row per file: a file icon, the name, the size, "Ready" and a ghost × to remove it. Below the list: "Each file lands on its Account's row below.", Cancel, and the primary "Import N files".

**Progress.** The import stays one POST, as today. The view checks every file and then imports them oldest first across the batch, so there is no per-file progress.
- **Upload:** a 6px Household Indigo bar (`role="progressbar"`, `aria-valuenow`) labelled "Uploading 7 files", with the percentage at the right.
- **Checking:** then an indeterminate bar, "Checking and importing 7 Statements · oldest first, so each one's Duplicates are found". Each staged row shows a 14px spinner.
- **Announcements:** the start, the end of the upload and the result are announced politely.

**Result banner.** A card holds a check icon and the headline, "173 Transactions imported from 3 files" (Ink 600). The headline is focused (`tabindex="-1"`) and announced. Under it, a muted line reads "44 wait for review · 1 file needs an Account · 2 files weren't imported · 1 was already imported". A primary "Review now →" at the right opens the Review queue.

**Needs you.** A card titled "Needs you · 3 files" lists, for each file that needs the Member:
- a 170px left column with its status and file name;
- on the right, either the Choose-the-Account form or the rejection (see Import copy).

**Status words.** Imported, Needs an Account, Not imported and Already imported, each a 16px icon plus a 600 13px word in Ink. The icon (check, question, alert, equals) carries the difference, never a red, green or Category hue (the No Verdict Rule).

**Already imported** is not a failure. It gets one muted line under the tray: "sparkasse_2026-08.pdf went into Maja's Sparkasse on 3 Sep 2026; nothing changed."

**Board.** One card. The header row holds "Account" above a 250px column. To its right is the axis, from the Household's first Coverage day to today: years as 600 Ink 2 labels at January, quarter months in Muted 12px, and quarter hairlines through every track.

Each row has two parts:
- **Who:** the Account name (600), "bank · owners" in Muted 13px (Member names, never usernames), and two links: "20 Statements" (a disclosure) and, for admins, "Edit".
- **Track:** 30px high.
  - **Covered stretches** are 22px Coverage Slate bars with a 5px radius.
  - **The stretch this import added** is Household Indigo.
  - **Gaps are outlined slots:** a card fill, a 1.5px Ink 2 border, and an 11px 600 label naming the month ("Jul") or the length ("49 d") when it fits. Each slot is a button, `aria-label` "Gap 1–31 Jul 2026: import a Statement".
  - **Today:** a 1.5px Ink rule at the right end marks it.

Under the track, a 13px caption line names the result and the Gaps in text:
- the result: "New: 1–30 Sep 2026 · 64 Transactions, 20 to review", in Indigo Ink. It is a disclosure that opens the full domain counts (see Import copy) under the row.
- every Gap in Muted: "Gap 1–31 Jul 2026", or "Gap 1 Sep – 19 Oct 2026, since the last Statement";
- "Tracked from 1 Jan 2025".

A visually hidden ordered list reads the whole timeline ("Covered 1 Jan 2025 – 31 Aug 2026", "Gap …"). Gaps include the stretch since the last Statement (CONTEXT.md). Completeness uses neither the hatch nor the dash, so the text is the non-colour cue. An Account that takes no Statements reads "Takes no Statements: money moved to its IBAN counts as a Transfer." in place of a track.

**Gap action.** Activating a Gap shows a notice above the drop strip and focuses "Choose files": "For Luka's N26: a Statement covering 1–31 Jul 2026. Download it from N26 and drop it here." It can't preselect the Account, because the Statement's IBAN decides it.

**Statements.** "20 Statements" expands a table under the row, on Raised, newest first, with columns Period, Format, Transactions, Imported (date and Member name), and Delete. Delete appears for admins and for the Member who imported the Statement. It confirms with its consequences, as today:
- how many Transactions appear on no other Statement and are deleted with it;
- that the Coverage shrinks, so the period becomes a Gap;
- how many outcomes set by hand are lost.

**Accounts page.**
- **Header:** the same board without the drop strip, titled "Accounts", with "New Account" as the primary action and a muted line, "Each Account with its Coverage, as on Import."
- **Edit** expands the row in place. The form sits on the left: Name, Bank (with the hint that "Other" is for an Account whose Statements aren't imported), Owners as Member-name checkboxes ("Several owners make it a joint Account, shown in the Joint bucket."), and IBANs.
- **Delete or why it's missing** sits on the right:
  - with Statements: "Can't be deleted while it has 20 Statements. Delete them first."
  - without: "Delete Account", which confirms how many Rules only for this Account go with it.
- **Save** collapses the row and shows "✓ Saved" beside the Account name (`role="status"`, announced).
- **Members who aren't admins** see Import's board without Edit.

## Import copy
Each rejection says the cause first, then the next step, then the evidence behind a disclosure. The heading is the cause. "Nothing from this file was imported" is said once. "Keep the file" appears only where a fix to the reader could help, never for a wrong file.

| Cause | Heading | Then | Disclosure |
|---|---|---|---|
| Rows don't match the printed totals, or the balances don't add up | A payment seems to be missing | "The Statement lists 31 payments out, totalling 2.652,45 €. Pursegraph read 30 of them…: 20,00 € short." Keep the file: the N26 reader needs a fix. Until then, Luka's N26 has a Gap for 1–31 Jul 2026. | Show the reconciliation: Opening balance, All rows read, added up, So the closing balance should be, The Statement prints; then Printed on the Statement / Read by Pursegraph totals; then the rows read |
| Parser couldn't read it | Not a Statement Pursegraph can read | Download the Statement from your bank's website or app; scans and photos can't be read. If it is a downloaded Statement, keep it: the reader may need a fix. | What the reader found |
| Not PDF or CSV | Not a PDF or CSV file | Download the Statement as a PDF (or a CSV from Revolut) | none |
| Opening balance ≠ the Account's | Doesn't follow on from what's imported | A Statement in between may be missing, or a balance was misread | Show the balances |
| Rows inside the Coverage differ | Disagrees with what's already imported | The bank may have re-booked or reverted a payment since the earlier export | Show the days that differ |
| Bank ≠ the chosen Account's | Wrong bank for that Account | Import it again and choose an N26 Account, or a new one | none |
| IBAN on another Account | This Statement belongs to Joint Revolut | Import it again without choosing an Account: it goes there by its IBAN | none |
| Account takes no Statements | Maja's savings takes no Statements | Choose another Account, or ask an admin to change its bank | none |

- **The mismatched figure** in a disclosure is marked by 700 weight and a 2px Ink underline, not by colour.
- **Choose the Account:** the first sentence depends on whether the Statement carries an IBAN.
  - **A PDF with an unknown IBAN:** "An N26 Statement, 1–30 Sep 2026. Its IBAN DE89 … isn't on any Account yet. Pick the Account it belongs to, or create one. The IBAN is added to it, so next time the Statement goes there by itself."
  - **A Revolut CSV, which has no IBAN:** "A Revolut CSV export, 1 Jan – 14 Oct 2026. It carries no IBAN, so pick the Account it belongs to, or create one."
  - Then the Accounts of that bank as bordered radio rows, "A new Revolut Account" (Name, Owners), and "Import into this Account".
- **Domain counts:** "64 Transactions imported" and "No Duplicates" or "22 Duplicates skipped: already imported from an earlier Statement". Also, where they apply: "4 card payments still pending or declined, left out" (never "non-completed rows"), "3 Transfers recognised: 2 paired, 1 one-sided", "1 categorized Transaction is now a Transfer", "1 Transfer has several possible other sides, so it waits in the Review queue", "41 categorized by Rules" and "20 wait for suggestions and review · Review queue". Zero counts read "No …" in Muted.
