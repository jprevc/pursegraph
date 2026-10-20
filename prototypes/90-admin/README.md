# PROTOTYPE: #90 Admin pages (throwaway, never merge)

**Question:** how do the admin pages (Categories, LLM suggestions, Members) look in the new direction, on desktop only? Covers UX critique findings 13 (destructive actions confirm), 26 (the Categories wall of controls), 27 (the LLM units and status) and the P3 Members note (mark the current user, separate state from action, invite link with Copy, expiry as a date and "shown only now").

```sh
python3 -m http.server 8090      # from the repo root
# → http://localhost:8090/prototypes/90-admin/?variant=A&page=categories
```

The page is static, inside the #63 shell with Manage open. Its invariants mirror `ledger/categories.py` and `members/views.py`: the catch-all is last and can't be deleted, a Category is deleted only when nothing uses it, and the last active admin can't be demoted or deactivated. Changes stay in memory. The black bar switches the variant (‹ ›, or ← / → while nothing has focus), jumps between the three pages, cycles the LLM status (ok / down / off) on LLM suggestions, and toggles the theme and a reset. You are Maja, the only admin.

| Variant | Categories | LLM suggestions | Members | Confirm |
|---|---|---|---|---|
| **A · Tables, row menu, dialogs** | One table, Categories expandable to their Subcategories, with Transactions and Rules columns. Each row's actions sit in a ⋯ menu, and a disabled item says why ("The catch-all stays last") | Three cards: Status, Auto-accept (a number field in "% sure"), Ask again | A table with Name (+ You), Username, Role, Status, Owns, and a ⋯ menu. Invite a Member and the link are their own pages | Modal dialog |
| **B · Master–detail, inline confirm** | A Category list (drag, Alt+↑/↓) on the left; the selected Category on the right with its Subcategories, counts, Rename and Delete icon buttons, the catch-all locked last | A sentence with a slider and a live effect line ("At 70 %, 5 suggestions now in the queue would pass"), status in a side card | A Member list; the detail puts each state beside its own action (Role: Member · Make admin; Status: Active · Deactivate). The form and the link open in the detail pane | Inline, under the thing (DESIGN.md's Manage rule from #87) |
| **C · Read first, edit one at a time** | Read-only Category cards, each with its Subcategories and counts. Edit opens one card (full width) with inputs, ↑ ↓, Delete, and Save changes. The other cards lock | A status strip (with Check now), then a histogram of the queued suggestions by % sure in 5 % bins, with the Auto-accept line that moves with the slider | Grouped by role: Admins, Members, Deactivated. The section is the state, and the row's buttons are the actions. The form and the link open in dialogs | Inline |

**Shared by all three:**

- **Delete a Subcategory** names the effect: "Its 412 Transactions and 4 Rules move to Food › Other. Queued suggestions for it are asked again."
- **Delete a Category** is offered only when it is unused, and otherwise says why: "Food still has 555 Transactions. Delete its Subcategories first, then recategorize what is left in Other."
- **Catch-all**: tagged, never moved or deleted, and "New Subcategory" goes just above it. A Category's hue follows its id, so moving it keeps its colour.
- **Threshold in % sure** (the queue's unit). Lowering it offers the queued suggestions that now pass ("Accept 5" / "Leave in the queue"). Ask again confirms.
- **LLM status**: Working (model, server, last answer), Can't reach the LLM (last failure, retrying every 5 minutes), or Not set up (OLLAMA_URL empty). Counts: with a suggestion, waiting to be asked, by the LLM this month.
- **Members**: "You" tag; "Hasn't set a password yet · invited 18 Oct" from the unusable password; Deactivate and Make admin confirm with their consequences; the last admin's actions are replaced by the reason.
- **Invite / reset link**: Copy link, "Shown only now", "Works once, until Tuesday 27 October 2026 at 14:05", and "There is no email here".

**Things a winner would need from the backend** (carried, not decided here): a "last answer at" time and a Check now probe for the LLM (today there's only the `suggestions_unavailable` flag), per-Subcategory Transaction and Rule counts, the per-month LLM count, and the invite date for a Member who hasn't set a password.

Shots in `shots/` (desktop, light and dark).

## Findings

_Pending: the variant is picked with the user (HITL)._
