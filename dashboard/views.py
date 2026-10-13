from django.shortcuts import render

from ledger.models import Statement


def dashboard(request):
    # The charts aren't built yet; the dashboard only tells an empty installation where to start.
    return render(
        request, "dashboard/dashboard.html", {"has_statements": Statement.objects.exists()}
    )
