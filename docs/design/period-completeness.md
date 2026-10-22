# Period completeness

A surface section of the design system. Tokens, type, components and Named Rules live in [`DESIGN.md`](../../DESIGN.md); a "see *X*" names another surface in this folder or a section of `DESIGN.md`.

A missing Statement must never read as less spending. The Dashboard reads Coverage (derived, read-only: no new data, no URL change) and says how complete the period is. It considers only the Accounts the Member and Account filters include, so it never names an Account whose numbers aren't on screen. Accounts that receive no Statements are never considered.

**Month states.** Each month, for the included Accounts, is one of:
- **Complete:** no Gap. Drawn as usual, and a 0 is a real 0.
- **Partial:** at least one included Account has a Gap in it (a missing July; or 16–30 Sep, after a mid-month import).
- **Partly tracked:** before the first Coverage day of some included Account but not of all. It isn't a Gap: Coverage can't tell an Account opened later from one whose earlier Statements were never imported, so the month says what is known without claiming anything is missing.
- **In progress:** the running month, with no Gap up to today. Incomplete by time, not by a Gap.
- **Not tracked:** before the first Coverage day of every included Account. There are no numbers, not zeros.

The running month with a Gap is Partial. A longer period takes the first of Partial, Partly tracked, In progress, Not tracked, Complete that any of its months is. A period that is wholly Not tracked shows the Not tracked card (see Empty states) instead of a view.

**Header line.** One line between the view bar and the stat tiles: Ink 2 13px with a muted 16px info icon, no fill, border or alert colour (the No Verdict Rule). It has up to three parts, joined by "·":
1. **Gaps,** leading with the consequence: "Incomplete: no Statements yet from Luka's N26 for 1–31 Jul". Each Account name links to Import. Past two Accounts the rest collapse into "and 2 more", which expands in place.
2. **Partly tracked,** for each included Account that isn't tracked yet during a part of the period in which another one is: "Joint Revolut is tracked from 1 Feb 2026". No link, because there may be nothing to import.
3. **Awaiting review:** "2.148 € (81 %) still awaiting review", linked to the Review queue, whenever the period's Awaiting review is not zero. It is a statement of fact, not a nudge, and never makes a period incomplete.

The line is absent when neither part applies. In progress alone adds nothing here, because the stepper's "so far, to 17 Oct" already says it. On a phone it wraps and is never truncated.

**Month-axis charts** (Cashflow, Category trends, and any view over several months). The data marks stay as they are, because they are real numbers, only incomplete. The month column carries the state:
- **Partial / Partly tracked / In progress:** a full-height band behind the month in Hover (Raised is invisible on the card), with a muted 11px label at its top, "Partial", "Partly tracked" or "So far". The bands are a bar series of their own on hidden axes, because a `markArea` from a month to itself has no width on a category axis, and on the shared axes they would join Cashflow's bar groups. Category trends draws its points at month centres (`boundaryGap: true`) so that each month is a column a band can fill. Months in a row in one state make one band, labelled once; a band too narrow for its label's longest word (a single month on a phone) goes unlabelled, as the table's qualifiers and the tooltip still say it. The axis label of the running month reads "Oct (so far)". The axis tooltip opens with the reason ("No Statements from Luka's N26 for 1–31 Jul", "Joint Revolut is tracked from 1 Feb 2026", or "So far, to 17 Oct") above its table.
- **Not tracked:** the month keeps its place on the axis with a Faint label, and its data is `null`: no bar, and lines break rather than dropping to 0. Its tooltip reads "No Statements yet".

The bands' text labels are the non-colour cue. The hatch stays reserved for Awaiting review and the dash for Awaiting review as a line, so completeness uses neither.

**Tables** beside the charts carry the same states in text: column headers "Jul (partial)", "Jan (partly tracked)" and "Oct (so far)", and "—" (never 0) in a Not tracked month's cells. A qualifier wraps under the month, in Muted, so it never widens the table.

**Periods.** Every view opens on the last full month, even when that month is Partial (the header line says why), and Category trends opens on the 12 months ending with it. The running month is reached only with ›, as In progress. There is no "this month so far" anywhere else.
