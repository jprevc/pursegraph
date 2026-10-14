from .models import Transaction
from .suggestions import suggestions_unavailable


def review_queue(request):
    # Callables, so they are only queried when a template shows them.
    return {
        "review_queue_count": lambda: Transaction.objects.unresolved().count(),
        "suggestions_unavailable": suggestions_unavailable,
    }
