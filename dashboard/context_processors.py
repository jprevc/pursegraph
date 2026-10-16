from django.http import QueryDict
from django.utils.functional import SimpleLazyObject

from . import queries, views


def this_month(request):
    # Lazy, so it is only queried when a template shows it.
    return {"this_month": SimpleLazyObject(queries.this_month)}


def carried(request):
    """On the pages other than the dashboard views, the period and filters their `dashboard` parameter carries,
    for the sidebar's links. A dashboard view sets its own."""
    query = request.GET.get("dashboard")
    return views.carried_queries(views.carried_params(QueryDict(query))) if query else {}
