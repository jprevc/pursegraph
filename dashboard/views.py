from django.shortcuts import render


def dashboard(request):
    # No Statements can be imported yet, so the dashboard is always empty.
    return render(request, "dashboard/dashboard.html")


def import_statements(request):
    return render(request, "dashboard/import.html")


def review_queue(request):
    return render(request, "dashboard/review_queue.html")
