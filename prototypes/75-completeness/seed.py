"""PROTOTYPE (#75), wipe me. Fills the scratch database with a synthetic Household over the last 12 months,
spending in every Category, so each chart has enough to show. Run by run.sh, never against a real database.

Coverage, so every month state shows (#75): Ana's Sparkasse and Marko's N26 from 1 Jan 2026 and the Joint
Revolut from 1 Feb, all up to today, except that Marko's N26 has no Statement for July. So Oct-Dec 2025 are
Not tracked, July is Partial and the running month is In progress."""

import random
from datetime import date, timedelta
from decimal import Decimal

from django.db import connection

from ledger.models import Account, Statement, Subcategory, Transaction
from members.models import Member

assert "wipe_me" in connection.settings_dict["NAME"], "seed.py only runs against the PROTOTYPE scratch database"

rng = random.Random(75)
ana = Member.objects.create_user("ana", password="prototype", first_name="Ana", is_admin=True)
marko = Member.objects.create_user("marko", password="prototype", first_name="Marko")


def account(name, bank, *owners):
    a = Account.objects.create(name=name, bank=bank)
    a.owners.add(*owners)
    return a


anas, markos = account("Ana's Sparkasse", "sparkasse_si", ana), account("Marko's N26", "n26", marko)
joint, savings = account("Joint Revolut", "revolut", ana, marko), account("Savings", "other", ana)
sub = lambda c, s: Subcategory.objects.get(category__name=c, name=s)  # noqa: E731

# (Subcategory, accounts, times a month, typical amount)
SPENDING = [
    (sub("Food", "Groceries"), [joint, anas], 8, 55),
    (sub("Food", "Restaurants & cafés"), [markos, anas], 4, 28),
    (sub("Home", "Rent / mortgage"), [joint], 1, 820),
    (sub("Home", "Utilities"), [joint], 2, 85),
    (sub("Home", "Internet & phone"), [joint], 1, 45),
    (sub("Transport", "Fuel"), [markos], 3, 60),
    (sub("Transport", "Public transport & car sharing"), [anas], 2, 25),
    (sub("Health", "Pharmacy"), [anas], 1, 22),
    (sub("Children", "Childcare & school"), [joint], 1, 240),
    (sub("Children", "Activities"), [anas], 1, 60),
    (sub("Shopping", "Clothing & shoes"), [anas, markos], 1, 90),
    (sub("Shopping", "Electronics"), [markos], 0.3, 300),
    (sub("Leisure", "Subscriptions & digital services"), [markos], 3, 12),
    (sub("Leisure", "Travel"), [joint], 0.25, 900),
    (sub("Finance", "Bank fees"), [anas, markos], 1, 4),
    (sub("Other", "Cash withdrawal"), [anas], 1, 80),
]
salary, interest = sub("Income", "Salary"), sub("Income", "Interest")
rows = []
today = date.today()
for back in range(11, -1, -1):
    y, m = today.year, today.month - back
    if m < 1:
        y, m = y - 1, m + 12
    last = 28 if back else today.day

    def day():
        return date(y, m, rng.randint(1, last))

    def add(acc, amount, desc, outcome=None, transfer=False):
        rows.append(Transaction(account=acc, date=day(), amount=Decimal(amount).quantize(Decimal("0.01")),
                                description=desc, subcategory=outcome, is_transfer=transfer,
                                source="manual" if outcome or transfer else ""))

    if back or today.day >= 15:
        add(anas, 2350 + rng.uniform(-20, 20), "Salary Ana", salary)
        add(markos, 2050 + rng.uniform(-20, 20), "Salary Marko", salary)
    add(markos, rng.uniform(1, 9), "Interest", interest)
    for outcome, accounts, times, typical in SPENDING:
        n = int(times) + (rng.random() < times % 1)
        # Winter heating and summer travel give the trend lines some shape.
        season = 1.6 if outcome.name == "Utilities" and m in (12, 1, 2) else 1
        season = 2.5 if outcome.name == "Travel" and m in (7, 8) else season
        for _ in range(max(n, 0) if back else max(n // 2, 0)):
            add(rng.choice(accounts), -typical * season * rng.uniform(0.6, 1.4), f"{outcome.name} payment", outcome)
    for acc in (anas, markos):
        add(acc, -600, "To Joint Revolut", None, True)
        add(joint, 600, "From own Account", None, True)
    add(anas, -rng.choice([200, 300, 400]), "To Savings", None, True)
    if rng.random() < 0.3:
        add(anas, 35, "Clothing & shoes refund", sub("Shopping", "Clothing & shoes"))
    for _ in range(rng.randint(1, 4) if back < 3 else 0):
        add(rng.choice([anas, joint]), -rng.uniform(8, 70), "Unknown shop")
    if back < 2:
        add(anas, 45, "Unknown payment in")

COVERAGE = {
    anas: [(date(2026, 1, 1), today)],
    markos: [(date(2026, 1, 1), date(2026, 6, 30)), (date(2026, 8, 1), today)],
    joint: [(date(2026, 2, 1), today)],
}
for acc, ranges in COVERAGE.items():
    for start, end in ranges:
        month = start
        while month <= end:  # one Statement a month
            last = min(end, (month.replace(day=28) + timedelta(days=4)).replace(day=1) - timedelta(days=1))
            Statement.objects.create(account=acc, format="csv", period_start=month, period_end=last,
                                     opening_balance=0, closing_balance=0, imported_by=ana,
                                     sha256=f"{acc.pk:04d}{month:%Y%m%d}".ljust(64, "0"), file=f"proto/{acc.pk}-{month:%Y-%m}.csv")
            month = last + timedelta(days=1)
# Only what a Statement covers was imported; Transfers to Savings stay one-sided.
rows = [r for r in rows if r.account not in COVERAGE or any(s <= r.date <= e for s, e in COVERAGE[r.account])]
Transaction.objects.bulk_create(rows)
print(f"PROTOTYPE seed: {len(rows)} Transactions; log in as ana / prototype")
