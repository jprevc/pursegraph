from django.shortcuts import render
from django.urls import reverse

from ledger.models import Statement, Transaction
from ledger.views import categories_with_subcategories

from . import queries
from .periods import Period


def dashboard(request):
    """The landing page: Spending by Category, or where to start on an empty installation."""
    if not Statement.objects.exists() and not Transaction.objects.exists():
        return render(request, "dashboard/empty.html")
    return spending(request)


def spending(request):
    """Spending by Category. HTMX swaps it in alone; anything else gets the whole page."""
    period = Period.from_query(request.GET)
    data = queries.view_data("spending", period, queries.Filters())
    drill = f"{reverse('spending_transactions')}?period={period.token}"
    context = {
        "view": "spending",
        "view_url": reverse("spending"),
        "period": period,
        "data": data,
        "chart": {"bars": data.series, "drill": drill},
    }
    template = (
        "dashboard/_spending.html"
        if request.headers.get("HX-Request")
        else "dashboard/dashboard.html"
    )
    return render(request, template, context)


def spending_transactions(request):
    """The drill-down: the Transactions behind one chart mark, as rows with inline outcome editing."""
    period = Period.from_query(request.GET)
    rows = queries.drill_down(
        "spending", period, queries.Filters(), request.GET.get("category", "")
    ).select_related("account")
    return render(
        request,
        "dashboard/_drill_down.html",
        {"transactions": rows, "categories": categories_with_subcategories()},
    )
