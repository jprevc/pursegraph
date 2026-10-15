from django.core.management.base import BaseCommand, CommandError

from ledger.models import Statement, Transaction
from ledger.reparse import ChangedRow, FieldChange, reparse


class Command(BaseCommand):
    help = (
        "Re-parse stored Statement files and print the differences against the stored "
        "Statements and Transactions, such as after a parser fix. Only shows them; changes nothing."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "statement_ids", nargs="*", type=int, help="Statements to re-parse (default: all)."
        )

    def handle(self, *args, statement_ids, **options):
        statements = Statement.objects.select_related("account").order_by(
            "account__name", "account_id", "period_start", "id"
        )
        if statement_ids:
            statements = statements.filter(pk__in=statement_ids)
            missing = set(statement_ids) - {s.pk for s in statements}
            if missing:
                raise CommandError(f"No Statement with id {', '.join(map(str, sorted(missing)))}.")

        unchanged = differing = failed = 0
        for statement in statements:
            result = reparse(statement)
            self.stdout.write(
                f"Statement {statement.pk}: {statement.account} "
                f"{statement.period_start}–{statement.period_end} ({statement.file.name})"
            )
            for change in result.statement_changes:
                self.stdout.write(f"  {_change(change)}")
            # In date order, whatever the kind of difference.
            rows = [
                *((changed.transaction.date, changed) for changed in result.changed),
                *((row.date, row) for row in result.added),
                *((transaction.date, transaction) for transaction in result.removed),
            ]
            for _day, row in sorted(rows, key=lambda dated: dated[0]):
                if isinstance(row, ChangedRow):
                    self.stdout.write(f"  ~ {_row(row.transaction)}")
                    for change in row.changes:
                        self.stdout.write(f"      {_change(change)}")
                elif isinstance(row, Transaction):
                    self.stdout.write(f"  - {_row(row)}")
                else:
                    self.stdout.write(f"  + {_row(row)}")
            if result.error:
                failed += 1
                self.stdout.write(f"  failed: {result.error}")
            elif result.has_differences:
                differing += 1
            else:
                unchanged += 1
                self.stdout.write("  no differences")

        total = unchanged + differing + failed
        self.stdout.write(
            f"{total} Statement{'' if total == 1 else 's'} re-parsed: {unchanged} unchanged, "
            f"{differing} with differences, {failed} failed. Nothing was changed."
        )


def _row(transaction_or_row) -> str:
    return f"{transaction_or_row.date} {transaction_or_row.amount:.2f} {transaction_or_row.description}"


def _value(value) -> str:
    if value is None:
        return "—"
    return repr(value) if isinstance(value, str) else str(value)


def _change(change: FieldChange) -> str:
    return f"{change.name}: {_value(change.stored)} → {_value(change.parsed)}"
