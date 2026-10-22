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
from django.utils.formats import number_format
from django.utils.http import url_has_allowed_host_and_scheme, urlencode
from django.utils.translation import gettext as _
from django.utils.translation import ngettext
from django.views.decorators.http import require_http_methods, require_POST

from dashboard import periods, queries
from dashboard.views import VIEWS
from members.permissions import admin_required
from pursegraph import figures
from pursegraph.htmx import announce, wants_the_fragment_alone

from . import categories as category_edits
from . import facets, outcomes, review, suggestions
from . import rules as rule_edits
from .forms import (
    AccountAdminForm,
    AccountForm,
    CategoryForm,
    NameForm,
    OutcomeForm,
    RuleForm,
    StatementFileForm,
    ThresholdForm,
)
from .importer import (
    CheckedStatement,
    FileResult,
    ImportRejected,
    NewAccount,
    check_statement,
    commit_statement,
)
from .models import Account, Bank, Category, Rule, Statement, Subcategory, Transaction

TRANSACTIONS_PER_PAGE = 25


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
            _("Deleted the %(account)s Statement %(period)s.")
            % {
                "account": statement.account.name,
                "period": figures.date_range(statement.period_start, statement.period_end),
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


def transactions(request):
    """Every Transaction, narrowed by the facets and read 25 at a time (docs/design/transactions-page.md). A facet,
    the search or the pager swaps the results in (`#results`), with the rail, the summary and the breadcrumb out of
    band; the sidebar swaps the whole page into the main area."""
    choice = facets.Choice.from_query(request.GET)
    count, money_out, money_in = facets.totals(choice)
    rows = facets.rows(choice).select_related(
        "account", "subcategory__category", "rule", "counterpart__account"
    )
    paginator = Paginator(rows, TRANSACTIONS_PER_PAGE)
    page = paginator.get_page(request.GET.get("page"))
    groups = facets.rail(choice, facets.counts(choice), count)
    names = facets.named(choice, groups)
    query = choice.query()
    cleared = facets.Choice(dashboard=choice.dashboard).query()
    page_url = f"{request.path}?{query}&page=" if query else f"{request.path}?page="
    alone = wants_the_fragment_alone(request)
    in_place = alone and request.headers.get("HX-Target") == "results"
    title = str(_(" · ")).join([_("Transactions"), *names[:2]])
    response = render(
        request,
        "ledger/_transactions.html" if alone else "ledger/transactions.html",
        {
            "choice": choice,
            "groups": groups,
            "names": names,
            "count": count,
            "money_out": money_out,
            "money_in": money_in,
            "page": page,
            "page_range": list(
                paginator.get_elided_page_range(page.number, on_each_side=1, on_ends=1)
            ),
            "ellipsis": Paginator.ELLIPSIS,
            # A page's address is this plus its number.
            "page_url": page_url,
            # Clearing the filters keeps what the sidebar's links carry.
            "clear_url": f"{request.path}?{cleared}" if cleared else request.path,
            "crumb": _crumb(choice),
            # The Amount facet keeps the rest of the choice, and its Clear only its own.
            "amount_carry": choice.changed(direction="", least=None, most=None).params,
            "amount_clear_query": choice.query(direction="", least=None, most=None),
            "amount_least": "" if choice.least is None else number_format(choice.least),
            "amount_most": "" if choice.most is None else number_format(choice.most),
            **outcomes.picker(),
            "any_transactions": count or Transaction.objects.exists(),
            "page_title": title,
            "alone": alone,
            # Swapped in alone, the page also brings the sidebar, so that only Transactions is highlighted and the
            # dashboard views no longer swap into a view that has left the page.
            "swap_nav": alone and not in_place,
        },
    )
    if in_place:
        # The address names the choice the same way however it was picked.
        address = f"{request.path}?{query}" if query else request.path
        response["HX-Push-Url"] = address if page.number == 1 else f"{page_url}{page.number}"
        announce(response, _transactions_said(request, page, count))
    patch_vary_headers(response, ["HX-Request", "HX-History-Restore-Request"])
    return response


def _transactions_said(request, page, count: int) -> str:
    """What a swap of the results announces: the pager the page it went to, anything else the count."""
    pages = page.paginator.num_pages
    if request.headers.get("X-Pager"):
        return _("Page %(page)d of %(pages)d, %(first)d–%(last)d of %(count)d") % {
            "page": page.number,
            "pages": pages,
            "first": page.start_index(),
            "last": page.end_index(),
            "count": count,
        }
    said = ngettext("%(count)d Transaction", "%(count)d Transactions", count) % {"count": count}
    if pages > 1:
        said += _(" · page %(page)d of %(pages)d") % {"page": page.number, "pages": pages}
    return said


def _crumb(choice: facets.Choice) -> dict | None:
    """The breadcrumb back to the Dashboard view and chart mark the page was opened from: "Spending · Food ·
    September 2026", linking to the view with the period and filters it had."""
    if not (choice.view and choice.period):
        return None
    view = VIEWS[choice.view]
    heeded = queries.heeded(view.name, choice.filters)
    mark = queries.mark_label(view.name, choice.period, heeded, choice.mark)
    if mark is None:
        return None
    query = choice.dashboard or urlencode([("period", choice.period.token), *choice.filters.params])
    return {
        "label": str(_(" · ")).join([str(view.label), mark, choice.period.label]),
        "url": f"{reverse(view.name)}?{query}",
    }


REVIEW_DECIDED_SESSION_KEY = "review_decided"
REVIEW_UNDO_SESSION_KEY = "review_undo"


def review_queue(request):
    """The Review queue, a group open beside the list (docs/design/review-queue.md). `group` opens a group (on a
    phone, over the list), `at` only marks it, `back` returns to the list on a phone, and `resolved` shows the groups
    decided since arriving. Arriving, with none of them, starts a new review."""
    params = request.GET
    if not any(name in params for name in ("group", "at", "resolved", "back")):
        request.session[REVIEW_DECIDED_SESSION_KEY] = []
    opened = params.get("group", "")
    marked = opened or params.get("at", "")
    resolved = bool(params.get("resolved"))
    response = _review(
        request,
        selected=int(marked) if marked.isdigit() else None,
        opened=bool(opened),
        focus="heading" if opened else ("group" if "back" in params else ""),
        resolved=resolved,
    )
    # Show resolved, an in-place control, says what it changed.
    if request.headers.get("HX-Request") and "at" in params and "back" not in params:
        return announce(
            response,
            _("Resolved groups shown.") if resolved else _("Resolved groups hidden."),
        )
    return response


def _posted_pks(request) -> list[int] | None:
    pks = request.POST.getlist("transaction")
    if not pks or not all(pk.isdigit() for pk in pks):
        return None
    return sorted(int(pk) for pk in pks)


def _group_key(pks: list[int]) -> str:
    return ",".join(map(str, pks))


@require_POST
def review_decide(request):
    """Gives a group the outcome posted, as OutcomeForm takes it, all of it or none: the group's Transactions still in
    the Review queue; any decided since are left alone. Undo puts the whole group back."""
    pks = _posted_pks(request)
    if pks is None:
        return HttpResponseBadRequest()
    with db_transaction.atomic():
        waiting = Transaction.objects.select_for_update().filter(
            pk__in=Transaction.objects.in_review_queue().filter(pk__in=pks).values("pk")
        )
        forms = [OutcomeForm(request.POST, transaction=t) for t in waiting]
        if not all(form.is_valid() for form in forms):
            return HttpResponseBadRequest()
        before = []
        for form in forms:
            t = form.transaction
            before += outcomes.snapshot(
                t, t.counterpart, form.candidates.get(form.cleaned_data["outcome"])
            )
            form.save()
    decided = sorted(form.transaction.pk for form in forms)
    if decided:
        request.session[REVIEW_DECIDED_SESSION_KEY] = [
            *request.session.get(REVIEW_DECIDED_SESSION_KEY, []),
            decided,
        ]
        undo = request.session.get(REVIEW_UNDO_SESSION_KEY, {})
        undo[_group_key(decided)] = before
        request.session[REVIEW_UNDO_SESSION_KEY] = dict(list(undo.items())[-UNDO_KEPT:])
    group = review.group_of(decided or pks)
    if group is None:
        return HttpResponseBadRequest()
    if not decided:
        # Decided elsewhere meanwhile: nothing was saved, and the next waiting group opens.
        said = _("%(description)s was already decided.") % {"description": group.description}
        return _review_changed(request, group, focus="heading", said=said, select=False)
    said = ngettext(
        "Saved %(description)s as %(outcome)s.",
        "Saved %(count)d × %(description)s as %(outcome)s.",
        group.size,
    ) % {
        "count": group.size,
        "description": group.description,
        "outcome": group.newest.outcome_label,
    }
    return _review_changed(request, group, focus="next", said=said)


def _review_changed(request, group: review.Group, *, focus: str, said: str, select=True):
    """After a decision or its Undo: the group open again (a plain form post goes to it), and what changed said,
    with how many are left."""
    if not request.headers.get("HX-Request"):
        return redirect(f"{reverse('review_queue')}?group={group.key}")
    left = Transaction.objects.in_review_queue().count()
    return announce(
        _review(
            request,
            selected=group.key if select else None,
            opened=True,
            focus=focus,
            resolved=bool(request.POST.get("resolved")),
        ),
        f"{said} {_left_to_review(left)}",
    )


def _left_to_review(count: int) -> str:
    if not count:
        return _("Nothing left to review.")
    return ngettext("%(count)d left to review.", "%(count)d left to review.", count) % {
        "count": count
    }


@require_POST
def review_undo(request):
    """Puts back the outcomes a group's decision replaced, the whole group at once, and opens it again."""
    pks = _posted_pks(request)
    if pks is None:
        return HttpResponseBadRequest()
    key = _group_key(pks)
    before = request.session.get(REVIEW_UNDO_SESSION_KEY, {}).pop(key, None)
    request.session.modified = True
    if before is None:
        return HttpResponseBadRequest()
    try:
        outcomes.restore(before)
    except outcomes.UndoRefused:
        return HttpResponseBadRequest()
    request.session[REVIEW_DECIDED_SESSION_KEY] = [
        decided
        for decided in request.session.get(REVIEW_DECIDED_SESSION_KEY, [])
        if _group_key(decided) != key
    ]
    group = review.group_of(pks)
    if group is None:
        return HttpResponseBadRequest()
    said = _("Undone. %(description)s is back in the Review queue.") % {
        "description": group.description
    }
    return _review_changed(request, group, focus="heading", said=said)


def _review(request, *, selected: int | None, opened: bool, focus: str, resolved: bool):
    """The Review queue, whole or (for HTMX) its region alone, with the title and the sidebar's count."""
    waiting = review.waiting_groups()
    decided_pks = request.session.get(REVIEW_DECIDED_SESSION_KEY, [])
    decided = [
        group
        for pks in decided_pks
        if (group := review.group_of(pks)) is not None and not group.waiting
    ]
    # With nothing waiting, the end state shows, unless a group decided just now is opened.
    group = next(
        (g for g in [*waiting, *decided] if selected in g.pks and (waiting or opened)),
        waiting[0] if waiting else None,
    )
    count = sum(g.size for g in waiting)
    context = {
        "groups": review.sorted_groups([*waiting, *decided]) if resolved else waiting,
        "waiting_count": len(waiting),
        "decided_count": len(decided),
        "resolved": resolved,
        "group": group,
        # On a phone the detail shows instead of the list: a group opened, or the end state.
        "opened": opened or group is None,
        "focus": focus,
        "summary": _queue_summary(count, len(waiting)),
        "page_title": _("Review queue (%(count)d)") % {"count": count}
        if count
        else _("Review queue"),
        "next_group": waiting[0] if waiting else None,
        "listed": bool(waiting or decided),
    }
    if not waiting:
        context.update(_queue_clear([pk for pks in decided_pks for pk in pks], decided))
    if group is not None:
        context.update(_group_detail(group))
    alone = wants_the_fragment_alone(request)
    response = render(
        request,
        "ledger/_review.html" if alone else "ledger/review_queue.html",
        {**context, "swapped": alone},
    )
    patch_vary_headers(response, ["HX-Request", "HX-History-Restore-Request"])
    return response


def _queue_summary(count: int, groups: int) -> str:
    if not count:
        return _("Nothing left to review.")
    in_groups = ngettext("%(count)d group", "%(count)d groups", groups) % {"count": groups}
    return ngettext(
        "%(count)d Transaction in %(groups)s still needs an outcome",
        "%(count)d Transactions in %(groups)s still need an outcome",
        count,
    ) % {"count": count, "groups": in_groups}


def _group_detail(group: review.Group) -> dict:
    """What deciding `group` offers: what was used last time and the other outcomes, the suggested one left out."""
    last = review.last_time(group.description, exclude=group.pks)
    suggested = str(group.suggestion.pk) if group.suggestion else None
    used_last = last if last and last.outcome != suggested else None
    left_out = {suggested, used_last.outcome if used_last else None}
    picker = outcomes.picker()
    return {
        "last": last,
        "used_last": used_last,
        "categories": picker["categories"],
        "most_used": [s for s in picker["most_used"] if str(s.pk) not in left_out],
        "candidates": group.newest.pairing_candidates() if group.ambiguous else [],
    }


def _queue_clear(decided_pks: list[int], decided: list[review.Group]) -> dict:
    """The end state's words and links: how many were decided just now, and the newest month that made Complete."""
    completed = review.completed_month(decided_pks) if decided_pks else None
    current = periods.today().replace(day=1)
    return {
        "decided_now": sum(g.size for g in decided),
        "completed_month": completed,
        "current_month": current,
    }


UNDO_SESSION_KEY = "outcome_undo"
# Undo is offered for 10 s; a few saves' worth is plenty to keep.
UNDO_KEPT = 20


@require_POST
def transaction_outcome(request, pk):
    """Sets a Transaction's outcome by hand. HTMX gets the updated row back, saying it saved and offering Undo; a
    plain form post goes back to `next`."""
    transaction = get_object_or_404(
        Transaction.objects.select_related("account", "subcategory__category", "counterpart"), pk=pk
    )
    form = OutcomeForm(request.POST, transaction=transaction)
    if not form.is_valid():
        return HttpResponseBadRequest(form.errors.as_text())
    before = outcomes.snapshot(
        transaction, transaction.counterpart, form.candidates.get(form.cleaned_data["outcome"])
    )
    form.save()
    undo = request.session.get(UNDO_SESSION_KEY, {})
    undo.pop(str(pk), None)
    undo[str(pk)] = before
    request.session[UNDO_SESSION_KEY] = dict(list(undo.items())[-UNDO_KEPT:])
    if request.headers.get("HX-Request"):
        transaction.refresh_from_db()
        return announce(
            _transaction_row(request, transaction, saved=True),
            _("Saved %(description)s as %(outcome)s.")
            % {"description": transaction.description, "outcome": transaction.outcome_label},
        )
    next_url = request.POST.get("next", "")
    if not url_has_allowed_host_and_scheme(next_url, allowed_hosts={request.get_host()}):
        next_url = "transactions"
    return redirect(next_url)


@require_POST
def undo_outcome(request, pk):
    """Puts back the outcome the last save of this Transaction replaced, with its source, and returns the row."""
    transaction = get_object_or_404(Transaction, pk=pk)
    before = request.session.get(UNDO_SESSION_KEY, {}).pop(str(pk), None)
    request.session.modified = True
    if before is None:
        return HttpResponseBadRequest()
    try:
        outcomes.restore(before)
    except outcomes.UndoRefused:
        return HttpResponseBadRequest()
    transaction.refresh_from_db()
    return announce(
        _transaction_row(request, transaction),
        _("Undone. %(description)s is back to %(outcome)s.")
        % {"description": transaction.description, "outcome": transaction.outcome_label},
    )


def _transaction_row(request, transaction, *, saved=False):
    """The shared Transaction row, swapped in for a Transaction just changed."""
    return render(
        request,
        "ledger/_transaction_row.html",
        {"t": transaction, **outcomes.picker(), "saved": saved, "refresh_review_queue_count": True},
    )


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
        count, pairing = rule_edits.apply_to_existing(rule)
        sentences = [
            ngettext(
                "%(count)d Transaction categorized by the Rule.",
                "%(count)d Transactions categorized by the Rule.",
                count,
            )
            % {"count": count}
        ]
        if pairing.converted_count:
            sentences.append(
                ngettext(
                    "%(count)d categorized Transaction converted to a Transfer.",
                    "%(count)d categorized Transactions converted to Transfers.",
                    pairing.converted_count,
                )
                % {"count": pairing.converted_count}
            )
        if pairing.ambiguous_count:
            sentences.append(
                ngettext(
                    "%(count)d Transfer with several possible counterparts waits in the Review queue.",
                    "%(count)d Transfers with several possible counterparts wait in the Review queue.",
                    pairing.ambiguous_count,
                )
                % {"count": pairing.ambiguous_count}
            )
        messages.success(request, " ".join(sentences))
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
