"""Seeds the default two-level Category list. The last Subcategory of each Category is its catch-all."""

from django.db import migrations

SPENDING = {
    "Food": ["Groceries", "Restaurants & cafés", "Fast food & takeaway", "Other"],
    "Home": ["Rent / mortgage", "Utilities", "Internet & phone", "Furniture & household", "Maintenance & repairs", "Other"],
    "Transport": [
        "Fuel", "Parking & tolls", "Car maintenance", "Car insurance & registration", "Public transport & car sharing",
        "Other",
    ],
    "Health": ["Pharmacy", "Doctor & dental", "Health insurance", "Other"],
    "Children": ["Childcare & school", "Activities", "Clothes & toys", "Other"],
    "Shopping": ["Clothing & shoes", "Electronics", "Gifts", "Personal care", "Other"],
    "Leisure": ["Travel", "Hobbies & sport", "Entertainment & going out", "Subscriptions & digital services", "Other"],
    "Finance": ["Bank fees", "Insurance (non-health)", "Taxes & fines", "Other"],
    "Other": ["Cash withdrawal", "Payments to people", "Miscellaneous"],
}
INCOME = {
    "Income": ["Salary", "Benefits & allowances", "Interest", "Gifts received", "Other income"],
}


def seed(apps, schema_editor):
    Category = apps.get_model("ledger", "Category")
    Subcategory = apps.get_model("ledger", "Subcategory")
    lists = [(name, "spending", subs) for name, subs in SPENDING.items()]
    lists += [(name, "income", subs) for name, subs in INCOME.items()]
    for position, (name, kind, subcategories) in enumerate(lists):
        category = Category.objects.create(name=name, kind=kind, position=position)
        Subcategory.objects.bulk_create(
            Subcategory(category=category, name=sub, position=i, is_catch_all=i == len(subcategories) - 1)
            for i, sub in enumerate(subcategories)
        )


class Migration(migrations.Migration):
    dependencies = [("ledger", "0002_categories_and_outcomes")]

    operations = [migrations.RunPython(seed, migrations.RunPython.noop)]
