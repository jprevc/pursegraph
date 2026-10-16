# Product

<!-- impeccable:product-schema 1 -->

## Platform

web

## Users

A single **Household**, the family whose combined finances one installation shows. Today it is two adults with children; a child may become a **Member** later (for example a teenager with an Account of their own).

- **The driver:** a technical admin Member. Every week they import the new **Statements** and clear the **Review queue**, sometimes at a desk and often on a phone. They also maintain **Rules**, **Accounts**, **Categories** and Members.
- **The reader:** a less technical Member who mostly reads the **Dashboard**, often on a phone, to see where the money went. Occasionally they import a Statement themselves.
- **Secondary audience:** people seeing Pursegraph as a portfolio piece, through README screenshots and a GIF of a fictional demo Household. They never use the app. The design is built for the Household's real weekly use, not for the screenshot, and it earns the showcase by doing that job well.

## Product Purpose

Pursegraph gives everyone in the Household a shared, trustworthy picture of where the money goes: by **Category**, over time, and per Member. The aim is that the family can talk about money from the same numbers instead of arguing about them.

It looks back and does not tell people what to do. There are no budgets, goals, alerts or nudges. Success looks like this:

- the weekly routine (import, then clear the Review queue) takes minutes;
- the reader can answer "where did our money go last month?" from the Dashboard alone.

## Positioning

Pursegraph is **the whole Household's money in one private picture**. It brings every Member's Accounts together across banks (Sparkasse SI, N26, Revolut, plus statement-less Accounts such as savings elsewhere). It understands **Transfers** between the Household's own Accounts, so money moving between Members or into savings is never counted as spending or income. It is self-hosted and reachable only on the LAN or over a VPN, so the data never leaves the home.

A bank's app sees only one bank. A single-user budgeting tool sees only one person.

## Operating Context

- **Weekly ritual:** download Statements (PDF, or Revolut CSV) from the banks, import several at once, then work through the Review queue. Most Transactions arrive already categorized by a Rule or by the local LLM's suggestion. The rest wait with a suggestion preselected.
- **Reading:** the Dashboard has five views (Spending, Cash flow, Money flow, Trends, Per Member) with drill-down and filters. The reader opens it casually, often on a phone.
- **Devices:** desktop-first. The Dashboard and the Review queue must be genuinely good on a phone. Import and the admin pages need only work on desktop.
- **Network:** LAN or VPN only, never exposed to the internet. The app has to work fully offline from the internet, so every asset is self-hosted.

## Capabilities and Constraints

- Domain vocabulary is defined in `CONTEXT.md` and is binding in the UI: Household, Member, Account, Bucket, Statement, Coverage, Transaction, Duplicate, Category, Subcategory, Rule, Review queue, Refund, Transfer.
- Statements are reconciled on import (balances and printed totals must add up) and rejected whole if they don't. Overlaps with Coverage are checked and skipped as Duplicates.
- Every Transaction ends with an outcome: a Subcategory or Transfer. A Refund reduces spending in its Subcategory.
- **Visibility:** every Member sees the whole Household. *Open question:* whether a future child Member should see less. Nothing is designed for it now.
- **Stack (existing, binding):** server-rendered Django templates with HTMX, hand-written CSS with no build step, ECharts for charts, and every asset vendored or self-hosted (no CDN).
- **Locale:** EUR amounts, timezone Europe/Ljubljana. UI text is English in v1 and is all marked for translation.
- There is no email server: invites and password resets are one-time links that an admin hands over in person.

## Brand Commitments

- **Name:** Pursegraph.
- **Voice:** calm, plain-spoken and factual. The copy never judges spending, cheers people on or gamifies, and an error says exactly what happened and what to do next. It uses the `CONTEXT.md` terms consistently.
- **Look: the category standard, done impeccably.** Pursegraph deliberately looks like a polished personal-finance dashboard, with the craft of Monarch Money as the bar. It has a light sidebar, white cards, Dashboard stat tiles, a Category donut and one indigo accent. This is a standing preference, chosen over more distinctive directions: familiarity serves the less technical reader. The convention is executed straight, with no quirk smuggled in.
- **Must never be mistaken for:**
  - a bank or fintech app (upsells, "insights" marketing);
  - a budgeting nag (red warnings, guilt, streaks, savings goals);
  - a trading terminal (dense, neon-on-black, built for traders).
- **Wordmark and favicon:** "Pursegraph" set in Inter, beside a two-segment donut mark on an indigo tile (see `DESIGN.md`).

## Evidence on Hand

- Real Statements live only in the gitignored `samples/` directory, and anonymized parser fixtures are in `tests/fixtures/`. Neither may appear in screenshots.
- There is no demo dataset, screenshots or testimonials yet. A fictional demo Household is planned for after the redesign, and nothing may stand in for it.

## Product Principles

1. **One Household, one picture.** Show the combined money flow first. Per-Member detail is something to drill into, not the starting point.
2. **Trust the numbers.** Reconciled data is the product's backbone. Make it visible where the numbers come from (Coverage, gaps, outcomes), and never show a figure that can't be traced back to Transactions.
3. **Describe, don't judge.** Show where money went, neutrally. No good/bad colouring of spending, no nudges.
4. **The weekly routine is short.** Import and review must be quick, including the Review queue on a phone.
5. **Readable by the least technical Member.** Every Dashboard view must make sense without knowing how the data got there.

## Accessibility & Inclusion

- WCAG 2.2 AA is the bar. No specific impairments are known in the Household.
- Charts must not rely on colour alone to tell series or Categories apart.
- A Slovenian translation is plausible later, so layouts must tolerate longer strings. Number and date formats should follow the locale (EUR, sl-SI conventions such as `1.234,56 €`).
