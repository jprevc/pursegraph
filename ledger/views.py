import base64

from django.contrib import messages
from django.core.paginator import Paginator
from django.db.models import Count, Prefetch
from django.http import HttpResponseBadRequest
from django.shortcuts import get_object_or_404, redirect, render
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.http import require_POST

from members.permissions import admin_required

from . import categories as category_edits
from .forms import (
    AccountForm,
    CategoryForm,
    NameForm,
    OutcomeForm,
    StatementFileForm,
    TransactionFilterForm,
)
from .importer import ImportRejected, check_statement, commit_statement
from .models import Account, Bank, Category, Statement, Subcategory, Transaction

TRANSACTIONS_PER_PAGE = 100


def categories_with_subcategories():
    """The Categories with their Subcategories prefetched, for outcome dropdowns and the Categories page."""
    return list(Category.objects.prefetch_related("subcategories"))


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
                    summary = commit_statement(
                        checked, member=request.user, account=checked.account
                    )
                else:
                    account_form = AccountForm(
                        request.POST if choosing else None, statement=checked
                    )
                    if choosing and account_form.is_valid():
                        summary = commit_statement(
                            checked, member=request.user, account=account_form.chosen_account()
                        )
                    else:
                        pending = {
                            "form": StatementFileForm(
                                initial={
                                    "content": base64.b64encode(content).decode(),
                                    "filename": filename,
                                }
                            ),
                            "statement": checked.parsed,
                            "bank": Bank(checked.parsed.bank).label,
                        }
            except ImportRejected as error:
                rejection = error

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
            "summary": summary,
            "rejection": rejection,
            "accounts": accounts,
            "account_form": account_form,
            "pending": pending,
        },
    )


def transactions(request):
    categories = categories_with_subcategories()
    form = TransactionFilterForm(request.GET, categories=categories)
    rows = form.filter(Transaction.objects.select_related("account").order_by("-date", "-id"))
    page = Paginator(rows, TRANSACTIONS_PER_PAGE).get_page(request.GET.get("page"))
    query = request.GET.copy()
    query.pop("page", None)
    return render(
        request,
        "ledger/transactions.html",
        {
            "form": form,
            "page": page,
            "query": query.urlencode(),
            "categories": categories,
            "any_transactions": page.paginator.count or Transaction.objects.exists(),
        },
    )


def review_queue(request):
    rows = Transaction.objects.unresolved().select_related("account").order_by("date", "id")
    return render(
        request,
        "ledger/review_queue.html",
        {"transactions": rows, "categories": categories_with_subcategories()},
    )


@require_POST
def transaction_outcome(request, pk):
    """Sets a Transaction's outcome by hand. HTMX gets the updated row back; a plain form post goes back to `next`."""
    transaction = get_object_or_404(Transaction.objects.select_related("account"), pk=pk)
    form = OutcomeForm(request.POST)
    if not form.is_valid():
        return HttpResponseBadRequest(form.errors.as_text())
    form.save(transaction)
    if request.headers.get("HX-Request"):
        return render(
            request,
            "ledger/_transaction_row.html",
            {
                "t": transaction,
                "categories": categories_with_subcategories(),
                "refresh_review_queue_count": True,
            },
        )
    next_url = request.POST.get("next", "")
    if not url_has_allowed_host_and_scheme(next_url, allowed_hosts={request.get_host()}):
        next_url = "transactions"
    return redirect(next_url)


@admin_required
def categories(request):
    return render(
        request,
        "ledger/categories.html",
        {
            "categories": categories_with_subcategories(),
            "kinds": Category.Kind.choices,
        },
    )


def _category_edit(view):
    """An admin-only POST that edits the Category list, then goes back to the Categories page with any refusal
    or form error shown."""

    @admin_required
    @require_POST
    def wrapper(request, *args, **kwargs):
        try:
            view(request, *args, **kwargs)
        except category_edits.CategoryEditRefused as refusal:
            messages.error(request, str(refusal))
        return redirect("categories")

    return wrapper


def _cleaned_data_or_errors(request, form):
    if not form.is_valid():
        for errors in form.errors.values():
            for error in errors:
                messages.error(request, error)
        return None
    return form.cleaned_data


@_category_edit
def add_category(request):
    if data := _cleaned_data_or_errors(request, CategoryForm(request.POST)):
        category_edits.add_category(data["name"].strip(), data["kind"])


@_category_edit
def rename_category(request, pk):
    category = get_object_or_404(Category, pk=pk)
    if data := _cleaned_data_or_errors(request, NameForm(request.POST)):
        category_edits.rename(category, data["name"].strip())


@_category_edit
def move_category(request, pk):
    category_edits.move_category(get_object_or_404(Category, pk=pk), request.POST.get("direction"))


@_category_edit
def delete_category(request, pk):
    category_edits.delete_category(get_object_or_404(Category, pk=pk))


@_category_edit
def add_subcategory(request, pk):
    category = get_object_or_404(Category, pk=pk)
    if data := _cleaned_data_or_errors(request, NameForm(request.POST)):
        category_edits.add_subcategory(category, data["name"].strip())


@_category_edit
def rename_subcategory(request, pk):
    subcategory = get_object_or_404(Subcategory, pk=pk)
    if data := _cleaned_data_or_errors(request, NameForm(request.POST)):
        category_edits.rename(subcategory, data["name"].strip())


@_category_edit
def move_subcategory(request, pk):
    category_edits.move_subcategory(
        get_object_or_404(Subcategory, pk=pk), request.POST.get("direction")
    )


@_category_edit
def delete_subcategory(request, pk):
    category_edits.delete_subcategory(get_object_or_404(Subcategory, pk=pk))
