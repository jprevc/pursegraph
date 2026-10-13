#!/usr/bin/env python3
# /// script
# requires-python = ">=3.12"
# dependencies = ["django>=5.1,<6"]
# ///
"""PROTOTYPE, throwaway. Issue #8: what should the dashboard look like?

Four variants of the Household dashboard on one throwaway route, switchable via
?variant=A|B|C|D and the floating bar (or the left/right arrow keys):

  A  Overview grid    : every view at once as panels, KPI strip on top (ECharts)
  B  Sidebar + HTMX   : one view at a time, picked from a sidebar, HTMX-swapped (ECharts)
  C  Monthly story    : a scrolling report with the Sankey as the hero (ECharts)
  D  Overview in Plotly: A's layout rendered with Plotly, to compare the libraries

All data is fake, generated in memory from a fixed seed: two Members (Ana, Marko),
three Accounts (Ana's Sparkasse, Marko's N26, a joint Revolut). No database.
Clicking a chart mark loads its Transactions below it via HTMX (drill-down).

Run:  uv run prototypes/dashboard/app.py
Open: http://127.0.0.1:8008/prototype/dashboard/
"""
import datetime as dt
import json
import random
import sys
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path

from django.conf import settings

HERE = Path(__file__).resolve().parent
settings.configure(
    DEBUG=True,  # the variant switcher only renders when DEBUG is on
    SECRET_KEY="prototype",
    ROOT_URLCONF=__name__,
    ALLOWED_HOSTS=["*"],
    TEMPLATES=[{"BACKEND": "django.template.backends.django.DjangoTemplates", "DIRS": [HERE / "templates"]}],
)

import django  # noqa: E402

django.setup()

from django.http import HttpResponseRedirect  # noqa: E402
from django.shortcuts import render  # noqa: E402
from django.urls import path  # noqa: E402

# ---------------------------------------------------------------- fake data

TODAY = dt.date(2026, 10, 13)
FIRST_MONTH = dt.date(2025, 10, 1)

# Default Categories from #4, in a fixed order so a Category keeps its colour everywhere.
SPENDING = ["Food", "Home", "Transport", "Health", "Children", "Shopping", "Leisure", "Finance", "Other"]
REVIEW = "Awaiting review"
REVIEW_IN = "Income awaiting review"  # Sankey node names must be unique
COLORS = {  # dataviz reference palette, slots 1-8, then neutrals
    "Food": "#2a78d6", "Home": "#eb6834", "Transport": "#1baf7a", "Health": "#eda100",
    "Children": "#e87ba4", "Shopping": "#008300", "Leisure": "#6250d6", "Finance": "#e34948",
    "Other": "#898781", REVIEW: "#c3c2b7",
}
ACCOUNTS = {
    "sparkasse": ("Ana · Sparkasse", ["Ana"]),
    "n26": ("Marko · N26", ["Marko"]),
    "revolut": ("Joint · Revolut", ["Ana", "Marko"]),
}
MEMBERS = ["Ana", "Marko", "Joint"]  # "Joint" is the derived bucket for jointly-owned Accounts


@dataclass
class Tx:
    id: int
    date: dt.date
    account: str
    amount: float  # signed: + is money in
    description: str
    category: str | None  # None + not transfer = in the Review queue
    subcategory: str | None
    transfer: bool = False

    @property
    def member(self):
        owners = ACCOUNTS[self.account][1]
        return owners[0] if len(owners) == 1 else "Joint"


def generate():
    rnd = random.Random(8)
    txs = []

    def add(d, account, amount, desc, cat=None, sub=None, transfer=False):
        if d <= TODAY:
            txs.append(Tx(len(txs) + 1, d, account, round(amount, 2), desc, cat, sub, transfer))

    def some(n_lo, n_hi, account, lo, hi, descs, cat, sub, month):
        for _ in range(rnd.randint(n_lo, n_hi)):
            add(month.replace(day=rnd.randint(1, 28)), account, -rnd.uniform(lo, hi), rnd.choice(descs), cat, sub)

    m = FIRST_MONTH
    while m <= TODAY:
        mo = m.month
        D = lambda day: m.replace(day=day)  # noqa: E731
        # income
        add(D(10), "sparkasse", 2150, "PLAČA UKC LJUBLJANA", "Income", "Salary")
        add(D(15), "n26", 2600, "Salary Acme d.o.o.", "Income", "Salary")
        add(D(18), "revolut", 120, "OTROŠKI DODATEK CSD", "Income", "Benefits & allowances")
        add(D(28), "revolut", rnd.uniform(1.5, 3.5), "Savings interest", "Income", "Interest")
        if mo == 7:
            add(D(10), "sparkasse", 1250, "REGRES ZA LETNI DOPUST", "Income", "Salary")
        if mo == 12:
            add(D(24), "n26", 300, "Christmas gift from parents", "Income", "Gifts received")
        # transfers into the joint Account (two sides each)
        for d, src, amt in [(11, "sparkasse", 900), (16, "n26", 1100)]:
            add(D(d), src, -amt, "Transfer to Joint Revolut", transfer=True)
            add(D(d), "revolut", amt, f"Transfer from {ACCOUNTS[src][0]}", transfer=True)
        # home
        add(D(1), "revolut", -780, "NLB STANOVANJSKI KREDIT", "Home", "Rent / mortgage")
        add(D(5), "revolut", -rnd.uniform(95, 190) * (1.3 if mo in (12, 1, 2) else 1), "ELEKTRO ENERGIJA", "Home", "Utilities")
        add(D(6), "revolut", -34.99, "TELEMACH", "Home", "Internet & phone")
        some(0, 1, "revolut", 20, 160, ["IKEA", "JYSK", "Merkur"], "Home", "Furniture & household", m)
        # food
        some(8, 11, "revolut", 25, 140, ["MERCATOR", "SPAR", "LIDL", "HOFER"], "Food", "Groceries", m)
        some(3, 5, "sparkasse", 12, 60, ["Gostilna Pri Lojzetu", "Kavarna Zvezda", "Pizzeria Foculus"], "Food", "Restaurants & cafés", m)
        some(3, 6, "n26", 15, 70, ["Restavracija Strelec", "Bistro Mirje"], "Food", "Restaurants & cafés", m)
        some(2, 4, "n26", 7, 18, ["Wolt", "McDonald's", "Hood Burger"], "Food", "Fast food & takeaway", m)
        # transport
        some(2, 3, "n26", 55, 80, ["PETROL", "OMV"], "Transport", "Fuel", m)
        some(1, 2, "sparkasse", 45, 70, ["PETROL"], "Transport", "Fuel", m)
        some(1, 4, "n26", 1.5, 12, ["LPT parkirnina", "DARS vinjeta"], "Transport", "Parking & tolls", m)
        add(D(3), "sparkasse", -20, "LPP mesečna", "Transport", "Public transport & car sharing")
        if mo == 3:
            add(D(12), "n26", -540, "ZAVAROVALNICA TRIGLAV avto", "Transport", "Car insurance & registration")
        if mo in (4, 10):
            add(D(20), "n26", -rnd.uniform(90, 320), "Vulkanizer Novak", "Transport", "Car maintenance")
        # health
        add(D(2), "sparkasse", -38.5, "VZAJEMNA dopolnilno", "Health", "Health insurance")
        add(D(2), "n26", -38.5, "VZAJEMNA dopolnilno", "Health", "Health insurance")
        some(0, 2, "revolut", 6, 45, ["LEKARNA LJUBLJANA"], "Health", "Pharmacy", m)
        some(0, 1, "sparkasse", 40, 120, ["Zobna ordinacija"], "Health", "Doctor & dental", m)
        # children
        if mo != 8:
            add(D(8), "revolut", -231, "VRTEC TRNOVO", "Children", "Childcare & school")
        add(D(9), "revolut", -45, "Plavalni klub", "Children", "Activities")
        some(0, 2, "revolut", 15, 70, ["Hervis", "Lumpi", "Pikapolonica"], "Children", "Clothes & toys", m)
        # shopping
        some(0, 3, "sparkasse", 20, 110, ["ZARA", "H&M", "Zalando"], "Shopping", "Clothing & shoes", m)
        some(1, 3, "sparkasse", 8, 35, ["DM", "Müller"], "Shopping", "Personal care", m)
        if mo == 11:
            add(D(28), "n26", -649, "BIG BANG", "Shopping", "Electronics")
        if mo == 12:
            some(4, 6, "revolut", 25, 110, ["Mladinska knjiga", "Amazon", "Hervis"], "Shopping", "Gifts", m)
        # leisure
        add(D(4), "sparkasse", -39, "FITNES 365", "Leisure", "Hobbies & sport")
        add(D(14), "revolut", -13.99, "NETFLIX.COM", "Leisure", "Subscriptions & digital services")
        add(D(21), "n26", -10.99, "Spotify", "Leisure", "Subscriptions & digital services")
        some(0, 2, "n26", 15, 60, ["Kinodvor", "Kino Cineplexx", "Cvetličarna"], "Leisure", "Entertainment & going out", m)
        if mo == 2:
            add(D(15), "revolut", -720, "Kranjska Gora ski pass + hotel", "Leisure", "Travel")
        if mo == 7:
            add(D(2), "revolut", -1840, "Booking.com Hvar", "Leisure", "Travel")
        if mo == 8:
            add(D(12), "revolut", -420, "Jadrolinija + restaurants Hvar", "Leisure", "Travel")
        # finance
        add(D(1), "sparkasse", -4.5, "Nadomestilo za vodenje računa", "Finance", "Bank fees")
        add(D(1), "revolut", -9.99, "Revolut Premium plan fee", "Finance", "Bank fees")
        add(D(20), "revolut", -22, "Generali zavarovanje doma", "Finance", "Insurance (non-health)")
        # other
        some(0, 2, "sparkasse", 50, 100, ["ATM BANKOMAT"], "Other", "Cash withdrawal", m)
        some(0, 1, "n26", 10, 40, ["Payment to Luka K."], "Other", "Payments to people", m)
        # occasional Refund: money in, placed in a spending Subcategory
        if rnd.random() < 0.4:
            add(D(rnd.randint(1, 28)), "sparkasse", rnd.uniform(20, 80), "Zalando refund", "Shopping", "Clothing & shoes")
        m = (m + dt.timedelta(days=32)).replace(day=1)

    # Review queue: a chunk of the most recent Transactions are not categorized yet, plus a few stragglers.
    for t in txs:
        if t.transfer or t.category is None:
            continue
        recent = (TODAY - t.date).days <= 18
        if (recent and rnd.random() < 0.3) or rnd.random() < 0.004:
            t.category = t.subcategory = None
    txs.sort(key=lambda t: (t.date, t.id))
    return txs


TXS = generate()

# ---------------------------------------------------------------- aggregation


def month_key(d):
    return d.strftime("%Y-%m")


def all_months():
    out, m = [], FIRST_MONTH
    while m <= TODAY:
        out.append(month_key(m))
        m = (m + dt.timedelta(days=32)).replace(day=1)
    return out


MONTHS = all_months()


def label(mk, short=False):
    d = dt.date.fromisoformat(mk + "-01")
    return d.strftime("%b %y" if short else "%B %Y")


def bucket(t):
    """Which Category bucket a Transaction lands in for charts, or None if it's a Transfer."""
    if t.transfer:
        return None
    if t.category is None:
        return REVIEW
    return t.category


def month_figures(mk, member=None):
    income = spending = 0.0
    by_cat = defaultdict(float)
    by_sub = defaultdict(lambda: defaultdict(float))
    income_by_sub = defaultdict(float)
    for t in TXS:
        if month_key(t.date) != mk or (member and t.member != member):
            continue
        b = bucket(t)
        if b is None:
            continue
        if b == "Income" or (b == REVIEW and t.amount > 0):
            income += t.amount
            income_by_sub[t.subcategory or REVIEW_IN] += t.amount
        else:
            spending -= t.amount  # a Refund (+) reduces spending in its Subcategory
            by_cat[b] -= t.amount
            by_sub[b][t.subcategory or REVIEW] -= t.amount
    return income, spending, by_cat, by_sub, income_by_sub


def r(x):
    return round(x, 2)


def dashboard_data(mk):
    i = MONTHS.index(mk)
    window = MONTHS[max(0, i - 11): i + 1]
    income, spending, by_cat, by_sub, income_by_sub = month_figures(mk)
    prev_spending = month_figures(MONTHS[i - 1])[1] if i > 0 else None

    cats = [c for c in SPENDING + [REVIEW] if by_cat.get(c, 0) > 0.005]
    by_category = [
        {"name": c, "value": r(by_cat[c]), "color": COLORS[c],
         "subs": sorted(({"name": s, "value": r(v)} for s, v in by_sub[c].items() if v > 0.005), key=lambda x: -x["value"])}
        for c in sorted(cats, key=lambda c: -by_cat[c])
    ]

    cashflow = {"months": [label(m, True) for m in window], "keys": window, "in": [], "out": [], "net": []}
    trends = {"months": cashflow["months"], "keys": window, "series": {c: [] for c in SPENDING}}
    for m in window:
        inc, sp, bc, _, _ = month_figures(m)
        cashflow["in"].append(r(inc))
        cashflow["out"].append(r(sp))
        cashflow["net"].append(r(inc - sp))
        for c in SPENDING:
            trends["series"][c].append(r(bc.get(c, 0)))
    trends["series"] = [{"name": c, "color": COLORS[c], "data": v} for c, v in trends["series"].items()]

    members = {"names": MEMBERS, "series": [], "income": [], "spending": []}
    per = {mb: month_figures(mk, mb) for mb in MEMBERS}
    for c in SPENDING + [REVIEW]:
        vals = [r(per[mb][2].get(c, 0)) for mb in MEMBERS]
        if any(v > 0.005 for v in vals):
            members["series"].append({"name": c, "color": COLORS[c], "data": vals})
    members["income"] = [r(per[mb][0]) for mb in MEMBERS]
    members["spending"] = [r(per[mb][1]) for mb in MEMBERS]

    # Sankey: income Subcategories -> Household -> spending Categories (+ Saved / From savings)
    nodes, links = [], []
    for s, v in sorted(income_by_sub.items(), key=lambda x: -x[1]):
        if v > 0.005:
            nodes.append({"name": s})
            links.append({"source": s, "target": "Household", "value": r(v)})
    nodes.append({"name": "Household"})
    if income < spending:
        nodes.append({"name": "From savings"})
        links.append({"source": "From savings", "target": "Household", "value": r(spending - income)})
    for c in by_category:
        nodes.append({"name": c["name"], "color": c["color"]})
        links.append({"source": "Household", "target": c["name"], "value": c["value"]})
    if income > spending:
        nodes.append({"name": "Saved"})
        links.append({"source": "Household", "target": "Saved", "value": r(income - spending)})

    review_count = sum(1 for t in TXS if not t.transfer and t.category is None)
    month_review = sum(1 for t in TXS if month_key(t.date) == mk and not t.transfer and t.category is None)
    return {
        "month": mk, "monthLabel": label(mk),
        "partial": mk == month_key(TODAY), "asOf": TODAY.strftime("%-d %b %Y"),
        "kpis": {"income": r(income), "spending": r(spending), "net": r(income - spending),
                 "prevSpending": r(prev_spending) if prev_spending is not None else None,
                 "reviewCount": review_count, "monthReview": month_review},
        "byCategory": by_category, "cashflow": cashflow, "trends": trends,
        "members": members, "sankey": {"nodes": nodes, "links": links},
        "colors": COLORS,
    }


# ---------------------------------------------------------------- views

VARIANTS = [("A", "Overview grid"), ("B", "Sidebar + HTMX"), ("C", "Monthly story"), ("D", "Overview in Plotly")]
B_VIEWS = [("spending", "Spending by Category"), ("cashflow", "Cashflow"), ("trends", "Category trends"),
           ("members", "Per Member"), ("sankey", "Money flow")]


def dashboard(request):
    variant = request.GET.get("variant", "A").upper()
    if variant not in dict(VARIANTS):
        return HttpResponseRedirect("?variant=A")
    mk = request.GET.get("month", MONTHS[-1])
    if mk not in MONTHS:
        mk = MONTHS[-1]
    i = MONTHS.index(mk)
    data = dashboard_data(mk)
    view = request.GET.get("view")
    ctx = {
        "data": data, "variant": variant, "variant_name": dict(VARIANTS)[variant],
        "variants_json": json.dumps(VARIANTS), "debug": settings.DEBUG,
        "month": mk, "months": [(m, label(m)) for m in MONTHS],
        "prev_month": MONTHS[i - 1] if i > 0 else None,
        "next_month": MONTHS[i + 1] if i < len(MONTHS) - 1 else None,
        "view": view if view in dict(B_VIEWS) else "spending","b_views": B_VIEWS, "b_views_json": json.dumps(dict(B_VIEWS)),
    }
    if variant == "B" and request.headers.get("HX-Request"):
        return render(request, "b_view.html", ctx)  # HTMX swaps just the view panel
    return render(request, f"variant_{variant.lower()}.html", ctx)


def transactions(request):
    """HTMX drill-down: the Transactions behind one chart mark."""
    mk = request.GET.get("month")
    cat = request.GET.get("category")
    member = request.GET.get("member")
    kind = request.GET.get("kind")  # "in" / "out" from the cashflow chart
    if cat == REVIEW_IN:
        cat, kind = REVIEW, "in"
    rows = []
    for t in TXS:
        if mk and month_key(t.date) != mk:
            continue
        if member and t.member != member:
            continue
        b = bucket(t)
        if b is None:
            continue
        if cat and b != cat and t.subcategory != cat:
            continue
        if kind == "in" and not (b == "Income" or (b == REVIEW and t.amount > 0)):
            continue
        if kind == "out" and (b == "Income" or (b == REVIEW and t.amount > 0)):
            continue
        rows.append(t)
    rows.sort(key=lambda t: t.date, reverse=True)
    title = " · ".join(x for x in [cat, {"in": "Money in", "out": "Money out"}.get(kind), member,
                                       label(mk) if mk else None] if x)
    return render(request, "transactions.html", {
        "rows": [{"t": t, "account": ACCOUNTS[t.account][0]} for t in rows],
        "title": title, "total": r(sum(t.amount for t in rows)),
    })


urlpatterns = [
    path("", lambda request: HttpResponseRedirect("/prototype/dashboard/")),
    path("prototype/dashboard/", dashboard),
    path("prototype/dashboard/transactions/", transactions),
]

if __name__ == "__main__":
    from django.core.management import execute_from_command_line

    execute_from_command_line([sys.argv[0], "runserver", *(sys.argv[1:] or ["127.0.0.1:8008"])])
