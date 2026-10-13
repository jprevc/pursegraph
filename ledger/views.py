from django.db.models import Count, Prefetch
from django.shortcuts import render

from .coverage import coverage, timeline
from .forms import ImportForm
from . import importer
from .models import Account, Statement, Transaction


def import_statements(request):
    results = []
    if request.method == "POST":
        form = ImportForm(request.POST, request.FILES)
        if form.is_valid():
            results = importer.import_statements(
                files=[(upload.name, upload.read()) for upload in form.cleaned_data["file"]],
                member=request.user, account=form.chosen_account(),
            )
            form = ImportForm()
    else:
        form = ImportForm()

    statements = Statement.objects.select_related("imported_by").annotate(transaction_count=Count("transactions"))
    accounts = Account.objects.prefetch_related("owners", Prefetch("statements", queryset=statements))
    for account in accounts:
        account.coverage_timeline = timeline(coverage(account.statements.all()))
    return render(request, "ledger/import.html", {
        "form": form, "results": results, "accounts": accounts,
    })


def transactions(request):
    rows = Transaction.objects.select_related("account").order_by("-date", "-id")
    return render(request, "ledger/transactions.html", {"transactions": rows})
