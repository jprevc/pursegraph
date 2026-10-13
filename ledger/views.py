import base64

from django.db.models import Count, Prefetch
from django.shortcuts import render

from .forms import AccountForm, StatementFileForm
from .importer import ImportRejected, check_statement, commit_statement
from .models import Account, Bank, Statement, Transaction


def import_statements(request):
    """Upload a Statement. When its IBAN doesn't identify the Account, a second step asks for it,
    carrying the file along; posting `account` with the file skips straight to that step's answer."""
    form = StatementFileForm()
    summary = rejection = account_form = pending = None
    if request.method == "POST":
        posted = StatementFileForm(request.POST, request.FILES)
        if not posted.is_valid():
            form = posted
        else:
            content, filename = posted.cleaned_data["content"], posted.cleaned_data["filename"]
            try:
                checked = check_statement(content=content, filename=filename)
                choosing = "account" in request.POST
                if checked.account and not choosing:
                    summary = commit_statement(checked, member=request.user, account=checked.account)
                else:
                    account_form = AccountForm(request.POST if choosing else None, statement=checked)
                    if choosing and account_form.is_valid():
                        summary = commit_statement(checked, member=request.user, account=account_form.chosen_account())
                    else:
                        pending = {
                            "form": StatementFileForm(initial={
                                "content": base64.b64encode(content).decode(), "filename": filename,
                            }),
                            "statement": checked.parsed, "bank": Bank(checked.parsed.bank).label,
                        }
            except ImportRejected as error:
                rejection = error

    statements = Statement.objects.select_related("imported_by").annotate(transaction_count=Count("transactions"))
    accounts = Account.objects.prefetch_related("owners", "ibans", Prefetch("statements", queryset=statements))
    return render(request, "ledger/import.html", {
        "form": form, "summary": summary, "rejection": rejection, "accounts": accounts,
        "account_form": account_form, "pending": pending,
    })


def transactions(request):
    rows = Transaction.objects.select_related("account").order_by("-date", "-id")
    return render(request, "ledger/transactions.html", {"transactions": rows})
