from django.utils.functional import SimpleLazyObject

from .models import Transaction
from .setup import in_setup_mode
from .suggestions import suggestions_unavailable


def review_queue(request):
    # Only queried when a template shows them: the count is lazy (so once, however often it shows), the status a callable.
    return {
        "review_queue_count": SimpleLazyObject(
            lambda: Transaction.objects.in_review_queue().count()
        ),
        "suggestions_unavailable": suggestions_unavailable,
        # Until the first Statement the shell offers only what works yet; asked once, by the navigation.
        "setup_mode": SimpleLazyObject(in_setup_mode),
    }
