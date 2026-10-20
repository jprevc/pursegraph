# PROTOTYPE: #86 Import, Accounts and Coverage (throwaway, never merge)

**Question:** how do Import, Accounts and Coverage look and read in the new direction (desktop only)? The ticket covers:

- per-file outcomes, multi-file progress, and a summary that links to the Review queue;
- cause-first rejection copy;
- Coverage gaps that offer an action, with text for screen readers;
- Accounts: owner names, save confirmation, and why Delete is missing;
- keeping the trust ritual that already works.

```sh
python3 -m http.server 8086      # from the repo root
# → http://localhost:8086/prototypes/86-import-accounts/?variant=A&page=import
```

The prototype is a static page inside the #63 shell (variant B). The upload is stubbed as **one POST, like the real view.** The view checks every file first, then imports them oldest first, so each one's Duplicate check sees the Coverage the earlier ones left. Honest progress is therefore upload progress, then an indeterminate "Checking and importing" phase, not per-file streaming.

**Navigating it.** "Choose files" (or dropping anything on the page) stages a synthetic batch of 7 files. ‹ › on the black bar, or ← / → while nothing has focus, switch the variant. The bar also has:

- **page**, which switches between Import and Accounts;
- **jump to results**;
- **every rejection**, which adds one file for each other rejection cause, so all the copy can be read in place;
- **admin/member**;
- the theme;
- **reset**.

The batch contains:

- 3 files that import;
- 1 already imported;
- 1 with an unknown IBAN, which needs an Account;
- 1 that fails reconciliation (a July N26 file, leaving a July Gap);
- 1 unreadable photo PDF.

| Variant | Import results | Coverage | Accounts |
|---|---|---|---|
| **A · Batch report** | A report card on top: a headline, three tiles and **Review 44 Transactions**. Then one expandable row per file, with the files that need you open first. | A bar per Account on its own axis. Gaps keep today's stripes. Each Gap is listed in text with **Import**. | A table with owner names. A disabled Delete sits beside "Has 20 Statements: delete them under Import first". A "Saved …" notice and a row flash. |
| **B · Accounts board** | Files drop anywhere on the page. A one-line banner with **Review now**, then a "Needs you" tray. Successes land on their Account's row ("New: 1–30 Sep · 64 Transactions, 20 to review"). | Every Account on **one shared time axis**. Gaps are outlined slots ("Jul", "49 d") that are buttons to import, with no stripes. | The same board. Rows edit in place, and Delete or its reason sits beside the form. |
| **C · Guided flow** | Steps: Choose → Import → Check the results. "Needs you" cards, then a quiet Imported list (counts behind "All counts"), then a dark hand-over band, "Next: 44 Transactions wait for review". | An **Account × month grid** (13 months) in the Dashboard's completeness words: Complete, new, "to 15", an Import Gap, or · not tracked. | Cards. Edit opens a side drawer with the form, the Statements and the delete zone. A toast and a card flash on save. |

**Shared by all of them (the copy is the proposal, not a variant):**

- **Rejections lead with the cause, then the next step,** with the reconciliation behind a disclosure. "Keep the file" appears only where a reader fix could help, never for a wrong file type. Examples:
  - "A payment seems to be missing. The Statement lists 31 payments out, totalling 2.652,45 €. Pursegraph read 30 of them…"
  - "Not a Statement Pursegraph can read."
  - "Doesn't follow on from what's imported."
  - "Disagrees with what's already imported."
- **"Already imported" is neutral, not a failure:** "Went into Maja's Sparkasse on 3 Sep 2026. Nothing changed."
- **Plain domain counts.** "non-completed rows" becomes "card payments still pending or declined, left out". "Σ rows" becomes "All rows read, added up".
- **Status is an icon plus a word,** never red or green (the No Verdict Rule).
- **Gaps include the stretch since the last Statement** (CONTEXT.md, and #75's carried item).
- **A Gap's action** shows "For Luka's N26: a Statement covering 1–31 Jul 2026. Download it from N26 and drop it here." It can't preselect anything, because the IBAN decides the Account.
- **Kept as today:**
  - Statement and Account delete confirmations with their consequences (Transactions lost, manual outcomes, Rules);
  - attaching an unknown IBAN at import, so that next time the Statement goes there by itself.

**Open conflict to settle.** The ticket says to keep the gap stripes (A does). DESIGN.md reserves the hatch for Awaiting review and says completeness uses neither hatch nor dash (B and C follow that).

## Findings

**Verdict: B, the Accounts board.** Import is the Household's Accounts on one shared time axis, with files dropped onto the page. Accounts (Manage, admins) is the same board, with rows that edit in place.

- **The stripes conflict is settled B's way.** Gaps are outlined slots with text, and the hatch stays reserved for Awaiting review, as DESIGN.md says.
- **The domain counts stay.** B's first cut showed only "New: 1–30 Sep · 64 Transactions, 20 to review". That caption is now a disclosure that opens the full counts, because the counts are part of the trust ritual the ticket keeps.
- **Leaving mid-import is out of scope for #86.** The import is one POST, so leaving during "checking" still imports everything, but the per-file outcomes (rejections, the Account choice) are lost.
- **A's and C's parts that didn't win:** A's per-file report and C's guided steps. C's step 3 also can't be reopened after leaving, which made the lost-response problem most visible.

Shots are in `shots/`: each variant's results, A's and C's Accounts, B idle in dark, and C idle.
