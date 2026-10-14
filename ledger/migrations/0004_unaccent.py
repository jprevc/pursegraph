from django.contrib.postgres.operations import UnaccentExtension
from django.db import migrations


class Migration(migrations.Migration):
    """Accent-insensitive search: "cevljar" finds "Čevljar"."""

    dependencies = [("ledger", "0003_seed_default_categories")]

    operations = [UnaccentExtension()]
