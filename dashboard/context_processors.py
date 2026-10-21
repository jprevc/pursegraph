from django.http import QueryDict

from . import views


def carried(request):
    """On the pages other than the dashboard views, the period and filters their `dashboard` parameter carries,
    for the sidebar's links. A dashboard view sets its own."""
    query = request.GET.get("dashboard")
    return views.carried_queries(views.carried_params(QueryDict(query))) if query else {}
