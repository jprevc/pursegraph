from django.utils.functional import SimpleLazyObject

from .models import Transaction
from .setup import in_setup_mode


def review_queue(request):
    # Only queried when a template shows them, and lazily, so once however often it shows.
    return {
        "review_queue_count": SimpleLazyObject(
            lambda: Transaction.objects.in_review_queue().count()
        ),
        # Until the first Statement the shell offers only what works yet; asked once, by the navigation.
        "setup_mode": SimpleLazyObject(in_setup_mode),
    }
