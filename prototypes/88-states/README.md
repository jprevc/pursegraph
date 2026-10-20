# PROTOTYPE: #88 Login, empty, loading and first-run states (throwaway, never merge)

**Question:** what do login, empty, loading and first-run states look like and say? Covers what a brand-new Household sees, the empty pages (so they aren't dead ends), a wholly Not tracked period ("No Statements cover this period yet", from #75), login and locked out (an admin's reset link also clears the lockout, and errors are linked to their fields), and the loading placeholder. UX critique finding 15 and the P3 login note.

```sh
python3 -m http.server 8088      # from the repo root
# → http://localhost:8088/prototypes/88-states/?variant=A&state=login
```

The page is static, inside the #63 shell. Use the black bar to switch the variant (‹ ›, or ← / → while nothing has focus) and the **state**. It also toggles a phone frame and the theme, and has a reset. Log in as `maja` / `prototype`. Any other password counts as wrong, and the 5th wrong one locks the username, as `AXES_FAILURE_LIMIT` does. In **First run** the nav works, so you can open each empty page. On the Dashboard, the period arrows, view tabs and Member filter all trigger a load, and **replay load** runs one again.

| | A · In place | B · Setup mode | C · Show by example |
|---|---|---|---|
| **Login** | Centred card. Error summary at the top, and both fields point to it with `aria-describedby` | Split screen: what Pursegraph is on the left, the form on the right. The error sits under the password | Bare form on the ground. Error banner above the form |
| **Locked out** | The card becomes "Login paused until 15:42", with the reset-link escape and "Log in as someone else" | A countdown ("60 min, at 15:42") and two numbered steps to unlock now | The form stays. A banner explains the lock. The password field is disabled only while the locked username is typed |
| **First run** (admin, nothing imported) | The full nav stays. The Dashboard says "Nothing imported yet" and gives three facts: any Member imports, Accounts come from the IBAN, you're the only Member | The Dashboard becomes "Set up the Household", a 4-step checklist. The nav shows only what works yet: Get started, Import, Categories, Accounts, Members | A greyed example Dashboard marked "Example", under a notice that nothing is imported yet |
| **Empty pages** | Each page keeps its own frame (table headers) and puts the reason and the action where the rows would be | One centred block (icon, heading, reason, action), the same on every page | Greyed example rows marked "Example", with the reason and the action over them |
| **A new Member's first login** (Luka owns no Account alone) | Dismissible notice: "None of your own Accounts are in Pursegraph yet…" | A "Your first steps, Luka" card: import, then help with the Review queue | Coach mark on Import |
| **Not tracked** (Member filter Luka, Feb 2026) | One card: "No Statements cover February 2026 yet", then Go to March / Show all Members / Import an earlier Statement | The same, plus a Coverage timeline of the Accounts the filter includes | The view is drawn with "—" in the tiles and an empty dashed ring, plus the quiet header line |
| **Loading** | Skeletons in the shape of the content | The old view stays, dimmed, under a 2px progress line | One line saying what is loading: "Loading Spending for September 2026…" |

**Copy shared by all three:**
- "Forgot your password? There is no email here: ask an admin of the Household for a reset link."
- Locked out names the username, says "from this device" (the lock is per username + IP), gives the time it lifts, and says that choosing a new password through an admin's reset link also lifts it (`SetPasswordView` calls `axes.reset`). It also says other Members can still log in.
- Accounts: "There's nothing to add first: importing a Statement creates its Account from the IBAN printed on it. Add one here only for an Account that never gets Statements…"
- The empty Review queue is two different states: "Nothing to review yet" before any import, and "Nothing waiting for review" once everything is decided (state **Review queue empty**).
- Categories is never empty, because the list is seeded.

**Open trade-offs to judge:**
- C's example figures go against "the numbers are honest by construction".
- B's reduced nav hides pages until the first import.
- All three say how many tries are left after the 2nd wrong password ("3 more tries before luka is locked…"), which says how the lockout works.

Shots in `shots/`: every state per variant, desktop light and phone dark, plus `*-empty-<page>.png` for the first-run pages. **Verdict: B (Setup mode)**, written into DESIGN.md in PR #96, with these answers:
- Keep hiding Transactions, the Review queue and Rules until the first import.
- Show the tries left from the 3rd wrong try.
- The loading dim and line show only after 300 ms.
- In the spec, buttons stay standard (not filled with indigo), and the Coverage timeline is Muted, not a Category hue.
