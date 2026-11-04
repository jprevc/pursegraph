from datetime import date
from decimal import Decimal

import pytest
from django.db import connection
from django.db.migrations.executor import MigrationExecutor

BEFORE = [("ledger", "0010_categorizer_tokens")]
AFTER = [("ledger", "0011_source_categorizer")]


def migrate(targets):
    """Migrates the test database to `targets`; returns the models as they are there."""
    executor = MigrationExecutor(connection)
    executor.migrate(targets)
    executor.loader.build_graph()
    return executor.loader.project_state(targets).apps


def sources(apps):
    rows = apps.get_model("ledger", "Transaction").objects.order_by("description")
    return list(rows.values_list("description", "source"))


@pytest.mark.django_db(transaction=True)
def test_the_llm_source_becomes_categorizer_and_back():
    apps = migrate(BEFORE)
    account = apps.get_model("ledger", "Account").objects.create(name="Checking", bank="n26")
    for description, source in [("Suggested", "llm"), ("Matched", "rule"), ("Waiting", "")]:
        apps.get_model("ledger", "Transaction").objects.create(
            account=account,
            date=date(2026, 9, 1),
            amount=Decimal("-5"),
            description=description,
            source=source,
        )

    try:
        assert sources(migrate(AFTER)) == [
            ("Matched", "rule"),
            ("Suggested", "categorizer"),
            ("Waiting", ""),
        ]
        assert sources(migrate(BEFORE)) == [
            ("Matched", "rule"),
            ("Suggested", "llm"),
            ("Waiting", ""),
        ]
    finally:
        executor = MigrationExecutor(connection)
        executor.migrate(executor.loader.graph.leaf_nodes())
