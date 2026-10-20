# Rules

A surface section of the design system. Tokens, type, components and Named Rules live in [`DESIGN.md`](../../DESIGN.md); a "see *X*" names another surface in this folder or a section of `DESIGN.md`.

A Rule is a saved filter over the Household's Transactions. Each of its pages shows which Transactions it catches and what it does to them, so a Rule is never saved blind.
- **Rules page.** It has the title row with "New Rule" as its primary action, a muted line ("The first Rule a Transaction matches at import decides it"), then two cards: the list (300px) and the selected Rule's detail.
  - **List items:** each item shows the Rule's place (Faint, tabular), its name, the count of Transactions it categorized (Muted, tabular), and its outcome as Transaction-row text below. A Rule's name is its description text in quotes ("“HOFER”"), else its IBAN in groups of four.
  - **List as a listbox:** the selected item takes Indigo Wash. ↑/↓ move the selection, and Enter opens the Rule.
- **Detail.** The head is "7. “SPAR” → Food › Groceries", with Move up and Move down icon buttons, Edit, and a ghost Delete.
  - **Conditions:** pills ("contains **SPAR**", "IBAN **SI56 …**", "money **out**", "on **Maja · N26**").
  - **Effect line:** "Categorized 13 Transactions." When earlier Rules take some of its matches, it adds "6 of its matches go to Rule 7 (“SPAR”) above", which is how a Rule that categorizes nothing explains itself.
  - **Matches table:** Date, Transaction (the matched text in a soft highlight), Amount, and Outcome now with its source. It is grouped under Raised header rows: "Categorized by this Rule · N", then "Also matches, decided otherwise · N".
- **Reorder.** Drag a list item, or press Alt+↑/↓ while it is focused, or use the detail's Move buttons. Every move is announced ("Moved “SPAR” to 6th"). A new Rule goes to the top.
- **Delete.** Confirms inline under the detail head, on Raised with a Line Strong border: "Delete “SPAR”? Its 13 Transactions keep their outcome; future imports won't use it", with "Keep it" and a primary "Delete Rule". Focus moves to "Delete Rule". Deleting never changes an outcome. Every destructive action in Manage confirms the same way.
- **The Rule page** (New Rule, Edit Rule, Make a Rule). A title row with Back, then one card.
  - **Filter bar:** the conditions, as a wrapping row of 36px controls like the Dashboard's filter bar: Description contains (ignores case and accents), Counterparty IBAN, Direction, Account. Every condition set must hold.
  - **Preview:** below the filter bar, the Transactions the filter matches, live as you type, with columns Date, Transaction, Amount, Now and After saving. They are grouped:
    - "Will change · N";
    - "Set by hand to something else: kept now, but new ones like them would follow this Rule · N";
    - "Already *outcome* · N";
    - "Keep their outcome · N".

    The second group is how a Rule that is too broad shows itself. Outcomes set by hand, by IBAN, by pairing or by the parser are never overwritten; only those awaiting review, by LLM or by another Rule change.
  - **Warnings:** muted info lines above the table, with no alert colour: "Takes 2 over from Rule 7 (“SPAR”)" and "At import, Rule 3 above wins on 4 of these".
  - **Save bar:** sticky at the card's foot, holding "Categorize as" with the outcome select ("Category › Subcategory" options), Cancel, "Future imports only" and the primary "Save and change N" ("Save Rule" when nothing would change). This replaces the separate "Apply the Rule to existing Transactions?" page. After saving, the Rules page opens with the Rule selected, and a status line says what changed.
- **Make a Rule** (from "Saved as … · Undo · Make a Rule" in the Review queue). It opens the Rule page pre-filled from the Transaction, with the outcome it was just given.
  - **Pre-filled condition:** its counterparty IBAN if it has one. Otherwise the merchant word from the description: store numbers and towns are dropped, and after a payment processor ("PAYPAL *STEAMGAMES") the word after "*" is used. "HOFER 2201 LJUBLJANA" pre-fills "HOFER", never the whole string.
  - **Word chips:** under the field, the description's words, Indigo Wash when used. Tapping one widens or narrows the match, and it stays one contiguous run of words.
  - **No pre-filled direction:** a Refund must still match.
  - **The source Transaction:** pinned first in its group, tinted Indigo Wash, with "the one you just saved".
- **Phone (≤900px).** The list shows first, and a Rule's detail opens with a back button. On the Rule page, the filter fields stack, each preview row is a stacked card, and the save bar sits above the tab bar with 44px buttons.
