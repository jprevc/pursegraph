from django.core.management.base import BaseCommand, CommandError

from ledger.models import Statement, Transaction
from ledger.reparse import (
    ChangedRow,
    FieldChange,
    apply_changes,
    describe_row,
    refusal,
    reparse,
)


class Command(BaseCommand):
    help = (
        "Re-parse stored Statement files and print the differences against the stored "
        "Statements and Transactions, such as after a parser fix. Only shows them unless --apply."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "statement_ids", nargs="*", type=int, help="Statements to re-parse (default: all)."
        )
        parser.add_argument(
            "--apply",
            action="store_true",
            help="Take the changed Transactions' fields on, keeping manual outcomes.",
        )

    def handle(self, *args, statement_ids, apply: bool, **options):
        statements = Statement.objects.select_related("account").order_by(
            "account__name", "account_id", "period_start", "id"
        )
        if statement_ids:
            statements = statements.filter(pk__in=statement_ids)
            missing = set(statement_ids) - {s.pk for s in statements}
            if missing:
                raise CommandError(f"No Statement with id {', '.join(map(str, sorted(missing)))}.")

        unchanged = differing = applied = refused = failed = 0
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
                    self.stdout.write(f"  ~ {describe_row(row.transaction)}")
                    for change in row.changes:
                        self.stdout.write(f"      {_change(change)}")
                elif isinstance(row, Transaction):
                    self.stdout.write(f"  - {describe_row(row)}")
                else:
                    self.stdout.write(f"  + {describe_row(row)}")
            if result.error:
                failed += 1
                self.stdout.write(f"  failed: {result.error}")
            elif not result.has_differences:
                unchanged += 1
                self.stdout.write("  no differences")
            elif not apply:
                differing += 1
            else:
                try:
                    reason = refusal(result)
                    outcome_changes = [] if reason else apply_changes(result)
                except Exception as error:
                    # Rolled back: this Statement fails, the others are still applied.
                    failed += 1
                    self.stdout.write(f"  failed: {type(error).__name__}: {error}")
                    continue
                if reason:
                    refused += 1
                    self.stdout.write(f"  refused: {reason}")
                    continue
                applied += 1
                count = len(result.changed)
                self.stdout.write(
                    f"  applied: {count} Transaction{'' if count == 1 else 's'} updated"
                )
                for outcome in outcome_changes:
                    self.stdout.write(
                        f"    {describe_row(outcome.transaction)}: {outcome.before} → {outcome.after}"
                    )

        total = unchanged + differing + applied + refused + failed
        if apply:
            self.stdout.write(
                f"{total} Statement{'' if total == 1 else 's'} re-parsed: {applied} applied, "
                f"{refused} refused, {unchanged} unchanged, {failed} failed."
            )
            return
        self.stdout.write(
            f"{total} Statement{'' if total == 1 else 's'} re-parsed: {unchanged} unchanged, "
            f"{differing} with differences, {failed} failed. Nothing was changed."
        )


def _value(value) -> str:
    if value is None:
        return "—"
    return repr(value) if isinstance(value, str) else str(value)


def _change(change: FieldChange) -> str:
    return f"{change.name}: {_value(change.stored)} → {_value(change.parsed)}"
