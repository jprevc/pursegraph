from collections.abc import Callable
from dataclasses import dataclass

from django.http import Http404
from django.shortcuts import render
from django.urls import reverse
from django.utils.cache import patch_vary_headers
from django.utils.http import urlencode

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


def _filter_query(filters: queries.Filters) -> str:
    """The filters as query parameters to append to a link that names its period: "&member=…&account=…"."""
    return f"&{urlencode(filters.params)}" if filters.params else ""


def carried_queries(carried: list[tuple[str, str]]) -> dict[str, str]:
    """What the sidebar's links add to carry a period chosen and the filters: the dashboard views' links name them
    directly, and the other pages' links hold them in one `dashboard` parameter, apart from their own (the
    Transactions page has an `account` of its own), so that their links back to the views can name them again."""
    return {
        "carried_query": f"?{urlencode(carried)}" if carried else "",
        "carried_page_query": f"?{urlencode({'dashboard': urlencode(carried)})}" if carried else "",
    }


def _period_chosen(params) -> bool:
    return bool(params.get("period") or params.get("from"))


def _carried(
    period: Period, period_chosen: bool, filters: queries.Filters
) -> list[tuple[str, str]]:
    """The query parameters that carry a period, if one is chosen, and the filters to the other views."""
    return ([("period", period.token)] if period_chosen else []) + filters.params


def carried_params(params) -> list[tuple[str, str]]:
    """The query parameters that carry a request's period, if one is chosen, and its filters to the other views."""
    return _carried(
        Period.from_query(params), _period_chosen(params), queries.Filters.from_query(params)
    )


def show(request, view: str):
    """A dashboard view, or where to start on an empty installation."""
    v = _view(view)
    if not Statement.objects.exists() and not Transaction.objects.exists():
        return render(request, "dashboard/empty.html")
    period = Period.from_query(request.GET, v.default_period)
    filters = queries.Filters.from_query(request.GET)
    filter_query = _filter_query(filters)
    # A period chosen carries to the other views too; otherwise each opens on its own default.
    period_chosen = _period_chosen(request.GET)
    data = queries.view_data(v.name, period, filters)
    view_template = f"dashboard/_{v.name}.html"
    members, accounts = queries.filter_choices()
    context = {
        "view": v.name,
        "view_url": reverse(v.name),
        "period": period,
        "period_chosen": period_chosen,
        "filters": filters,
        "filter_query": filter_query,
        "members": members,
        "accounts": accounts,
        **carried_queries(_carried(period, period_chosen, filters)),
        "data": data,
        # A mark's drill-down address is `drill` plus its key.
        "chart": {
            **data.chart,
            "drill": f"{reverse(v.name + '_transactions')}?period={period.token}{filter_query}"
            f"&{v.mark_param}=",
        },
        "view_template": view_template,
        # Swapped in alone, the view also brings the sidebar's links, so that they carry its period and filters.
        "swap_nav": _wants_the_view_alone(request),
    }
    template = view_template if _wants_the_view_alone(request) else "dashboard/dashboard.html"
    response = render(request, template, context)
    patch_vary_headers(response, ["HX-Request", "HX-History-Restore-Request"])
    return response


def transactions(request, view: str):
    """The drill-down: the Transactions behind one chart mark, as rows with inline outcome editing."""
    v = _view(view)
    period = Period.from_query(request.GET, v.default_period)
    filters = queries.Filters.from_query(request.GET)
    rows = queries.drill_down(
        v.name, period, filters, request.GET.get(v.mark_param, "")
    ).select_related("account")
    return render(
        request,
        "dashboard/_drill_down.html",
        {
            "transactions": rows,
            "categories": categories_with_subcategories(),
            # Without HTMX, saving an outcome goes back to the view rather than to this fragment.
            "next": f"{reverse(v.name)}?period={period.token}{_filter_query(filters)}",
        },
    )
