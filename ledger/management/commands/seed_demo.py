import random
from datetime import date, timedelta
from decimal import Decimal
from itertools import count

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

from ledger.models import Account, Bank, Category, Source, Statement, Subcategory, Transaction

# Synthetic, so it may sit in scripts and docs; the demo database is thrown away after use.
PASSWORD = "demo-pass-123"
MONTHS = 10


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

        spending = list(
            Subcategory.objects.exclude(category__kind=Category.Kind.INCOME).order_by("pk")
        )
        salary = Subcategory.objects.get(category__kind=Category.Kind.INCOME, name="Salary")
        sources = [Source.MANUAL, Source.RULE, Source.LLM]

        today = timezone.localdate()
        for back in range(MONTHS, -1, -1):
            year, month = divmod(today.year * 12 + today.month - 1 - back, 12)
            month += 1
            # The running month only up to today.
            last_day = today.day if back == 0 else 28

            def on(day, year=year, month=month):
                return date(year, month, day)

            if last_day >= 15:
                for account, amount in ((sparkasse, "2410.00"), (n26, "1980.00")):
                    Transaction.objects.create(
                        account=account,
                        date=on(15),
                        amount=Decimal(amount),
                        description="Salary",
                        subcategory=salary,
                        source=Source.MANUAL,
                    )
            for i in range(18):
                subcategory = rng.choice(spending)
                Transaction.objects.create(
                    account=rng.choice([sparkasse, n26, joint]),
                    date=on(rng.randint(1, last_day)),
                    amount=-Decimal(rng.randint(400, 32000)) / 100,
                    description=f"{subcategory.name} {i + 1}",
                    subcategory=subcategory,
                    source=rng.choice(sources),
                )
            # Awaiting review.
            for i in range(2):
                Transaction.objects.create(
                    account=sparkasse,
                    date=on(rng.randint(1, last_day)),
                    amount=-Decimal(rng.randint(500, 9000)) / 100,
                    description=f"Card payment {month}-{i + 1}",
                )

        # Coverage that shows every state of Period completeness: the Joint Revolut is tracked two months later
        # than the others, and Luka's N26 lacks a month and has nothing yet since the end of last month.
        def month_start(back):
            year, month = divmod(today.year * 12 + today.month - 1 - back, 12)
            return date(year, month + 1, 1)

        hashes = count(1)

        def statement(account, start, end):
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

        before = timedelta(days=1)
        statement(sparkasse, month_start(MONTHS), today)
        statement(joint, month_start(MONTHS - 2), today)
        statement(n26, month_start(MONTHS), month_start(4) - before)
        statement(n26, month_start(3), month_start(0) - before)

        self.stdout.write(f"Seeded the demo Household: {Transaction.objects.count()} Transactions.")
