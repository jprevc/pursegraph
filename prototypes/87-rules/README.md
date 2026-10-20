# PROTOTYPE: #87 Rules (throwaway, never merge)

**Question:** how should Rules work and look in the new direction? Covers a live "matches N" preview, what Make a Rule pre-fills (so it isn't store-specific like "HOFER 2201"), per-Rule effect counts, reordering with a keyboard alternative, and confirming a delete. UX critique findings 13 and 24.

```sh
python3 -m http.server 8087      # from the repo root
# → http://localhost:8087/prototypes/87-rules/?variant=A&page=review
```

The page is static, inside the #63 shell. Its matching engine mirrors `ledger/rules.py`. Saves happen in memory. The black bar switches the variant (‹ ›, or ← / → while nothing has focus), jumps between the Review queue and Rules, and toggles a phone frame, the theme and a reset. Start in the Review queue and use **Make a Rule** on HOFER, PAYPAL *STEAMGAMES or Telekom (which has an IBAN).

| Variant | Rules list | Making or editing a Rule | Reorder | Delete |
|---|---|---|---|---|
| **A · Table + Rule page** | Table: conditions as pills, outcome, "N Transactions" categorized, "6 go to Rule 7 above" | Its own page: form on the left, live preview on the right; "Also change the N existing…" checkbox | Drag, plus ↑ ↓ buttons | Modal dialog |
| **B · Sentences, in place** | Each Rule as a sentence, "If the description contains SPAR → Food › Groceries" | A sentence builder opens in place; Make a Rule opens under the Review queue row; "Save and change N" / "Save, future imports only" | A "1st / 2nd …" select per Rule | No confirmation; Undo instead |
| **C · Saved filter** | Master/detail: the selected Rule shows every Transaction it caught | A filter bar over the matching Transactions, grouped Will change / Set by hand to something else / Already / Keep, with Now → After | Drag, or Alt+↑/↓, plus buttons | Inline confirmation |

**Shared by all three:**

- **Pre-fill.** An IBAN when the source has one. Otherwise the merchant word: store numbers and towns are dropped, and with a processor (PAYPAL *X) the word after `*` is used. "HOFER 2201 LJUBLJANA" pre-fills "HOFER". The description's words are chips that keep the match one contiguous run of words. Direction is never pre-filled, since a Refund must still match.
- **Preview.** Matches N: how many would change (awaiting, by LLM, by another Rule), how many already have the outcome, and how many keep theirs (set by hand, by IBAN or by pairing).
- **Warnings in the preview.**
  - "Set by hand to something else" (Gostilna Hofer, HOFER REISEN): new ones like them would follow this Rule at import. This is the clearest sign a Rule is too broad.
  - "Takes N over from Rule k."
  - "Rule k above wins on N of these."
- **Seeded mistake.** Rule 7 "SPAR" also catches "SPARKASSE account fee", so Rule 8 categorizes 0. Each variant's list shows this differently.

Shots in `shots/` (desktop light, phone dark/light).

## Findings

**Verdict: C.** A Rule is a filter over the Household's Transactions. Its page shows exactly which Transactions it catches and what happens to each one, so the preview isn't a summary next to the form: it is the page.

- **Now → After per Transaction** answers "what will this do" better than counts. The groups do the explaining: Will change, Set by hand to something else, Already, Keep. The "Set by hand to something else" group (Gostilna Hofer, HOFER REISEN) is where a too-broad Rule shows itself.
- **Save names its effect:** "Save and change 3", with "Future imports only" beside it. This replaces today's separate "Apply the Rule to existing Transactions?" page.
- **The list says what each Rule did.** The detail lists what the selected Rule caught, so the seeded SPAR → "SPARKASSE account fee" mistake is visible at a glance, and "6 of its matches go to Rule 7 above" explains a Rule that categorizes nothing.
- **Reorder:** drag, Alt+↑/↓ on the focused Rule, or the Move up / Move down buttons in the detail head.
- **Delete** confirms inline and says the outcomes stay. Deleting a Rule keeps its Transactions' outcomes (`Transaction.rule` is `SET_NULL`).
- **A's** separate preview pane read as a second thing to check, and its checkbox hid the effect. **B's** sentences were pleasant to read but long, and its builder was cramped on a phone. B's Undo-instead-of-confirm also contradicts critique finding 13.
- **Phone:** the list comes first and a Rule opens with a back button. The save bar must sit above the tab bar.
