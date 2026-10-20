# Loading

A surface section of the design system. Tokens, type, components and Named Rules live in [`DESIGN.md`](../../DESIGN.md); a "see *X*" names another surface in this folder or a section of `DESIGN.md`.

An HTMX swap (a view tab, the period, a filter or the drill-down) keeps the old content on screen while the new one loads.
- **Immediately:** the swapped region gets `aria-busy="true"`.
- **After 300 ms:** if the swap is still running, the old content dims to 45% opacity and stops taking pointer events. A 2px Household Indigo line slides along the top of the region (1.1 s, eased, looping). The region clips it sideways, so the page never scrolls sideways. A swap that finishes within 300 ms shows neither, so fast swaps on the LAN don't flicker.
- **Labels change at once.** The period label, the active tab and the filter show the new choice straight away, so it is clear what is loading.
- **With nothing to dim** (a drill-down opening for the first time), the card opens with its title and the line over an empty body.
- **Reduced motion:** the line is static, full width, at 50% opacity.
- There are no skeletons or spinners.
- **Actions** (a row save, Accept for all, a Rule save) don't dim anything. The acting button is disabled with `aria-busy="true"` at once, so it can't be sent twice. After 300 ms its label becomes "Saving…" ("Accepting…" for Accept), and there is no line.
- **A swap that fails** (no network, a server error) keeps the old content, un-dimmed. A quiet line on Raised at the top of the region reads "Couldn't load September 2026." with a "Try again" button. It is announced politely and isn't red, like the Transaction row's failed-save line. The tab, period or filter label goes back to what is actually shown. An expired session (401/403) is a full redirect to login, with `?next=` back to the URL.
