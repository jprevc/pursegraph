from collections.abc import Callable
from dataclasses import dataclass

from django.http import Http404
from django.shortcuts import render
from django.urls import reverse
from django.utils.cache import patch_vary_headers

from ledger.models import Statement, Transaction
from ledger.views import categories_with_subcategories

from . import queries
from .periods import Period


@dataclass(frozen=True)
class View:
    """A dashboard view at /<path>/, its drill-down at /<path>/transactions/; their URL names are `name` and
    "<name>_transactions"."""

    name: str
    path: str
    # The drill-down's query parameter naming the chart mark.
    mark_param: str = "key"
    default_period: Callable[[], Period] = Period.default


VIEWS = {
    v.name: v
    for v in [
        View("spending", "spending", "category"),
        View("cashflow", "cashflow"),
        View("trends", "trends", default_period=Period.last_12_months),
        View("per_member", "per-member"),
        View("money_flow", "money-flow"),
    ]
}


def _wants_the_view_alone(request) -> bool:
    """HTMX swapping a view in. Restoring history after a cache miss needs the whole page."""
    return bool(
        request.headers.get("HX-Request") and not request.headers.get("HX-History-Restore-Request")
    )


def _view(name: str) -> View:
    if name not in VIEWS:
        raise Http404
    return VIEWS[name]


def dashboard(request):
    """The landing page: Spending by Category."""
    return show(request, "spending")


def show(request, view: str):
    """A dashboard view, or where to start on an empty installation."""
    v = _view(view)
    if not Statement.objects.exists() and not Transaction.objects.exists():
        return render(request, "dashboard/empty.html")
    period = Period.from_query(request.GET, v.default_period)
    data = queries.view_data(v.name, period, queries.Filters())
    view_template = f"dashboard/_{v.name}.html"
    context = {
        "view": v.name,
        "view_url": reverse(v.name),
        "period": period,
        "data": data,
        # A mark's drill-down address is `drill` plus its key.
        "chart": {
            **data.chart,
            "drill": f"{reverse(v.name + '_transactions')}?period={period.token}&{v.mark_param}=",
        },
        "view_template": view_template,
    }
    template = view_template if _wants_the_view_alone(request) else "dashboard/dashboard.html"
    response = render(request, template, context)
    patch_vary_headers(response, ["HX-Request", "HX-History-Restore-Request"])
    return response


def transactions(request, view: str):
    """The drill-down: the Transactions behind one chart mark, as rows with inline outcome editing."""
    v = _view(view)
    period = Period.from_query(request.GET, v.default_period)
    rows = queries.drill_down(
        v.name, period, queries.Filters(), request.GET.get(v.mark_param, "")
    ).select_related("account")
    return render(
        request,
        "dashboard/_drill_down.html",
        {
            "transactions": rows,
            "categories": categories_with_subcategories(),
            # Without HTMX, saving an outcome goes back to the view rather than to this fragment.
            "next": f"{reverse(v.name)}?period={period.token}",
        },
    )
