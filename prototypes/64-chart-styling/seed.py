"""PROTOTYPE (#64), wipe me. Fills the scratch database with a synthetic Household over the last 12 months,
spending in every Category, so each chart has enough to show. Run by run.sh, never against a real database."""

import random
from datetime import date
from decimal import Decimal

from django.db import connection

from ledger.models import Account, Subcategory, Transaction
from members.models import Member

assert "wipe_me" in connection.settings_dict["NAME"], "seed.py only runs against the PROTOTYPE scratch database"

rng = random.Random(64)
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
today = date(2026, 10, 16)
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

Transaction.objects.bulk_create(rows)
print(f"PROTOTYPE seed: {len(rows)} Transactions; log in as ana / prototype")
