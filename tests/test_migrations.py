from datetime import UTC, date, datetime
from decimal import Decimal

import pytest
from django.db import connection
from django.db.migrations.executor import MigrationExecutor

BEFORE = [("ledger", "0011_webhooks")]
AFTER = [("ledger", "0012_source_categorizer")]


def migrate(targets):
    """Migrates the test database to `targets`; returns the models as they are there."""
    executor = MigrationExecutor(connection)
    executor.migrate(targets)
    executor.loader.build_graph()
    return executor.loader.project_state(targets).apps


def sources(apps):
    rows = apps.get_model("ledger", "Transaction").objects.order_by("description")
    return list(rows.values_list("description", "source"))


@pytest.mark.django_db(transaction=True, serialized_rollback=True)
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
        migrate(MigrationExecutor(connection).loader.graph.leaf_nodes())


@pytest.mark.django_db(transaction=True, serialized_rollback=True)
def test_a_token_created_before_the_rename_keeps_working(client):
    from ledger.api_tokens import _digest

    apps = migrate([("ledger", "0013_drop_suggestions_unavailable")])
    apps.get_model("ledger", "CategorizerToken").objects.create(
        name="Qwen on the NAS",
        digest=_digest("pgc_before"),
        last_used_at=datetime(2026, 10, 1, 9, tzinfo=UTC),
        last_suggestion_at=datetime(2026, 10, 2, 9, tzinfo=UTC),
    )

    try:
        migrate(MigrationExecutor(connection).loader.graph.leaf_nodes())
        from ledger.models import ApiToken

        token = ApiToken.objects.get()
        assert (token.name, token.last_suggestion_at) == (
            "Qwen on the NAS",
            datetime(2026, 10, 2, 9, tzinfo=UTC),
        )
        assert token.last_used_at == datetime(2026, 10, 1, 9, tzinfo=UTC)

        response = client.get(
            "/api/categorizer/v1/transactions/", headers={"Authorization": "Bearer pgc_before"}
        )
        assert response.status_code == 200
    finally:
        migrate(MigrationExecutor(connection).loader.graph.leaf_nodes())
