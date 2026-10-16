import base64

from django.contrib import messages
from django.contrib.auth import get_user_model
from django.core.exceptions import PermissionDenied
from django.core.paginator import Paginator
from django.db import IntegrityError
from django.db import transaction as db_transaction
from django.db.models import Count, Prefetch
from django.http import HttpResponseBadRequest
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils.cache import patch_vary_headers
from django.utils.formats import date_format
from django.utils.http import url_has_allowed_host_and_scheme
from django.utils.translation import gettext as _
from django.utils.translation import ngettext
from django.views.decorators.http import require_http_methods, require_POST

from members.permissions import admin_required

from . import categories as category_edits
from . import rules as rule_edits
from . import suggestions
from .forms import (
    AccountAdminForm,
    AccountForm,
    CategoryForm,
    NameForm,
    OutcomeForm,
    RuleForm,
    StatementFileForm,
    ThresholdForm,
    TransactionFilterForm,
)
from .importer import (
    CheckedStatement,
    FileResult,
    ImportRejected,
    NewAccount,
    check_statement,
    commit_statement,
)
from .models import Account, Bank, Category, Rule, Source, Statement, Subcategory, Transaction

TRANSACTIONS_PER_PAGE = 100


def categories_with_subcategories():
    """The Categories with their Subcategories prefetched, for outcome dropdowns and the Categories page."""
    return list(Category.objects.prefetch_related("subcategories"))


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


@admin_required
def accounts(request):
    return render(
        request,
        "ledger/accounts.html",
        {
            "accounts": Account.objects.prefetch_related(
                Prefetch("owners", queryset=get_user_model().objects.order_by("username")), "ibans"
            ).annotate(statement_count=Count("statements"))
        },
    )


@admin_required
def new_account(request):
    return _account_form(request, Account())


@admin_required
def edit_account(request, pk):
    return _account_form(request, get_object_or_404(Account, pk=pk))


def _account_form(request, account):
    if request.method != "POST":
        form = AccountAdminForm(instance=account)
        return render(request, "ledger/account_form.html", {"form": form})
    try:
        with db_transaction.atomic():
            if account.pk:
                # Serialized with imports into the Account, so it keeps its bank once one lands.
                account = Account.objects.select_for_update().get(pk=account.pk)
            form = AccountAdminForm(request.POST, instance=account)
            if form.is_valid():
                form.save()
                return redirect("accounts")
    except IntegrityError:
        # Another admin gave one of the IBANs to an Account in the meantime.
        form.add_error("ibans", _("One of these IBANs was just added to another Account."))
    return render(request, "ledger/account_form.html", {"form": form})


@admin_required
@require_http_methods(["GET", "POST"])
def delete_account(request, pk):
    """Deletes an Account after a confirmation, with the Rules only for it; refused while it has Statements,
    whose Transactions would go with it."""
    if request.method == "GET":
        account = get_object_or_404(Account, pk=pk)
        return render(
            request,
            "ledger/delete_account.html",
            {
                "account": account,
                "has_statements": account.statements.exists(),
                "rule_count": account.rules.count(),
            },
        )
    with db_transaction.atomic():
        # Serialized with imports into the Account.
        account = get_object_or_404(Account.objects.select_for_update(), pk=pk)
        if account.statements.exists():
            messages.error(
                request,
                _(
                    "%(account)s has Statements, so it can't be deleted. Delete its Statements first."
                )
                % {"account": account.name},
            )
        else:
            account.delete()
            messages.success(request, _("Deleted %(account)s.") % {"account": account.name})
    return redirect("accounts")


@require_http_methods(["GET", "POST"])
def delete_statement(request, pk):
    """Deletes a Statement after a confirmation; only its importer or an admin may."""
    statement = get_object_or_404(Statement.objects.select_related("account"), pk=pk)
    if not statement.can_be_deleted_by(request.user):
        raise PermissionDenied
    if request.method == "POST":
        statement.delete_with_transactions()
        messages.success(
            request,
            _("Deleted the %(account)s Statement %(start)s – %(end)s.")
            % {
                "account": statement.account.name,
                "start": date_format(statement.period_start, "j M Y"),
                "end": date_format(statement.period_end, "j M Y"),
            },
        )
        return redirect("import")
    return render(
        request,
        "ledger/delete_statement.html",
        {
            "statement": statement,
            "transaction_count": statement.own_transactions().count(),
            "manual_outcome_count": statement.lost_manual_outcome_count(),
        },
    )


def wants_the_fragment_alone(request) -> bool:
    """HTMX swapping a page's content in. Restoring history after a cache miss needs the whole page."""
    return bool(
        request.headers.get("HX-Request") and not request.headers.get("HX-History-Restore-Request")
    )


def transactions(request):
    """Every Transaction, filtered and paged. The sidebar swaps it into the main area via HTMX."""
    categories = categories_with_subcategories()
    form = TransactionFilterForm(request.GET, categories=categories)
    rows = form.filter(Transaction.objects.select_related("account").order_by("-date", "-id"))
    page = Paginator(rows, TRANSACTIONS_PER_PAGE).get_page(request.GET.get("page"))
    query = request.GET.copy()
    query.pop("page", None)
    alone = wants_the_fragment_alone(request)
    response = render(
        request,
        "ledger/_transactions.html" if alone else "ledger/transactions.html",
        {
            "form": form,
            "page": page,
            "query": query.urlencode(),
            "categories": categories,
            "any_transactions": page.paginator.count or Transaction.objects.exists(),
            # Swapped in alone, it also brings the sidebar's links, so that Transactions is highlighted and the
            # dashboard views no longer swap into a view that has left the page.
            "swap_nav": alone,
        },
    )
    patch_vary_headers(response, ["HX-Request", "HX-History-Restore-Request"])
    return response


def review_queue(request):
    rows = list(
        Transaction.objects.in_review_queue().select_related("account").order_by("date", "id")
    )
    return render(
        request,
        "ledger/review_queue.html",
        {
            "transactions": rows,
            "suggested": [t for t in rows if t.pending_suggestion_id],
            "categories": categories_with_subcategories(),
        },
    )


@require_POST
def accept_suggestions(request):
    """Accepts the suggestions the Review queue showed, each `accept` a "<Transaction id>:<Subcategory id>", as
    manual outcomes. Transactions decided since are left alone."""
    shown: dict[int, int] = {}
    for value in request.POST.getlist("accept"):
        transaction_pk, _sep, subcategory_pk = value.partition(":")
        if not (transaction_pk.isdigit() and subcategory_pk.isdigit()):
            return HttpResponseBadRequest()
        shown[int(transaction_pk)] = int(subcategory_pk)
    subcategories = Subcategory.objects.in_bulk(shown.values())
    count = 0
    with db_transaction.atomic():
        for t in Transaction.objects.unresolved().select_for_update().filter(pk__in=shown):
            if subcategory := subcategories.get(shown[t.pk]):
                t.set_outcome(subcategory, source=Source.MANUAL)
                count += 1
    _suggestions_accepted(request, count)
    return redirect("review_queue")


@require_POST
def transaction_outcome(request, pk):
    """Sets a Transaction's outcome by hand. HTMX gets the updated row back; a plain form post goes back to `next`."""
    transaction = get_object_or_404(Transaction.objects.select_related("account"), pk=pk)
    form = OutcomeForm(request.POST, transaction=transaction)
    if not form.is_valid():
        return HttpResponseBadRequest(form.errors.as_text())
    form.save()
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


@admin_required
@require_http_methods(["GET", "POST"])
def suggestion_settings(request):
    """The auto-accept threshold and re-suggesting. Right after lowering the threshold (`?lowered`), it offers
    the queued suggestions that now clear it."""
    form = ThresholdForm(request.POST or None, initial={"threshold": suggestions.threshold()})
    if form.is_valid():
        lowered = form.cleaned_data["threshold"] < suggestions.threshold()
        suggestions.set_threshold(form.cleaned_data["threshold"])
        return redirect(reverse("suggestion_settings") + ("?lowered" if lowered else ""))
    offered = (
        list(suggestions.suggestions_clearing_threshold().values_list("pk", flat=True))
        if "lowered" in request.GET
        else []
    )
    return render(request, "ledger/suggestion_settings.html", {"form": form, "offered": offered})


@admin_required
@require_POST
def accept_clearing_suggestions(request):
    """Accepts the offered suggestions, each `accept` a Transaction id, that still clear the threshold."""
    pks = request.POST.getlist("accept")
    if not all(pk.isdigit() for pk in pks):
        return HttpResponseBadRequest()
    _suggestions_accepted(request, suggestions.accept_suggestions_clearing_threshold(map(int, pks)))
    return redirect("suggestion_settings")


@admin_required
@require_POST
def resuggest_queue(request):
    count = suggestions.resuggest_queue()
    messages.success(
        request,
        ngettext(
            "%(count)d suggestion cleared; the LLM will be asked again.",
            "%(count)d suggestions cleared; the LLM will be asked again.",
            count,
        )
        % {"count": count},
    )
    return redirect("suggestion_settings")


def _suggestions_accepted(request, count: int) -> None:
    messages.success(
        request,
        ngettext("%(count)d suggestion accepted.", "%(count)d suggestions accepted.", count)
        % {"count": count},
    )


def rules(request):
    return render(
        request,
        "ledger/rules.html",
        {"rules": Rule.objects.select_related("account", "subcategory__category")},
    )


def new_rule(request):
    """A new Rule; `?transaction=<pk>` pre-fills it from a corrected Transaction ("Make a Rule")."""
    if request.method == "POST":
        return _save_rule(request, RuleForm(request.POST))
    transaction_pk = request.GET.get("transaction", "")
    if transaction_pk.isdigit():
        form = RuleForm.from_transaction(get_object_or_404(Transaction, pk=transaction_pk))
    else:
        form = RuleForm()
    return render(request, "ledger/rule_form.html", {"form": form})


def edit_rule(request, pk):
    rule = get_object_or_404(Rule, pk=pk)
    if request.method == "POST":
        return _save_rule(request, RuleForm(request.POST, instance=rule))
    return render(request, "ledger/rule_form.html", {"form": RuleForm(instance=rule)})


def _save_rule(request, form):
    """Saves the Rule, then offers to apply it to the existing Transactions it matches, if any."""
    if not form.is_valid():
        return render(request, "ledger/rule_form.html", {"form": form})
    rule = form.save()
    if rule_edits.overwritable_matches(rule).exists():
        return redirect("apply_rule", rule.pk)
    return redirect("rules")


def apply_rule(request, pk):
    """GET offers to apply the Rule to the existing Transactions it matches; POST applies it."""
    rule = get_object_or_404(Rule.objects.select_related("account", "subcategory__category"), pk=pk)
    if request.method == "POST":
        count = rule_edits.apply_to_existing(rule)
        messages.success(
            request,
            ngettext(
                "%(count)d Transaction categorized by the Rule.",
                "%(count)d Transactions categorized by the Rule.",
                count,
            )
            % {"count": count},
        )
        return redirect("rules")
    return render(
        request,
        "ledger/apply_rule.html",
        {"rule": rule, "count": rule_edits.overwritable_matches(rule).count()},
    )


@require_POST
def delete_rule(request, pk):
    get_object_or_404(Rule, pk=pk).delete()
    return redirect("rules")


@require_POST
def move_rule(request, pk):
    rule_edits.move(get_object_or_404(Rule, pk=pk), request.POST.get("direction", ""))
    return redirect("rules")


@require_POST
def reorder_rules(request):
    """The order after a drag: every Rule's id, top first."""
    ids = request.POST.getlist("rule")
    if not all(pk.isdigit() for pk in ids):
        return HttpResponseBadRequest()
    rule_edits.reorder([int(pk) for pk in ids])
    return redirect("rules")
