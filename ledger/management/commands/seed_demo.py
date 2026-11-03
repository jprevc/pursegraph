import random
from datetime import date, timedelta
from decimal import Decimal
from itertools import count

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

from ledger.models import (
    Account,
    AccountIBAN,
    Bank,
    Rule,
    Source,
    Statement,
    Subcategory,
    Transaction,
)
from ledger.transfers import pair

# Synthetic, so it may sit in scripts and docs; the demo database is thrown away after use.
PASSWORD = "demo-pass-123"
MONTHS = 12
# Card spending, as (Category, Subcategory), how often against the others, its merchants as
# (description, counterparty), and the range of an amount, in euros.
MERCHANTS = [
    (("Food", "Groceries"), 9, [
        ("MERCATOR CITYPARK", "Mercator d.d."),
        ("HOFER 4012 VIC", "Hofer trgovina d.o.o."),
        ("SPAR SLOVENIJA BTC", "Spar Slovenija d.o.o."),
        ("LIDL SLOVENIJA RUDNIK", "Lidl Slovenija d.o.o."),
    ], (12, 95)),
    (("Food", "Restaurants & cafés"), 3, [
        ("GOSTILNA DRAGA", "Gostilna Draga d.o.o."),
        ("KAVARNA ROG", "Kavarna Rog"),
        ("PIZZERIA FOCULUS", "Foculus d.o.o."),
    ], (6, 68)),
    (("Food", "Fast food & takeaway"), 3, [
        ("WOLT LJUBLJANA", "Wolt Enterprises Oy"),
        ("BUREK OLIMPIJA", "Burek Olimpija s.p."),
    ], (4, 26)),
    (("Home", "Furniture & household"), 1, [
        ("IKEA LJUBLJANA", "IKEA Slovenija d.o.o."),
        ("JYSK BTC", "JYSK d.o.o."),
    ], (12, 160)),
    (("Home", "Maintenance & repairs"), 0.5, [
        ("MERKUR TRGOVINA", "Merkur trgovina d.o.o."),
        ("BAUHAUS LJUBLJANA", "Bauhaus d.o.o."),
    ], (8, 90)),
    (("Transport", "Fuel"), 3, [
        ("PETROL BS CELOVSKA", "Petrol d.d."),
        ("PETROL BS TIVOLI", "Petrol d.d."),
    ], (38, 82)),
    (("Transport", "Parking & tolls"), 1.5, [
        ("DARS CESTNINA", "DARS d.d."),
        ("LPT PARKIRISCE KONGRESNI TRG", "LPT d.o.o."),
    ], (2, 18)),
    (("Transport", "Public transport & car sharing"), 1.5, [
        ("LPP URBANA", "Javno podjetje LPP d.o.o."),
        ("SZ POTNISKI PROMET", "SZ - Potniški promet d.o.o."),
        ("AVANT2GO", "Avant car d.o.o."),
    ], (2, 24)),
    (("Transport", "Car maintenance"), 0.3, [
        ("AVTOSERVIS KOS", "Avtoservis Kos s.p."),
    ], (60, 320)),
    (("Health", "Pharmacy"), 1.5, [
        ("BENU LEKARNA BTC", "Benu lekarne d.o.o."),
        ("LEKARNA LJUBLJANA ENOTA 5", "Lekarna Ljubljana"),
    ], (4, 38)),
    (("Health", "Doctor & dental"), 0.4, [
        ("ZOBNA AMBULANTA SMILE", "Smile d.o.o."),
    ], (40, 150)),
    (("Shopping", "Clothing & shoes"), 1.5, [
        ("ZALANDO SE", "Zalando SE"),
        ("H&M CITYPARK", "H & M Hennes & Mauritz d.o.o."),
        ("DECATHLON LJUBLJANA", "Decathlon d.o.o."),
    ], (15, 120)),
    (("Shopping", "Electronics"), 0.5, [
        ("BIG BANG BTC", "Big Bang d.o.o."),
        ("MIMOVRSTE.COM", "Mimovrste d.o.o."),
    ], (20, 260)),
    (("Shopping", "Personal care"), 1.5, [
        ("DM DROGERIE MARKT", "dm-drogerie markt d.o.o."),
        ("MULLER LJUBLJANA", "Müller trgovina d.o.o."),
    ], (5, 42)),
    (("Shopping", "Gifts"), 0.5, [
        ("ETSY.COM", "Etsy Ireland UC"),
        ("KNJIGARNA KONZORCIJ", "Mladinska knjiga d.d."),
    ], (12, 75)),
    (("Leisure", "Travel"), 0.6, [
        ("RYANAIR", "Ryanair DAC"),
        ("BOOKING.COM", "Booking.com B.V."),
        ("WIZZ AIR", "Wizz Air Hungary Ltd."),
    ], (45, 320)),
    (("Leisure", "Hobbies & sport"), 1, [
        ("FITNES TIVOLI", "Zavod Tivoli"),
        ("INTERSPORT BTC", "Intersport ISI d.o.o."),
    ], (18, 70)),
    (("Leisure", "Entertainment & going out"), 1, [
        ("KINO SISKA", "Zavod Kino Šiška"),
        ("CANKARJEV DOM", "Cankarjev dom"),
    ], (6, 45)),
]  # fmt: skip
CARD_PAYMENTS = 22  # a month, across the three Accounts
# Every month: the day, the Account ("ana", "luka" or "joint"), the description, the counterparty, the amount's range
# and the Subcategory.
FIXED = [
    (1, "joint", "Najemnina stanovanje", "Marko Novak", (850, 850), ("Home", "Rent / mortgage")),
    (5, "joint", "ELEKTRO LJUBLJANA d.d.", "Elektro Ljubljana d.d.", (52, 78), ("Home", "Utilities")),
    (8, "joint", "T-2 d.o.o. internet", "T-2 d.o.o.", (34.99, 34.99), ("Home", "Internet & phone")),
    (12, "luka", "NETFLIX.COM", "Netflix International B.V.", (12.99, 12.99),
     ("Leisure", "Subscriptions & digital services")),
    (20, "ana", "SPOTIFY P2F1C9", "Spotify AB", (10.99, 10.99),
     ("Leisure", "Subscriptions & digital services")),
]  # fmt: skip
# The Rules, top first, as what the description contains and the Subcategory it gives.
RULES = [
    ("Petrol", ("Transport", "Fuel")),
    ("Elektro Ljubljana", ("Home", "Utilities")),
    ("Mercator", ("Food", "Groceries")),
    ("Hofer", ("Food", "Groceries")),
    ("DARS", ("Transport", "Parking & tolls")),
]
# The Transactions awaiting review, in turn: a description and its LLM suggestion, if any.
WAITING = [
    ("Bolt.eu", ("Transport", "Public transport & car sharing", 0.78)),
    ("Kavarna Zvezda", None),
    ("PAYPAL *STEAMGAMES", ("Leisure", "Subscriptions & digital services", 0.86)),
    ("OMV 2041 Vič", ("Transport", "Fuel", 0.95)),
    ("Amazon EU S.a.r.l.", ("Shopping", "Other", 0.51)),
    ("Lekarna Ljubljana 12", ("Health", "Pharmacy", 0.97)),
    ("Zavarovalnica Triglav", ("Finance", "Insurance (non-health)", 0.74)),
    ("SEPA from J. Kranjc", None),
    ("Telekom Slovenije", ("Home", "Internet & phone", 0.93)),
]
# Refunds into Ana's Sparkasse, by how many months back: the day, the description, the counterparty,
# the amount and the spending Subcategory it goes back to.
REFUNDS = {
    7: (9, "ZALANDO SE RETOURE", "Zalando SE", "49.95", ("Shopping", "Clothing & shoes")),
    4: (21, "RYANAIR REFUND FR8274", "Ryanair DAC", "86.40", ("Leisure", "Travel")),
    1: (12, "IKEA LJUBLJANA VRACILO", "IKEA Slovenija d.o.o.", "39.99", ("Home", "Furniture & household")),
}  # fmt: skip


class Command(BaseCommand):
    help = (
        "Fill an empty database with a synthetic demo Household (Ana, admin, and Luka; password "
        f'"{PASSWORD}") and the last {MONTHS} months of Transactions, for screenshots and manual '
        "checks. The same day gives the same data."
    )

    @transaction.atomic
    def handle(self, *args, **options):
        User = get_user_model()
        if User.objects.exists() or Transaction.objects.exists():
            raise CommandError("seed_demo only fills an empty database.")
        rng = random.Random(7)
        today = timezone.localdate()

        ana = User.objects.create_user(
            username="ana", password=PASSWORD, first_name="Ana", is_admin=True
        )
        luka = User.objects.create_user(username="luka", password=PASSWORD, first_name="Luka")
        sparkasse = Account.objects.create(name="Ana's Sparkasse", bank=Bank.SPARKASSE_SI)
        sparkasse.owners.add(ana)
        n26 = Account.objects.create(name="Luka's N26", bank=Bank.N26)
        n26.owners.add(luka)
        joint = Account.objects.create(name="Joint Revolut", bank=Bank.REVOLUT)
        joint.owners.add(ana, luka)
        # Known only so that what Ana puts by is a Transfer.
        savings = Account.objects.create(name="Ana's savings", bank=Bank.OTHER)
        savings.owners.add(ana)
        accounts = {"ana": sparkasse, "luka": n26, "joint": joint}
        # Fictional: valid check digits, but a bank code of zeros, so none is anyone's real account.
        iban = {
            sparkasse: "SI02000000012345678",
            n26: "DE79000000001234567890",
            joint: "LT590000001234567890",
            savings: "SI41000000087654321",
        }
        for account, number in iban.items():
            AccountIBAN.objects.create(account=account, iban=number)

        # Coverage that shows every state of Period completeness: the Joint Revolut is tracked two months later
        # than the others, and Luka's N26 lacks a month and has nothing yet since the end of last month.
        def month_start(back):
            year, month = divmod(today.year * 12 + today.month - 1 - back, 12)
            return date(year, month + 1, 1)

        hashes = count(1)
        statements: list[Statement] = []

        def statement(account, start, end):
            statements.append(
                Statement.objects.create(
                    account=account,
                    format=Statement.Format.PDF,
                    period_start=start,
                    period_end=end,
                    opening_balance=0,
                    closing_balance=0,
                    imported_by=ana,
                    # Stands in for a file's hash, which only has to be unique.
                    sha256=f"{next(hashes):064x}",
                    file=f"demo/{account.pk}-{start}.pdf",
                )
            )

        before = timedelta(days=1)
        statement(sparkasse, month_start(MONTHS), today)
        statement(joint, month_start(MONTHS - 2), today)
        statement(n26, month_start(MONTHS), month_start(4) - before)
        statement(n26, month_start(3), month_start(0) - before)

        def book(account, day, amount, description, **fields):
            """A Transaction on the Statement that lists it; none outside the Account's Coverage."""
            listed_on = [
                s
                for s in statements
                if s.account == account and s.period_start <= day <= s.period_end
            ]
            if not listed_on:
                return None
            booked = Transaction.objects.create(
                account=account, date=day, amount=amount, description=description, **fields
            )
            booked.statements.set(listed_on)
            return booked

        def subcategory(category, name):
            return Subcategory.objects.get(category__name=category, name=name)

        salary = subcategory("Income", "Salary")

        def spend(account, day, low, high, description, counterparty, outcome):
            """A payment out, categorized by hand or by the LLM; the Rules take theirs at the end."""
            amount = -Decimal(rng.randint(round(low * 100), round(high * 100))) / 100
            if rng.random() < 0.5:
                confidence = rng.randint(90, 99) / 100
                how = {
                    "source": Source.LLM,
                    "suggested_subcategory": outcome,
                    "confidence": confidence,
                }
            else:
                how = {"source": Source.MANUAL}
            book(
                account,
                day,
                amount,
                description,
                counterparty_name=counterparty,
                subcategory=outcome,
                **how,
            )

        def side(account, other, day, amount, counterparty):
            """One side of a Transfer between `account` and `other`, a Transfer by its IBAN, not yet paired.
            The paying side names the Account paid into; the paid one, as banks do, the person who paid."""
            book(
                account,
                day,
                amount,
                f"Transfer to {other.name}" if amount < 0 else f"Transfer from {counterparty}",
                counterparty_name=counterparty,
                counterparty_iban=iban[other],
                is_transfer=True,
                source=Source.IBAN,
            )

        def transfer(payer, payee, day, amount, counterparty):
            side(payer, payee, day, -amount, counterparty)
            side(payee, payer, day, amount, counterparty)

        def suggestion(suggested):
            if not suggested:
                return {}
            category, name, confidence = suggested
            return {"suggested_subcategory": subcategory(category, name), "confidence": confidence}

        merchants = [subcategory(*outcome) for outcome, *_ in MERCHANTS]
        weights = [weight for _, weight, *_ in MERCHANTS]
        fixed = [subcategory(*outcome) for *_, outcome in FIXED]
        waiting = count()

        for back in range(MONTHS, -1, -1):
            start = month_start(back)
            # The running month only up to today.
            last_day = today.day if back == 0 else 28

            def on(day, start=start):
                return start.replace(day=day)

            for (day, whose, description, counterparty, (low, high), _), outcome in zip(
                FIXED, fixed, strict=True
            ):
                if day <= last_day:
                    spend(accounts[whose], on(day), low, high, description, counterparty, outcome)
            if last_day >= 15:
                for account, amount, employer in (
                    (sparkasse, "2410.00", "Kres Engineering d.o.o."),
                    (n26, "1980.00", "Lipa Software d.o.o."),
                ):
                    book(
                        account,
                        on(15),
                        Decimal(amount),
                        "Salary",
                        counterparty_name=employer,
                        subcategory=salary,
                        source=Source.MANUAL,
                    )
            if last_day >= 16:
                # Each pays into the Joint Revolut the day after payday; pairing links the two sides.
                for account, member, amount in (
                    (sparkasse, "Ana Zupan", "900.00"),
                    (n26, "Luka Zupan", "700.00"),
                ):
                    transfer(account, joint, on(16), Decimal(amount), member)
            if last_day >= 17:
                side(sparkasse, savings, on(17), Decimal("-300.00"), "Ana Zupan")
            for _payment in range(CARD_PAYMENTS):
                [i] = rng.choices(range(len(MERCHANTS)), weights)
                _, _, names, (low, high) = MERCHANTS[i]
                description, counterparty = rng.choice(names)
                spend(
                    rng.choice([sparkasse, n26, joint]),
                    on(rng.randint(1, last_day)),
                    low,
                    high,
                    description,
                    counterparty,
                    merchants[i],
                )
            if back in REFUNDS:
                day, description, counterparty, amount, outcome = REFUNDS[back]
                book(
                    sparkasse,
                    on(day),
                    Decimal(amount),
                    description,
                    counterparty_name=counterparty,
                    subcategory=subcategory(*outcome),
                    source=Source.MANUAL,
                )
            # Awaiting review: merchants that come back, so that the Review queue has groups.
            for _i in range(2):
                description, suggested = WAITING[next(waiting) % len(WAITING)]
                book(
                    sparkasse,
                    on(rng.randint(1, last_day)),
                    -Decimal(rng.randint(500, 9000)) / 100,
                    description,
                    **suggestion(suggested),
                )
            if back == MONTHS:
                # What Bolt.eu got last time, unlike its suggestion now.
                book(
                    sparkasse,
                    on(3),
                    Decimal("-12.40"),
                    "Bolt.eu",
                    counterparty_name="Bolt Operations OÜ",
                    subcategory=subcategory("Transport", "Other"),
                    source=Source.MANUAL,
                )

        # An ambiguous pairing: Ana's two equal payments into the Joint Revolut, two days either side of the
        # one it shows, so pairing can't tell which is its other side.
        top_up = Decimal("150.00")
        side(joint, sparkasse, today - timedelta(days=4), top_up, "Ana Zupan")
        for days in (6, 2):
            side(sparkasse, joint, today - timedelta(days=days), -top_up, "Ana Zupan")
        pair(Transaction.objects.filter(is_transfer=True))

        # The Rules, top first. Made a month into the demo, each categorized what it matches from then on, where
        # a Member would have chosen the same; what came before keeps the outcome a Member or the LLM gave it.
        made = month_start(MONTHS - 1)
        rules = [
            Rule(description_contains=contains, subcategory=subcategory(*outcome))
            for contains, outcome in RULES
        ]
        rules.append(Rule(direction=Rule.Direction.IN, account=n26, subcategory=salary))
        for position, rule in enumerate(rules):
            rule.position = position
            rule.save()
            Transaction.objects.filter(
                rule.condition(), subcategory=rule.subcategory, rule=None, date__gte=made
            ).update(source=Source.RULE, rule=rule, suggested_subcategory=None, confidence=None)

        self.stdout.write(f"Seeded the demo Household: {Transaction.objects.count()} Transactions.")
