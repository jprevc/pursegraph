---
version: 1
slug: "templates-dashboard-spending-html"
primary_target: "templates/dashboard/_spending.html"
related_targets: []
---

# Dashboard: Spending view

Scope: the Dashboard's Spending view and the app shell around it, as the first surface of the redesign. Mode: Operate. Audience: the driver (weekly, desk and phone) and the less technical reader (casual, often phone). Task: answer "where did our money go this period?" and drill into a Category's Transactions.

## Direction contract

THESIS: Pursegraph is a personal-finance dashboard at Monarch Money's level of craft, played straight. It refuses world costume and quirk; it doesn't refuse the convention.

OWN-WORLD: a cool grey ground with white cards (14px radius, soft offset shadow) and one indigo accent. Inter throughout, with tabular figures. Ten distinguishable Category hues, each kept identical in every view. 1.5px stroke icons. In dark mode, a near-black ground with raised graphite cards and the same hues lifted in lightness.

STORY: the reader sees what was spent, what came in and the net for the period. They see the share of each Category, find the biggest, open it and read its Transactions.

FIRST VIEWPORT: a white 240px sidebar with the mark, wordmark, the five Dashboard views, the ledger links (with a Review queue count badge) and a theme switch at the foot. Then a view bar with the title, period stepper and Member/Account filters. Below it, three tiles: Spent, Money in, Net. Then a donut card on the left and a ranked Category list card (share and amount) on the right. The drill-down card opens below.

Signature interaction: hovering or focusing a Category row highlights its donut segment, and the reverse; clicking opens the drill-down. Motion: the donut sweeps in once on load (ease-out), which is off under reduced motion.

FORM: the category standard (canon), chosen by the user; quality bar Monarch Money. seed:440d06eaf6aca514

FINISH: unreviewed and undocumented is unfinished; this build ends with the finish review, the verdict, DESIGN.md, and every shipping raster carrying its provenance
