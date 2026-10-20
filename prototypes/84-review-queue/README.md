# PROTOTYPE: #84 Review queue (throwaway, never merge)

**Question:** what is the Review queue in the new direction, on desktop and on a phone? This covers its shape (list or one card at a time), order and bulk accept, row context, what happens to resolved rows, the "Queue clear" end state, the follow-ups after a bulk accept, and keyboard shortcuts.

```sh
python3 -m http.server 8084      # from the repo root
# → http://localhost:8084/prototypes/84-review-queue/?variant=A
```

The prototype is a static page inside the #63 shell (variant B). Every row uses the #83 Transaction row (variant D): the outcome is text, it changes only through an explicit action, a fine pointer gets the chip panel and a coarse pointer gets the native select. Saves are stubbed: each takes 400 ms, and they all fail while **saves fail** is on.

The data is 15 synthetic Transactions from "Monday's import". Three of them share a description (Bolt.eu) and two more share another (HOFER). One Transfer has an ambiguous pairing, two Transactions have no suggestion, and three have suggestions that differ from what was used last time.

**Navigating it.** Use ‹ › on the black bar, or ← / → while nothing has focus, to switch the variant. The bar also has:

- **phone**, which loads the page in a 390 × 844 frame;
- **touch**, which fakes a coarse pointer so you get the native select;
- **saves fail**;
- the theme;
- **reset**.

It also shows the last screen-reader announcement.

| | A · Sorted list, confidence tiers | B · One card at a time | C · Grouped by description |
|---|---|---|---|
| **Shape** | One page with three cards: **Very likely** (≥ 90 %), **Check these** and **Needs you** (no suggestion, or an ambiguous Transfer). | A triage deck: one large card with progress above it, and **Up next** beside it on desktop. On a phone the buttons are sized for thumbs. | Master–detail. Transactions with the same description form one group, which is decided once ("Accept for all 3"). On a phone the list and the detail are two views. |
| **Order** | Surest first within each tier, then by date. | Surest first; Needs you comes last. | Newest group first. |
| **Bulk** | Only for Very likely: "Accept these 6". | None. Every card takes one tap. | Per group only. |
| **Row context** | Counterparty under the description, the owner in the Account pill, and a "Last time: … (differs)" line under the outcome. | The same, given more room on the card. | The group's Transactions plus a **Last time** section, with a note when the suggestion differs from it. |
| **Resolved rows** | They leave the tiers for a collapsed **Done** card, each with Undo. The counts, badge and title stay live. | The card advances. "Saved as … · Undo" stays under the deck. | The group stays where it is, ticked. Its detail keeps Undo, Make a Rule and Next. There is an All / Waiting filter. |
| **After a bulk accept** | "Accepted 6 … · Undo · See them in Transactions", which opens Transactions filtered to "Accepted just now · 6". | — | "Saved all 3 … · Undo · Make a Rule for "Bolt.eu" · See them in Transactions". |
| **Keyboard** | `j`/`k` move, `Enter` accepts, `e` opens Something else, `u` undoes. | `Enter` accepts, `e` opens Something else, `s` skips, `u` undoes the last save. | `j`/`k` move between groups, `Enter` accepts for all, `e` opens Something else, `u` undoes. |

**D · C revised** is C with three changes from the first review:

- **A "Show resolved" checkbox** replaces the All / Waiting tabs. It is off by default, so the list shows only groups still waiting. A group you just decided stays open in the detail pane, with its follow-ups (Undo, Make a Rule, See them in Transactions, Next), although it leaves the list.
- **No "Something else" button.** The decide box shows "Suggested · 78 % sure", the outcome and one Accept ("Accept for all 3"). Below it, the other outcomes are always open as chips under "Or choose another outcome". When the suggestion differs from what was used last time, a "Used last time" chip comes first, then Most used (without the suggested outcome), then the Categories. With no suggestion the heading is "Choose an outcome". An ambiguous Transfer asks "Which is the other side of this Transfer?" over the candidate cards, then "Or something else". The detail pane has room, so the chips are used on a phone as well, at 44 px.
- **No keyboard shortcuts**, and no key hints.

**Shared by all of them:** "Queue clear" says that September 2026 is now complete. Its primary action is "See September on the Dashboard" and its secondary one is "October so far". After a save, focus moves to the next waiting item. Shortcuts never fire while typing, inside the picker or with a modifier key, and the key hints are hidden on touch.

## Findings

_Leaning to D (C revised). The verdict is still to be confirmed._

Shots are in `shots/`: desktop shots of each variant at the start, with the picker open, after a save and at "Queue clear"; A after its bulk accept; C's group detail; and each variant on a phone in dark mode.
