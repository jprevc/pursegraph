from django.db.models import Count, Prefetch
from django.shortcuts import render

from .forms import ImportForm
from .importer import ImportRejected, import_statement
from .models import Account, Statement, Transaction


def import_statements(request):
    summary = rejection = None
    if request.method == "POST":
        form = ImportForm(request.POST, request.FILES)
        if form.is_valid():
            upload = form.cleaned_data["file"]
            try:
                summary = import_statement(
                    content=upload.read(), filename=upload.name, member=request.user, account=form.chosen_account(),
                )
                form = ImportForm()
            except ImportRejected as error:
                rejection = error
    else:
        form = ImportForm()

    statements = Statement.objects.select_related("imported_by").annotate(transaction_count=Count("transactions"))
    accounts = Account.objects.prefetch_related("owners", Prefetch("statements", queryset=statements))
    return render(request, "ledger/import.html", {
        "form": form, "summary": summary, "rejection": rejection, "accounts": accounts,
    })


def transactions(request):
    rows = Transaction.objects.select_related("account").order_by("-date", "-id")
    return render(request, "ledger/transactions.html", {"transactions": rows})
