# The core no longer calls an LLM, so it no longer records whether the last call failed.

from django.db import migrations


def drop_suggestions_unavailable(apps, schema_editor):
    apps.get_model("ledger", "Setting").objects.filter(key="suggestions_unavailable").delete()


class Migration(migrations.Migration):

    dependencies = [
        ("ledger", "0010_categorizer_tokens"),
    ]

    operations = [
        migrations.RunPython(drop_suggestions_unavailable, migrations.RunPython.noop),
    ]
