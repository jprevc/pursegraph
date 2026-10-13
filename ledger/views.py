import base64

from django.db.models import Count, Prefetch
from django.shortcuts import render

from .forms import AccountForm, StatementFileForm
from .importer import (
    CheckedStatement,
    FileResult,
    ImportRejected,
    NewAccount,
    check_statement,
    commit_statement,
)
from .models import Account, Bank, Statement, Transaction


def import_statements(request):
    """Upload Statements, several at once, each accepted or rejected on its own.

    Every file is checked first; the rest are then imported in period order, so each one's
    Duplicate check sees the Coverage the earlier ones left. A file goes into the Account its
    IBAN identifies; otherwise a second step asks for the Account, carrying the file along.
    Posting `account` with the files skips straight to that step's answer, for every file that
    needs one; a new Account it names is created by the first such file, and later files of that
    bank go into it.
    """
    form = StatementFileForm()
    results: list[FileResult] = []
    pending: list[dict] = []
    if request.method == "POST":
        posted = StatementFileForm(request.POST, request.FILES)
        if not posted.is_valid():
            form = posted
        else:
            checked: list[CheckedStatement] = []
            for filename, content in posted.cleaned_data["files"]:
                try:
                    checked.append(check_statement(content=content, filename=filename))
                except ImportRejected as error:
                    results.append(FileResult(filename, rejection=error))
            choosing = "account" in request.POST
            created: dict[str, Account] = {}
            for statement in sorted(
                checked, key=lambda c: (c.parsed.period_start, c.parsed.period_end)
            ):
                account: Account | NewAccount
                if statement.account and not choosing:
                    account = statement.account
                else:
                    account_form = AccountForm(
                        request.POST if choosing else None,
                        statement=statement,
                        auto_id=f"id_{len(pending)}_%s",
                    )
                    if not (choosing and account_form.is_valid()):
                        pending.append(_account_step(statement, account_form))
                        continue
                    account = account_form.chosen_account()
                    if isinstance(account, NewAccount):
                        account = created.get(statement.parsed.bank, account)
                try:
                    summary = commit_statement(statement, member=request.user, account=account)
                except ImportRejected as error:
                    results.append(FileResult(statement.filename, rejection=error))
                else:
                    results.append(FileResult(statement.filename, summary=summary))
                    if isinstance(account, NewAccount):
                        created[statement.parsed.bank] = summary.account

    statements = Statement.objects.select_related("imported_by").annotate(
        transaction_count=Count("transactions")
    )
    accounts = Account.objects.prefetch_related(
        "owners", "ibans", Prefetch("statements", queryset=statements)
    )
    return render(
        request,
        "ledger/import.html",
        {
            "form": form,
            "results": results,
            "pending": pending,
            "accounts": accounts,
        },
    )


def _account_step(statement: CheckedStatement, account_form: AccountForm) -> dict:
    """The second step for a Statement whose Account isn't known: the file, carried along, and the Account form."""
    return {
        "form": StatementFileForm(
            initial={
                "content": base64.b64encode(statement.content).decode(),
                "filename": statement.filename,
            }
        ),
        "statement": statement.parsed,
        "bank": Bank(statement.parsed.bank).label,
        "account_form": account_form,
    }


def transactions(request):
    rows = Transaction.objects.select_related("account").order_by("-date", "-id")
    return render(request, "ledger/transactions.html", {"transactions": rows})
