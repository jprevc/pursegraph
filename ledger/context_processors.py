from django.utils.functional import SimpleLazyObject

from .models import Transaction
from .suggestions import suggestions_unavailable


def review_queue(request):
    # Lazy, so they are only queried when a template shows them (the count once, however often it shows).
    return {
        "review_queue_count": SimpleLazyObject(
            lambda: Transaction.objects.in_review_queue().count()
        ),
        "suggestions_unavailable": suggestions_unavailable,
    }
