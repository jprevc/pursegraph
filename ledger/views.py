import base64
import json
from dataclasses import dataclass
from decimal import Decimal
from functools import wraps
from typing import NamedTuple
from urllib.parse import urlsplit

from django.contrib import messages
from django.contrib.auth import get_user_model
from django.contrib.humanize.templatetags.humanize import ordinal
from django.core.exceptions import PermissionDenied
from django.core.paginator import Paginator
from django.db import IntegrityError
from django.db import transaction as db_transaction
from django.db.models import Count, Prefetch, Q, QuerySet
from django.http import HttpResponse, HttpResponseBadRequest, QueryDict
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import Resolver404, resolve, reverse
from django.utils import timezone
from django.utils.cache import patch_vary_headers
from django.utils.formats import date_format, number_format
from django.utils.http import url_has_allowed_host_and_scheme, urlencode
from django.utils.translation import gettext as _
from django.utils.translation import ngettext
from django.views.decorators.http import require_http_methods, require_POST

from dashboard import periods, queries
from dashboard.views import VIEWS, drill_rows
from dashboard.views import transactions as drill_down
from members.permissions import admin_required
from pursegraph import figures
from pursegraph.htmx import announce, wants_the_fragment_alone

from . import api_tokens, facets, outcomes, review, suggestions, webhooks
from . import categories as category_edits
from . import rules as rule_edits
from .board import Axis, track
from .coverage import DateRange, coverage, removing
from .forms import (
    AccountAdminForm,
    AccountForm,
    ApiTokenForm,
    CategoryForm,
    NameForm,
    OutcomeForm,
    RuleForm,
    StatementFileForm,
    ThresholdForm,
    WebhookForm,
    split_parts,
)
from .import_results import banner, domain_counts
from .importer import (
    CheckedStatement,
    FileResult,
    ImportRejected,
    NewAccount,
    check_statement,
    commit_statement,
)
from .models import (
    Account,
    Bank,
    Category,
    Rule,
    Source,
    Statement,
    Subcategory,
    Transaction,
    Webhook,
)

TRANSACTIONS_PER_PAGE = 25

# What a Transaction row shows of each Transaction's relations.
_ROW_RELATED = ("account", "subcategory__category", "rule", "counterpart__account")


def import_statements(request):
    """Upload Statements, several at once, each accepted or rejected on its own (docs/design/import.md).

    Every file is checked first; the rest are then imported in period order, so each one's
    Duplicate check sees the Coverage the earlier ones left. A file goes into the Account its
    IBAN identifies; otherwise a second step asks for the Account, carrying the file along.
    Posting `account` with the files skips straight to that step's answer, for every file that
    needs one; a new Account it names is created by the first such file, and later files of that
    bank go into it.

    The result is told by a banner, a tray of the files that need the Member, and on the board, where each
    Account's row shows the stretch this import added. HTMX posts swap the `#import` region in.
    """
    form = StatementFileForm()
    results: list[FileResult] = []
    pending: list[dict] = []
    before: dict[int, list[DateRange]] | None = None
    if request.method == "POST":
        posted = StatementFileForm(request.POST, request.FILES)
        if not posted.is_valid():
            form = posted
        else:
            before = {
                account.pk: account.coverage()
                for account in Account.objects.prefetch_related("statements")
            }
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
                        initial={"owners": [request.user.pk]},
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

    said = banner(results, needs_account=len(pending)) if before is not None else None
    rejected = [r for r in results if r.rejection and not r.rejection.already_imported]
    response = render(
        request,
        "ledger/_import.html" if wants_the_fragment_alone(request) else "ledger/import.html",
        {
            "form": form,
            "banner": said,
            "pending": pending,
            "rejected": rejected,
            "already": [r for r in results if r.rejection and r.rejection.already_imported],
            "tray_count": len(pending) + len(rejected),
            **_board(before, [r.summary for r in results if r.summary]),
            "board_page": "import",
            "page_title": _("Import"),
            "alone": wants_the_fragment_alone(request),
        },
    )
    if said:
        announce(
            response,
            _("%(headline)s. %(rest)s") % {"headline": said.headline, "rest": said.rest}
            if said.rest
            else said.headline,
        )
    elif form.errors:
        # Nothing was posted to import; the strip says why.
        announce(
            response, " ".join(str(error) for errors in form.errors.values() for error in errors)
        )
    patch_vary_headers(response, ["HX-Request"])
    return response


def _board(before: dict[int, list[DateRange]] | None, summaries: list) -> dict:
    """The Accounts board: each Account's track on one axis from the Household's first covered day to today, with
    what this import added (when `before` holds the Coverage it started from) and its Statements."""
    statements = (
        Statement.objects.select_related("imported_by")
        .annotate(transaction_count=Count("transactions"))
        .order_by("-period_start", "-id")
    )
    accounts = list(
        Account.objects.prefetch_related(
            Prefetch("owners", queryset=get_user_model().objects.order_by("username")),
            Prefetch("statements", queryset=statements),
        )
    )
    ranges = {account.pk: coverage(account.statements.all()) for account in accounts}
    today = timezone.localdate()
    starts = [r[0].start for r in ranges.values() if r]
    axis = Axis(min(starts), today) if starts else None
    rows = []
    for account in accounts:
        covered = ranges[account.pk]
        stretches = (
            track(
                axis,
                covered,
                before=covered if before is None else before.get(account.pk, []),
            )
            if axis and covered
            else []
        )
        rows.append(
            {
                "account": account,
                "statements": account.statements.all(),
                "stretches": stretches,
                "gaps": [s for s in stretches if s.is_gap],
                "tracked_from": covered[0].start if covered else None,
                "results": [
                    {"summary": s, "counts": domain_counts(s)}
                    for s in summaries
                    if s.account.pk == account.pk
                ],
            }
        )
    return {"axis": axis, "ticks": axis.ticks() if axis else [], "rows": rows}


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
    """The Accounts board (docs/design/import.md), where admins edit each Account in place. `closed` names the
    Account whose edit was just cancelled, so that its Edit takes the focus back."""
    return _accounts_page(request, focus=_pk_or_none(request.GET.get("closed")))


@admin_required
def new_account(request):
    return _account_form(request, Account())


@admin_required
def edit_account(request, pk):
    return _account_form(request, get_object_or_404(Account, pk=pk))


def _account_form(request, account):
    """An Account's row opened on the board with its form; a save closes it, saying "Saved" beside its name."""
    if request.method != "POST":
        form = AccountAdminForm(instance=account)
        form.fields["name"].widget.attrs["data-focus"] = ""
        return _accounts_page(request, form=form)
    try:
        with db_transaction.atomic():
            if account.pk:
                # Serialized with imports into the Account, so it keeps its bank once one lands.
                account = Account.objects.select_for_update().get(pk=account.pk)
            form = AccountAdminForm(request.POST, instance=account)
            if form.is_valid():
                saved = form.save()
                said = _("Saved %(account)s.") % {"account": saved.name}
                if not wants_the_fragment_alone(request):
                    messages.success(request, said)
                    return redirect("accounts")
                return announce(_accounts_page(request, saved=saved.pk, focus=saved.pk), said)
    except IntegrityError:
        # Another admin gave one of the IBANs to an Account in the meantime.
        form.add_error("ibans", _("One of these IBANs was just added to another Account."))
    # The first field to fix takes the focus.
    form.fields[next(iter(form.errors))].widget.attrs["data-focus"] = ""
    return announce(
        _accounts_page(request, form=form),
        " ".join(str(error) for errors in form.errors.values() for error in errors),
    )


def _accounts_page(request, *, form=None, saved=None, focus=None):
    """The Accounts page, or its board alone for HTMX: with `form`'s Account open (a new one last), the Account
    `saved` just now, and the Account whose Edit takes the `focus`."""
    context = {
        "account_form": form,
        "editing": (form.instance.pk or "new") if form else None,
        "saved": saved,
        "focus": focus,
    }
    if wants_the_fragment_alone(request):
        return _board_alone(request, "accounts", **context)
    response = render(
        request,
        "ledger/accounts.html",
        {**_board(None, []), "board_page": "accounts", "page_title": _("Accounts"), **context},
    )
    patch_vary_headers(response, ["HX-Request"])
    return response


def _board_alone(request, page: str, **context):
    """The board of `page`, Import or Accounts, swapped in alone with its page's title."""
    response = render(
        request,
        "ledger/_board.html",
        {
            **_board(None, []),
            "board_page": page,
            "page_title": _("Accounts") if page == "accounts" else _("Import"),
            "alone": True,
            **context,
        },
    )
    patch_vary_headers(response, ["HX-Request"])
    return response


def _ranges_said(ranges: list[DateRange]) -> str:
    return ", ".join(figures.date_range(r.start, r.end) for r in ranges)


def _pk_or_none(value: str | None) -> int | None:
    return int(value) if value and value.isdigit() else None


@admin_required
@require_http_methods(["GET", "POST"])
def delete_account(request, pk):
    """Deletes an Account after an inline confirmation, with the Rules only for it; refused while it has
    Statements, whose Transactions would go with it."""
    if request.method == "GET":
        account = get_object_or_404(Account, pk=pk)
        return render(
            request,
            "ledger/_confirm_delete_account.html"
            if wants_the_fragment_alone(request)
            else "ledger/delete_account.html",
            {
                "account": account,
                "statement_count": account.statements.count(),
                "rule_count": account.rules.count(),
                "alone": wants_the_fragment_alone(request),
            },
        )
    with db_transaction.atomic():
        # Serialized with imports into the Account.
        account = get_object_or_404(Account.objects.select_for_update(), pk=pk)
        refused = account.statements.exists()
        if refused:
            said = _(
                "%(account)s has Statements, so it can't be deleted. Delete its Statements first."
            ) % {"account": account.name}
        else:
            account.delete()
            said = _("Deleted %(account)s.") % {"account": account.name}
    if wants_the_fragment_alone(request):
        return announce(_accounts_page(request), said)
    (messages.error if refused else messages.success)(request, said)
    return redirect("accounts")


@require_http_methods(["GET", "POST"])
def delete_statement(request, pk):
    """Deletes a Statement after an inline confirmation; only its importer or an admin may. `board` names the
    page whose board asked, Import or Accounts, which is shown again."""
    statement = get_object_or_404(Statement.objects.select_related("account"), pk=pk)
    if not statement.can_be_deleted_by(request.user):
        raise PermissionDenied
    board = request.POST.get("board") or request.GET.get("board")
    on_accounts = board == "accounts" and request.user.is_admin
    if request.method == "POST":
        statement.delete_with_transactions()
        said = _("Deleted the %(account)s Statement %(period)s.") % {
            "account": statement.account.name,
            "period": figures.date_range(statement.period_start, statement.period_end),
        }
        if not wants_the_fragment_alone(request):
            messages.success(request, said)
            return redirect("accounts" if on_accounts else "import")
        return announce(
            _accounts_page(request) if on_accounts else _board_alone(request, "import"), said
        )
    others = coverage(statement.account.statements.exclude(pk=statement.pk))
    shrink = removing(
        DateRange(statement.period_start, statement.period_end), others, until=timezone.localdate()
    )
    return render(
        request,
        "ledger/_confirm_delete_statement.html"
        if wants_the_fragment_alone(request)
        else "ledger/delete_statement.html",
        {
            "statement": statement,
            "board": "accounts" if on_accounts else "import",
            "transaction_count": statement.own_transactions().count(),
            "manual_outcome_count": statement.lost_manual_outcome_count(),
            "shrink": shrink,
            "gaps_said": _ranges_said(shrink.gaps),
            "untracked_said": _ranges_said(shrink.untracked),
            "alone": wants_the_fragment_alone(request),
        },
    )


def transactions(request):
    """Every Transaction, narrowed by the facets and read 25 at a time (docs/design/transactions-page.md). A facet,
    the search or the pager swaps the results in (`#results`), with the rail, the summary and the breadcrumb out of
    band; the sidebar swaps the whole page into the main area."""
    choice = facets.Choice.from_query(request.GET)
    count, money_out, money_in = facets.totals(choice)
    rows = facets.rows(choice).select_related(*_ROW_RELATED)
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
    return _review_decided(request, pks, sorted(form.transaction.pk for form in forms), before)


@require_POST
def review_split(request):
    """Splits a group into the Parts posted, as `ledger.forms.split_parts` reads them: the Subcategories once, an
    amount of each for every Transaction still in the Review queue. All of them or none; Undo puts the whole group
    back. A refusal is a 400 whose text names the first Transaction it was about."""
    pks = _posted_pks(request)
    if pks is None:
        return HttpResponseBadRequest()
    before: list[dict] = []
    try:
        with db_transaction.atomic():
            waiting = Transaction.objects.select_for_update().filter(
                pk__in=Transaction.objects.in_review_queue().filter(pk__in=pks).values("pk")
            )
            for t in waiting:
                try:
                    before += outcomes.split(t, split_parts(request.POST, t))
                except outcomes.SplitRefused as refused:
                    if len(pks) == 1:
                        raise
                    raise outcomes.SplitRefused(
                        f"{figures.day(t.date)} · {figures.money(abs(t.amount))}: {refused}"
                    ) from refused
    except outcomes.SplitRefused as refused:
        return HttpResponseBadRequest(str(refused), content_type="text/plain; charset=utf-8")
    decided = sorted(s["pk"] for s in before if s["pk"] in pks)
    return _review_decided(request, pks, decided, before)


def _review_decided(request, pks: list[int], decided: list[int], before: list[dict]):
    """After the group `pks` was decided, `decided` those still waiting: kept for Undo and for Show resolved, and the
    group open again with what was saved said."""
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
        "outcome": group.newest.outcome_saved,
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
        # What the Split editor (static/split.js) opens with: the Transactions still waiting, Part 1 the Suggestion.
        "split_group": {
            "url": reverse("review_split"),
            "description": group.description,
            "first": group.suggestion.pk if group.suggestion else None,
            "rows": [
                {
                    "pk": t.pk,
                    "amount": str(t.amount),
                    "date": figures.day(t.date),
                    "account": t.account.name,
                }
                for t in group.transactions
                if t.is_unresolved or t.ambiguous_pairing
            ],
        },
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
        row, transaction = _transaction_row(request, pk, saved=True)
        return announce(
            row,
            _("Saved %(description)s as %(outcome)s.")
            % {"description": transaction.description, "outcome": transaction.outcome_saved},
        )
    next_url = request.POST.get("next", "")
    if not url_has_allowed_host_and_scheme(next_url, allowed_hosts={request.get_host()}):
        next_url = "transactions"
    return redirect(next_url)


@require_POST
def transaction_split(request, pk):
    """Splits a Transaction into the Parts posted (`ledger.forms.split_parts`), by hand. HTMX gets the row back with
    its Part rows, saying it saved and offering Undo; a refusal is a 400 whose text says why, for the editor to show."""
    transaction = get_object_or_404(Transaction, pk=pk)
    try:
        before = outcomes.split(transaction, split_parts(request.POST, transaction))
    except outcomes.SplitRefused as refused:
        return HttpResponseBadRequest(str(refused), content_type="text/plain; charset=utf-8")
    undo = request.session.get(UNDO_SESSION_KEY, {})
    undo.pop(str(pk), None)
    undo[str(pk)] = before
    request.session[UNDO_SESSION_KEY] = dict(list(undo.items())[-UNDO_KEPT:])
    if not request.headers.get("HX-Request"):
        return redirect("transactions")
    row, transaction = _transaction_row(request, pk, saved=True)
    return announce(
        row,
        _("Saved %(description)s as %(outcome)s.")
        % {"description": transaction.description, "outcome": transaction.outcome_saved},
    )


class _List(NamedTuple):
    """A list of Transaction rows: its Transactions as its rows show them, and whether it is a drill-down."""

    rows: QuerySet[Transaction]
    drill: bool


def _list_at(listed: str) -> _List | None:
    """The list at the address `listed`, the Transactions page or a drill-down; None for any other address."""
    address = urlsplit(listed)
    try:
        match = resolve(address.path)
    except Resolver404:
        return None
    query = QueryDict(address.query)
    if match.func is transactions:
        return _List(
            facets.rows(facets.Choice.from_query(query)).select_related(*_ROW_RELATED), False
        )
    if match.func is drill_down:
        return _List(drill_rows(match.kwargs["view"], query).select_related(*_ROW_RELATED), True)
    return None


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
    row, transaction = _transaction_row(request, pk)
    return announce(
        row,
        _("Undone. %(description)s is back to %(outcome)s.")
        % {"description": transaction.description, "outcome": transaction.outcome_label},
    )


def _transaction_row(request, pk: int, *, saved=False) -> tuple[HttpResponse, Transaction]:
    """The shared Transaction row, swapped in for a Transaction just changed, and that Transaction. It reads as a load
    of the list it is shown in (the posted `listed`, that list's address) shows it, with what it counts there, while
    it is in that list; else with every Part counted."""
    listed = request.POST.get("listed", "")
    shown_in = _list_at(listed)
    transaction = shown_in.rows.filter(pk=pk).first() if shown_in else None
    if transaction is None:
        transaction = Transaction.objects.with_counted().select_related(*_ROW_RELATED).get(pk=pk)
    row = render(
        request,
        "ledger/_transaction_row.html",
        {
            "t": transaction,
            **outcomes.picker(),
            "saved": saved,
            "listed": listed,
            "drill": bool(shown_in and shown_in.drill),
            "refresh_review_queue_count": True,
        },
    )
    return row, transaction


@admin_required
def categories(request):
    """The Categories page (docs/design/admin.md): read-only cards; `edit=<pk>` opens one Category for editing and
    `new` the New Category form. Asked for by HTMX, the grid alone; `closed=<pk>` names the card just closed."""
    return _categories_page(
        request,
        editing=_pk_or_none(request.GET.get("edit")),
        new="new" in request.GET,
        focus=_pk_or_none(request.GET.get("closed")),
    )


def _categories_page(
    request, *, editing=None, new=False, confirm=None, drafts=None, error="", focus=None, moved=None
):
    """The Categories page, or its grid alone for HTMX: the `editing` Category opened with the names typed so far
    (`drafts`, as posted), a delete `confirm`ed inline (a Subcategory's id, or "category"), the `error` of the last
    step, and `focus` naming what takes focus after a swap; `moved` is a (Subcategory id, direction) just moved."""
    context = {
        "categories": _categories(editing, drafts or {}, moved),
        "editing": editing,
        "new": new and not editing,
        "confirm": confirm,
        "error": error,
        "focus": focus,
        "kinds": Category.Kind.choices,
        "page_title": _("Categories"),
    }
    if wants_the_fragment_alone(request):
        response = render(request, "ledger/_categories.html", {**context, "alone": True})
    else:
        response = render(request, "ledger/categories.html", context)
    patch_vary_headers(response, ["HX-Request", "HX-History-Restore-Request"])
    return response


def _categories(editing: int | None, drafts, moved: tuple[int, str] | None) -> list[Category]:
    """The Categories with their counts, each with its `place` and `catch_all`; the `editing` one also with its
    names as typed (`draft`), why it can't be deleted (`refusal`), and which Move button keeps the focus."""
    categories = category_edits.with_counts()
    for place, category in enumerate(categories, 1):
        subcategories = list(category.subcategories.all())
        category.place = place  # type: ignore[attr-defined]
        category.catch_all = subcategories[-1]  # type: ignore[attr-defined]
        if category.pk != editing:
            continue
        category.save_form = f"save-{category.pk}"  # type: ignore[attr-defined]
        category.draft = drafts.get("name", category.name)  # type: ignore[attr-defined]
        category.refusal = category_edits.deletion_refused(category)  # type: ignore[attr-defined]
        movable = [s for s in subcategories if not s.is_catch_all]
        for s in subcategories:
            s.draft = drafts.get(f"sub-{s.pk}", s.name)  # type: ignore[attr-defined]
        if moved:
            at = next((i for i, s in enumerate(movable) if s.pk == moved[0]), None)
            if at is not None:
                movable[at].focus = _focused_move(moved[1], at + 1, len(movable))  # type: ignore[attr-defined]
    return categories


@dataclass(frozen=True)
class _CategoryStep:
    """What a step of editing the Categories leads to: the Category still `editing`, if any (else the `new` form,
    or none), what happened in words (`said`) or why it didn't (`error`), and what takes the focus."""

    editing: int | None = None
    new: bool = False
    said: str = ""
    error: str = ""
    focus: object = None
    moved: tuple[int, str] | None = None


def _category_step(view):
    """An admin-only POST that edits the Categories and returns a _CategoryStep: with HTMX, the grid swapped in as
    the step left it, the names typed so far kept and the step announced; without, the page again by redirect."""

    @admin_required
    @require_POST
    @wraps(view)
    def wrapper(request, *args, **kwargs):
        step = view(request, *args, **kwargs)
        if not wants_the_fragment_alone(request):
            if step.error:
                messages.error(request, step.error)
            query = f"?edit={step.editing}" if step.editing else "?new" if step.new else ""
            return redirect(reverse("categories") + query)
        response = _categories_page(
            request,
            editing=step.editing,
            new=step.new,
            drafts=request.POST,
            error=step.error,
            focus=step.focus,
            moved=step.moved,
        )
        said = step.error or step.said
        return announce(response, said) if said else response

    return wrapper


def _form_error(form) -> str:
    return " ".join(str(error) for errors in form.errors.values() for error in errors)


@_category_step
def add_category(request):
    form = CategoryForm(request.POST)
    if not form.is_valid():
        return _CategoryStep(new=True, error=_form_error(form))
    category = category_edits.add_category(
        form.cleaned_data["name"].strip(), form.cleaned_data["kind"]
    )
    return _CategoryStep(said=_("Added %(name)s.") % {"name": category.name}, focus=category.pk)


@_category_step
def save_category(request, pk):
    """Saves the names of a Category and its Subcategories (`name`, and `sub-<id>` for each), then closes it."""
    category = get_object_or_404(Category, pk=pk)
    names: dict[str, Category | Subcategory] = {"name": category}
    names |= {f"sub-{s.pk}": s for s in category.subcategories.all()}
    forms = {
        key: NameForm({"name": request.POST.get(key, item.name)}) for key, item in names.items()
    }
    if errors := [_form_error(form) for form in forms.values() if not form.is_valid()]:
        return _CategoryStep(editing=pk, error=errors[0])
    with db_transaction.atomic():
        for key, item in names.items():
            category_edits.rename(item, forms[key].cleaned_data["name"].strip())
    return _CategoryStep(said=_("Saved %(name)s.") % {"name": category.name}, focus=pk)


@_category_step
def move_category(request, pk):
    category = get_object_or_404(Category, pk=pk)
    direction = request.POST.get("direction", "")
    category_edits.move_category(category, direction)
    order = list(Category.objects.values_list("pk", flat=True))
    place = order.index(pk) + 1
    return _CategoryStep(
        editing=pk,
        said=_("Moved %(name)s to %(place)s.") % {"name": category.name, "place": ordinal(place)},
        focus="category-" + _focused_move(direction, place, len(order)),
    )


def _focused_move(direction: str, place: int, last: int) -> str:
    """Which Move button keeps the focus after a move `direction` to `place` of `last`: the one used, unless the
    move reached the end and disabled it, then the other one."""
    at_end = place == 1 if direction == "up" else place == last
    if not at_end:
        return direction
    return "down" if direction == "up" else "up"


@admin_required
@require_http_methods(["GET", "POST"])
def delete_category(request, pk):
    """Deletes a Category nothing uses, after an inline confirmation."""
    category = get_object_or_404(Category, pk=pk)
    if request.method == "GET":
        return _confirm_category_delete(request, category.pk, "category")
    return _delete_category(request, category)


@_category_step
def _delete_category(request, category):
    try:
        category_edits.delete_category(category)
    except category_edits.CategoryEditRefused as refusal:
        return _CategoryStep(editing=category.pk, error=str(refusal))
    return _CategoryStep(said=_("Deleted %(name)s.") % {"name": category.name})


@_category_step
def add_subcategory(request, pk):
    category = get_object_or_404(Category, pk=pk)
    form = NameForm(request.POST, prefix="new")
    if not form.is_valid():
        return _CategoryStep(editing=pk, error=_form_error(form), focus="add")
    subcategory = category_edits.add_subcategory(category, form.cleaned_data["name"].strip())
    return _CategoryStep(
        editing=pk,
        said=_("Added %(name)s to %(category)s.")
        % {"name": subcategory.name, "category": category.name},
        focus="add",
    )


@_category_step
def move_subcategory(request, pk):
    subcategory = get_object_or_404(Subcategory, pk=pk)
    direction = request.POST.get("direction", "")
    category_edits.move_subcategory(subcategory, direction)
    said = (_("Moved %(name)s up.") if direction == "up" else _("Moved %(name)s down.")) % {
        "name": subcategory.name
    }
    return _CategoryStep(editing=subcategory.category_id, said=said, moved=(pk, direction))


@admin_required
@require_http_methods(["GET", "POST"])
def delete_subcategory(request, pk):
    """Deletes a Subcategory after an inline confirmation, moving what uses it to its Category's catch-all."""
    subcategory = get_object_or_404(Subcategory, pk=pk)
    if request.method == "GET":
        return _confirm_category_delete(request, subcategory.category_id, subcategory.pk)
    return _delete_subcategory(request, subcategory)


@_category_step
def _delete_subcategory(request, subcategory):
    category = subcategory.category
    try:
        catch_all = category_edits.delete_subcategory(subcategory)
    except category_edits.CategoryEditRefused as refusal:
        return _CategoryStep(editing=category.pk, error=str(refusal))
    return _CategoryStep(
        editing=category.pk,
        said=_(
            "Deleted %(category)s › %(name)s; what used it moved to %(category)s › %(catch_all)s."
        )
        % {"category": category.name, "name": subcategory.name, "catch_all": catch_all.name},
        focus="heading",
    )


def _confirm_category_delete(request, editing: int, confirm):
    """The inline confirmation of deleting the `editing` Category (`confirm` "category") or one of its
    Subcategories (its id): alone for HTMX, else the page with that Category open and the confirmation in it."""
    if not wants_the_fragment_alone(request):
        return _categories_page(request, editing=editing, confirm=confirm)
    category = next(c for c in _categories(editing, {}, None) if c.pk == editing)
    if confirm == "category":
        return render(request, "ledger/_confirm_delete_category.html", {"category": category})
    subcategory = next(s for s in category.subcategories.all() if s.pk == confirm)
    subcategory.category = category  # with its catch_all
    return render(request, "ledger/_confirm_delete_subcategory.html", {"subcategory": subcategory})


@admin_required
@require_http_methods(["GET", "POST"])
def suggestion_settings(request):
    """The Suggestions page (docs/design/admin.md): what waits and what last arrived, how sure the queued
    suggestions are with the auto-accept threshold, and Ask again. Right after lowering the threshold (`?lowered`),
    it offers the queued suggestions that now clear it."""
    current = _threshold_percent()
    form = ThresholdForm(request.POST or None, initial={"threshold": current})
    if form.is_valid():
        percent = form.cleaned_data["threshold"]
        suggestions.set_threshold((Decimal(percent) / 100).quantize(Decimal("0.01")))
        return redirect(reverse("suggestion_settings") + ("?lowered" if percent < current else ""))
    return _suggestions_page(request, form=form, lowered="lowered" in request.GET)


def _suggestions_page(request, *, form=None, lowered=False, confirm=False):
    threshold = _threshold_percent()
    overview = suggestions.overview()
    offered = (
        list(suggestions.suggestions_clearing_threshold().values_list("pk", flat=True))
        if lowered
        else []
    )
    bins = [
        {"start": i * suggestions.BIN_WIDTH, "end": (i + 1) * suggestions.BIN_WIDTH, "count": n}
        for i, n in enumerate(overview.bins)
    ]
    tallest = max(3, *overview.bins)
    for b in bins:
        b["height"] = round(b["count"] / tallest * 100)
        b["over"] = b["start"] >= threshold
    chart_said = ngettext(
        "How sure the %(count)d queued suggestion is",
        "How sure the %(count)d queued suggestions are",
        overview.with_suggestion,
    ) % {"count": overview.with_suggestion}
    filled = ", ".join(_("%(start)d to %(end)d %%: %(count)d") % b for b in bins if b["count"])
    return render(
        request,
        "ledger/suggestion_settings.html",
        {
            "form": form or ThresholdForm(initial={"threshold": threshold}),
            "threshold": threshold,
            "offered": offered,
            "waiting_since": _when(overview.waiting_since),
            "last_suggestion_at": _when(
                overview.last_suggestion.last_suggestion_at if overview.last_suggestion else None
            ),
            "overview": overview,
            "bins": bins,
            "ticks": range(0, 101, 10),
            "chart_label": f"{chart_said}: {filled}" if filled else chart_said,
            "clearing": json.dumps(overview.clearing),
            "confirm": confirm,
        },
    )


def _threshold_percent() -> int:
    """The auto-accept threshold in % sure, as the Suggestions page shows and takes it."""
    return round(suggestions.threshold() * 100)


def _when(moment) -> str:
    """A moment as the status strip says it: the time today, else the date and time; "" for None."""
    if moment is None:
        return ""
    local = timezone.localtime(moment)
    if local.date() == timezone.localdate():
        return date_format(local, "H:i")
    return date_format(local, "j M Y H:i")


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
@require_http_methods(["GET", "POST"])
def resuggest_queue(request):
    """Ask again: clears the queued suggestions after an inline confirmation, so the Categorizers are asked about them again.
    When it can't run (`Overview.ask_again_refusal`), it confirms and clears nothing: the page says why, so a
    request for the confirmation alone gets an empty one and leaves the confirmation slot empty."""
    overview = suggestions.overview()
    if overview.ask_again_refusal:
        if wants_the_fragment_alone(request):
            return HttpResponse("")
        return redirect("suggestion_settings")
    if request.method == "GET":
        if wants_the_fragment_alone(request):
            return render(
                request, "ledger/_confirm_resuggest.html", {"count": overview.askable_again}
            )
        return _suggestions_page(request, confirm=True)
    count = suggestions.resuggest_queue()
    messages.success(
        request,
        ngettext(
            "%(count)d suggestion cleared; the Categorizers will be asked again.",
            "%(count)d suggestions cleared; the Categorizers will be asked again.",
            count,
        )
        % {"count": count},
    )
    return redirect("suggestion_settings")


@admin_required
@require_http_methods(["GET", "POST"])
def api_and_webhooks(request):
    """The API & Webhooks page (docs/design/admin.md): the API tokens programs outside Pursegraph connect with.
    Creating one redirects, so a refresh doesn't create another, and the page after it shows the secret once, in a
    dialog over the page."""
    form = ApiTokenForm(request.POST or None)
    if form.is_valid():
        token, secret = api_tokens.create(form.cleaned_data["name"], request.user)
        request.session[_NEW_TOKEN] = [token.name, secret]
        return redirect("api_and_webhooks")
    return _api_and_webhooks_page(request, form=form, created=request.session.pop(_NEW_TOKEN, None))


# The session key holding a new token's name and secret until the page after creating it shows them.
_NEW_TOKEN = "new_api_token"


def _api_and_webhooks_page(
    request, *, form=None, webhook_form=None, created=None, confirm=None, confirm_webhook=None
):
    response = render(
        request,
        "ledger/api_and_webhooks.html",
        {
            "form": form or ApiTokenForm(),
            "webhook_form": webhook_form or WebhookForm(),
            "tokens": api_tokens.active().select_related("created_by"),
            "webhooks": Webhook.objects.all(),
            "created": created,
            "confirm": confirm,
            "confirm_webhook": confirm_webhook,
        },
    )
    patch_vary_headers(response, ["HX-Request", "HX-History-Restore-Request"])
    return response


@admin_required
@require_http_methods(["GET", "POST"])
def revoke_token(request, pk):
    """Revoke, confirmed inline under the token's row."""
    token = get_object_or_404(api_tokens.active(), pk=pk)
    if request.method == "GET":
        if wants_the_fragment_alone(request):
            return render(request, "ledger/_confirm_revoke.html", {"token": token})
        return _api_and_webhooks_page(request, confirm=token.pk)
    api_tokens.revoke(token.pk)
    messages.success(
        request,
        _("“%(name)s” is revoked: what uses it can't connect any more.") % {"name": token.name},
    )
    return redirect("api_and_webhooks")


@admin_required
@require_POST
def add_webhook(request):
    """New Webhook, on the API & Webhooks page."""
    form = WebhookForm(request.POST)
    if not form.is_valid():
        return _api_and_webhooks_page(request, webhook_form=form)
    webhook = webhooks.add(form.cleaned_data["name"], form.cleaned_data["url"])
    messages.success(
        request,
        _(
            "“%(name)s” is added: Pursegraph calls it when Transactions are waiting for a suggestion."
        )
        % {"name": webhook.name},
    )
    return redirect("api_and_webhooks")


@admin_required
@require_http_methods(["GET", "POST"])
def delete_webhook(request, pk):
    """Delete, confirmed inline under the Webhook's row."""
    webhook = get_object_or_404(Webhook, pk=pk)
    if request.method == "GET":
        if wants_the_fragment_alone(request):
            return render(request, "ledger/_confirm_delete_webhook.html", {"webhook": webhook})
        return _api_and_webhooks_page(request, confirm_webhook=webhook.pk)
    webhook.delete()
    messages.success(
        request, _("“%(name)s” is deleted: Pursegraph no longer calls it.") % {"name": webhook.name}
    )
    return redirect("api_and_webhooks")


@admin_required
@require_POST
def notify_webhook(request, pk):
    """Notify now: calls this Webhook alone, even when nothing is waiting, and waits for the reply. HTMX swaps the
    Webhook's row for one showing how it went."""
    webhook = webhooks.deliver(get_object_or_404(Webhook, pk=pk), suggestions.waiting_count())
    if not wants_the_fragment_alone(request):
        return redirect("api_and_webhooks")
    response = render(request, "ledger/_webhook_row.html", {"webhook": webhook})
    said = _("%(name)s: delivered.") if webhook.delivered else _("%(name)s: failed.")
    return announce(response, said % {"name": webhook.name})


def _suggestions_accepted(request, count: int) -> None:
    messages.success(
        request,
        ngettext("%(count)d suggestion accepted.", "%(count)d suggestions accepted.", count)
        % {"count": count},
    )


def rules(request):
    """The Rules page (docs/design/rules.md): the Rules in order beside the selected one's detail. `rule` opens a
    Rule (on a phone, over the list) and `at` only selects it. Asked for the detail alone (`HX-Target:
    rule-detail`), it swaps in just that."""
    opened = request.GET.get("rule", "")
    selected = _pk_or_none(opened or request.GET.get("at"))
    if wants_the_fragment_alone(request) and request.headers.get("HX-Target") == "rule-detail":
        context = _rules_context(selected)
        response = render(request, "ledger/_rule_detail.html", {**context, "alone": True})
        patch_vary_headers(response, ["HX-Request", "HX-Target"])
        return response
    return _rules_page(request, selected=selected, opened=bool(opened))


def _rules_page(request, *, selected=None, opened=False, confirm=False, focus=""):
    """The Rules page, or its region alone for HTMX: `selected` Rule's detail (else the first's), `opened` over the
    list on a phone, with its delete `confirm`ed inline, and `focus` naming what takes focus after a swap: its
    "option" in the list, its Move "up" or "down" button, or the detail's "heading"."""
    context = {
        **_rules_context(selected),
        "opened": opened,
        "confirm": confirm,
        "focus": focus,
        "page_title": _("Rules"),
    }
    if wants_the_fragment_alone(request):
        response = render(request, "ledger/_rules.html", {**context, "alone": True})
    else:
        response = render(request, "ledger/rules.html", context)
    patch_vary_headers(response, ["HX-Request", "HX-Target"])
    return response


def _rules_context(selected: int | None) -> dict:
    """The Rules in order, each with its `place` and how many Transactions it `categorized`, and the `rule` shown:
    `selected`, else the first. Its detail: what it categorized, its other matches, and the earlier Rules that take
    some of its matches."""
    rules = list(
        Rule.objects.select_related("account", "subcategory__category")
        .annotate(categorized=Count("transactions", filter=Q(transactions__source=Source.RULE)))
        # An aggregate leaves out Meta.ordering.
        .order_by("position", "id")
    )
    places = rule_edits.places()
    for r in rules:
        r.place = places[r.pk]  # type: ignore[attr-defined]
    rule = next((r for r in rules if r.pk == selected), rules[0] if rules else None)
    if rule is None:
        return {"rules": rules, "rule": None}
    # What it categorized, even those its conditions no longer match since an edit, then its other matches.
    categorized = Q(rule=rule, source=Source.RULE)
    matches = list(
        Transaction.objects.filter(rule.condition() | categorized)
        .select_related("account", "subcategory__category", "rule", "counterpart__account")
        .order_by("-date", "-pk")
    )
    mine = [t for t in matches if t.rule_id == rule.pk and t.source == Source.RULE]
    taken = [
        ngettext(
            "%(count)d of its matches goes to Rule %(place)d (%(name)s) above",
            "%(count)d of its matches go to Rule %(place)d (%(name)s) above",
            n,
        )
        % {"count": n, "place": places[earlier.pk], "name": earlier.name}
        for earlier, n in rule_edits.taken_above(rule)
    ]
    return {
        "rules": rules,
        "rule": rule,
        "last_place": len(rules),
        "mine": mine,
        "others": [t for t in matches if t not in mine],
        "taken": "; ".join(taken),
        **outcomes.picker(),
    }


def new_rule(request):
    """A new Rule; `?transaction=<pk>` pre-fills it from a corrected Transaction ("Make a Rule")."""
    made_from = _made_from(request)
    if request.method == "POST":
        return _rule_page(request, RuleForm(request.POST), made_from)
    form = RuleForm.from_transaction(made_from) if made_from else RuleForm()
    return _rule_page(request, form, made_from)


def edit_rule(request, pk):
    rule = get_object_or_404(Rule, pk=pk)
    if request.method == "POST":
        return _rule_page(request, RuleForm(request.POST, instance=rule))
    return _rule_page(request, RuleForm(instance=rule))


def _made_from(request) -> Transaction | None:
    """Make a Rule's Transaction, carried through the Rule page's posts."""
    pk = _pk_or_none(request.POST.get("transaction") or request.GET.get("transaction"))
    return get_object_or_404(Transaction, pk=pk) if pk else None


def _rule_page(request, form, made_from=None):
    """The Rule page (New Rule, Edit Rule, Make a Rule) with its live preview. A valid post saves the Rule, and with
    `apply` applies it to the existing Transactions too, then opens it on the Rules page with a line saying what
    changed. `preview` asks only for the preview, without JS."""
    if request.method == "POST" and "preview" not in request.POST and form.is_valid():
        rule = form.save()
        if request.POST.get("apply"):
            # Saying what changed: the matches already its outcome are counted as kept.
            changed = len(rule_edits.preview(rule).change)
            _count, pairing = rule_edits.apply_to_existing(rule)
            messages.success(request, _applied_said(changed, pairing))
        else:
            messages.success(
                request,
                _("Saved %(name)s. Future imports will use it.") % {"name": rule.name},
            )
        return redirect(f"{reverse('rules')}?rule={rule.pk}")
    return render(request, "ledger/rule_form.html", _rule_page_context(form, made_from))


def rule_preview(request):
    """The Rule page's preview for the conditions and outcome typed so far, swapped in as they change."""
    instance = (
        get_object_or_404(Rule, pk=pk) if (pk := _pk_or_none(request.GET.get("rule"))) else None
    )
    form = RuleForm(request.GET, instance=instance)
    context = _rule_page_context(form, _made_from(request))
    response = render(request, "ledger/_rule_preview.html", {**context, "swapped": True})
    return announce(response, _preview_said(context["preview"]))


def _preview_said(p: rule_edits.Preview) -> str:
    """The preview's new state, read out as the conditions change."""
    if p.empty:
        return _("Set a condition to see what it matches.")
    matched = len(p.change) + len(p.set_by_hand) + len(p.already) + len(p.keep)
    return ngettext(
        "%(count)d Transaction matches, %(changed)d would change.",
        "%(count)d Transactions match, %(changed)d would change.",
        matched,
    ) % {"count": matched, "changed": len(p.change)}


def _rule_page_context(form, made_from) -> dict:
    draft, chosen = form.draft()
    p = rule_edits.preview(draft, chosen=chosen, made_from=made_from)
    places = rule_edits.places()

    def with_places(rules):
        """(place, name, how many) for each of the other Rules a preview names."""
        return [(places[r.pk], r.name, n) for r, n in rules]

    words = None
    if made_from and not made_from.counterparty_iban:
        words = rule_edits.word_chips(made_from.description, draft.description_contains)
    return {
        "form": form,
        "draft": draft,
        "chosen": chosen,
        "made_from": made_from,
        "words": words,
        "preview": p,
        "groups": [
            (_("Will change"), p.change),
            (
                _(
                    "Set by hand to something else: kept now, but new ones like them would follow this Rule"
                ),
                p.set_by_hand,
            ),
            (_("Already %(outcome)s") % {"outcome": draft.outcome_label}, p.already),
            (_("Keep their outcome"), p.keep),
        ],
        "taken_over": with_places(p.taken_over),
        "shadowed": with_places(p.shadowed),
        "place": places.get(draft.pk),
    }


def _applied_said(count: int, pairing) -> str:
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
    return " ".join(sentences)


@require_http_methods(["GET", "POST"])
def delete_rule(request, pk):
    """Deletes a Rule after an inline confirmation; its Transactions keep their outcome. Then the Rule now in its
    place is selected."""
    rule = get_object_or_404(Rule, pk=pk)
    if request.method == "GET":
        if wants_the_fragment_alone(request):
            return render(
                request,
                "ledger/_confirm_delete_rule.html",
                {"rule": rule, "categorized": rule.transactions.filter(source=Source.RULE).count()},
            )
        return _rules_page(request, selected=rule.pk, opened=True, confirm=True)
    ids = list(rule_edits.places())
    at = ids.index(rule.pk)
    rule.delete()
    said = _("Deleted %(name)s.") % {"name": rule.name}
    rest = ids[:at] + ids[at + 1 :]
    following = rest[min(at, len(rest) - 1)] if rest else None
    if not wants_the_fragment_alone(request):
        messages.success(request, said)
        return redirect(f"{reverse('rules')}?at={following}" if following else reverse("rules"))
    return announce(_rules_page(request, selected=following, focus="option"), said)


@require_POST
def move_rule(request, pk):
    """Moves a Rule one place `up` or `down`, from the detail's Move buttons or Alt+↑/↓ in the list."""
    rule = get_object_or_404(Rule, pk=pk)
    direction = request.POST.get("direction", "")
    rule_edits.move(rule, direction)
    return _moved(request, rule, focus=request.POST.get("focus") or direction)


@require_POST
def reorder_rules(request):
    """The order after a drag: every Rule's id, top first, and the one `moved`."""
    ids = request.POST.getlist("rule")
    if not all(pk.isdigit() for pk in ids):
        return HttpResponseBadRequest()
    rule_edits.reorder([int(pk) for pk in ids])
    moved_pk = _pk_or_none(request.POST.get("moved"))
    moved = Rule.objects.filter(pk=moved_pk).first() if moved_pk else None
    if moved is None:
        return redirect("rules")
    return _moved(request, moved, focus="option")


def _moved(request, rule: Rule, *, focus: str):
    """After a move: the Rules page with `rule` selected, its new place announced."""
    if not wants_the_fragment_alone(request):
        return redirect(f"{reverse('rules')}?at={rule.pk}")
    place = rule_edits.places()[rule.pk]
    return announce(
        _rules_page(request, selected=rule.pk, focus=focus),
        _("Moved %(name)s to %(place)s.") % {"name": rule.name, "place": ordinal(place)},
    )
