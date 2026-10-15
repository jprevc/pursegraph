from django.utils.functional import SimpleLazyObject

from . import queries


def this_month(request):
    # Lazy, so it is only queried when a template shows it.
    return {"this_month": SimpleLazyObject(queries.this_month)}
