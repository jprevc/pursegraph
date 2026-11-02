"""Setup mode (docs/design/empty-states.md): until the Household's first Statement, the Dashboard is Get started and
the navigation offers only what works yet."""

from django.contrib.auth import get_user_model

from .models import Statement, Transaction


def in_setup_mode() -> bool:
    """Whether the Household has no Statement yet. Transactions only ever arrive on a Statement, so in use that is
    all it asks; Transactions made without one, as tests make them, count as imported too."""
    return not Statement.objects.exists() and not Transaction.objects.exists()


def others_invited() -> bool:
    """Whether a second active Member exists: Get started's invite step is done."""
    return get_user_model().objects.filter(is_active=True).count() > 1
