from django.shortcuts import render
from django.urls import reverse
from django.utils.cache import patch_vary_headers

from ledger.models import Statement, Transaction
from ledger.views import categories_with_subcategories

from . import queries
from .periods import Period


def _wants_the_view_alone(request) -> bool:
    """HTMX swapping a view in. Restoring history after a cache miss needs the whole page."""
    return bool(
        request.headers.get("HX-Request") and not request.headers.get("HX-History-Restore-Request")
    )


def dashboard(request):
    """The landing page: Spending by Category."""
    return spending(request)


def spending(request):
    """Spending by Category, or where to start on an empty installation."""
    if not Statement.objects.exists() and not Transaction.objects.exists():
        return render(request, "dashboard/empty.html")
    period = Period.from_query(request.GET)
    data = queries.view_data("spending", period, queries.Filters())
    context = {
        "view_url": reverse("spending"),
        "period": period,
        "data": data,
        # A mark's drill-down address is this plus its key.
        "chart": {
            "bars": data.series,
            "drill": f"{reverse('spending_transactions')}?period={period.token}&category=",
        },
    }
    template = (
        "dashboard/_spending.html" if _wants_the_view_alone(request) else "dashboard/dashboard.html"
    )
    response = render(request, template, context)
    patch_vary_headers(response, ["HX-Request", "HX-History-Restore-Request"])
    return response


def spending_transactions(request):
    """The drill-down: the Transactions behind one chart mark, as rows with inline outcome editing."""
    period = Period.from_query(request.GET)
    transactions = queries.drill_down(
        "spending", period, queries.Filters(), request.GET.get("category", "")
    ).select_related("account")
    return render(
        request,
        "dashboard/_drill_down.html",
        {
            "transactions": transactions,
            "categories": categories_with_subcategories(),
            # Without HTMX, saving an outcome goes back to the view rather than to this fragment.
            "next": f"{reverse('spending')}?period={period.token}",
        },
    )
