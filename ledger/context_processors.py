from .models import Transaction


def review_queue(request):
    # A callable, so the count is only queried when a template shows it.
    return {"review_queue_count": lambda: Transaction.objects.in_review_queue().count()}
