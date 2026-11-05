from datetime import timedelta

from axes.utils import reset
from django.conf import settings
from django.contrib import messages
from django.contrib.auth import get_user_model
from django.contrib.auth import views as auth_views
from django.db import transaction
from django.db.models import Prefetch
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.template.loader import render_to_string
from django.urls import reverse_lazy
from django.utils import timezone
from django.utils.cache import patch_vary_headers
from django.utils.translation import gettext as _
from django.views.decorators.http import require_http_methods, require_POST

from ledger.models import Account
from ledger.setup import others_invited
from pursegraph.htmx import announce, wants_the_fragment_alone

from .forms import NewMemberForm, RenameMemberForm
from .links import set_password_link
from .permissions import admin_required


@admin_required
def member_list(request):
    return _members_page(request)


def _members_page(request, *, confirm=None, dialog=None):
    """The Members page (docs/design/admin.md), or its role cards alone for HTMX: `confirm` is a (kind, Member id)
    confirmed inline under that Member's row, `dialog` the context of the dialog shown open over the page, with its
    `dialog_template` (only without JS: with it, a dialog is swapped in alone)."""
    context = {**_roles(), "confirm": confirm, **(dialog or {})}
    if wants_the_fragment_alone(request):
        response = render(request, "members/_roles.html", {**context, "alone": True})
    else:
        # Only the first admin is active so far: the page asks to invite the rest of the Household.
        context |= {"alone": False, "only_admin": not others_invited()}
        response = render(request, "members/members.html", context)
    patch_vary_headers(response, ["HX-Request", "HX-History-Restore-Request"])
    return response


def _roles() -> dict:
    """The Members grouped by role, the section being their state: active admins, active Members, deactivated. Each
    Member with the names of the Accounts they own, and `last_admin` on the only active admin."""
    members = list(
        get_user_model()
        .objects.prefetch_related(Prefetch("accounts", queryset=Account.objects.order_by("name")))
        .order_by("username")
    )
    admins = [m for m in members if m.is_active and m.is_admin]
    for m in members:
        m.last_admin = len(admins) == 1 and m in admins  # type: ignore[attr-defined]
    return {
        "groups": [
            {
                "key": "admins",
                "title": _("Admins"),
                "text": _(
                    "Manage Members, Accounts, Categories and Categorizers, and do everything a Member does."
                ),
                "members": admins,
            },
            {
                "key": "members",
                "title": _("Members"),
                "text": _("Import their Statements, work the Review queue and read the Dashboard."),
                "members": [m for m in members if m.is_active and not m.is_admin],
            },
            {
                "key": "deactivated",
                "title": _("Deactivated"),
                "text": _("Can't log in. What they imported and decided stays."),
                "members": [m for m in members if not m.is_active],
            },
        ],
        "page_title": _("Members"),
    }


@admin_required
@require_http_methods(["GET", "POST"])
def new_member(request):
    """Invite a Member: a dialog with their name and username, then the dialog with their invite link."""
    form = NewMemberForm(request.POST or None)
    if form.is_valid():
        return _link(request, form.save(), invite=True, new=True)
    return _dialog(request, "members/_invite_dialog.html", {"form": form})


@admin_required
@require_POST
def reset_link(request, pk):
    """A new one-time link for a Member: a password-reset link, or a new invite while they haven't used theirs."""
    member = get_object_or_404(get_user_model(), pk=pk, is_active=True)
    return _link(request, member, invite=not member.has_usable_password())


def _link(request, member, *, invite: bool, new=False):
    return _dialog(
        request,
        "members/_link_dialog.html",
        {
            "member": member,
            "name": _name(member),
            "link": set_password_link(request, member),
            "invite": invite,
            "expires": timezone.localtime(
                timezone.now() + timedelta(seconds=settings.PASSWORD_RESET_TIMEOUT)
            ),
        },
        roles=new,
    )


def _dialog(request, template: str, context: dict, *, roles=False):
    """A dialog over the Members page: swapped in alone for HTMX, with the role cards too when they changed (a new
    Member's row); else the page with it open."""
    if not wants_the_fragment_alone(request):
        return _members_page(request, dialog={"dialog_template": template, **context})
    html = render_to_string(template, context, request)
    if roles:
        html += render_to_string("members/_roles.html", {**_roles(), "oob": True}, request)
    return HttpResponse(html)


@admin_required
@require_http_methods(["GET", "POST"])
def set_active(request, pk):
    """Deactivates a Member after an inline confirmation (`active=0`), or reactivates one at once (`active=1`)."""
    if request.method == "GET":
        return _confirm(request, "deactivate", pk)
    with transaction.atomic():
        member = _locked_member(pk)
        active = request.POST.get("active") == "1"
        if not active and _is_last_active_admin(member):
            return _stepped(
                request,
                _("%(name)s is the last active admin and can't be deactivated.")
                % {"name": _name(member)},
                refused=True,
            )
        # An inactive Member's session stops working: the auth backend no longer returns them.
        member.is_active = active
        member.save(update_fields=["is_active"])
    said = (
        _("%(name)s is active again and can log in.") if active else _("%(name)s is deactivated.")
    ) % {"name": _name(member)}
    return _stepped(request, said)


@admin_required
@require_http_methods(["GET", "POST"])
def set_admin(request, pk):
    """Makes a Member an admin after an inline confirmation (`admin=1`), or takes the rights away at once
    (`admin=0`)."""
    if request.method == "GET":
        return _confirm(request, "admin", pk)
    with transaction.atomic():
        member = _locked_member(pk)
        admin = request.POST.get("admin") == "1"
        if not admin and _is_last_active_admin(member):
            return _stepped(
                request,
                _("%(name)s is the last active admin and can't lose the admin flag.")
                % {"name": _name(member)},
                refused=True,
            )
        member.is_admin = admin
        member.save(update_fields=["is_admin"])
    said = (_("%(name)s is now an admin.") if admin else _("%(name)s is no longer an admin.")) % {
        "name": _name(member)
    }
    return _stepped(request, said)


@admin_required
@require_http_methods(["GET", "POST"])
def rename(request, pk):
    """Renames a Member through a dialog with their name. Only admins rename, any Member, deactivated ones too."""
    member = get_object_or_404(get_user_model(), pk=pk)
    before = _name(member)
    form = RenameMemberForm(request.POST or None, initial={"name": member.first_name})
    if not form.is_valid():
        return _dialog(
            request, "members/_rename_dialog.html", {"form": form, "m": member, "name": before}
        )
    unchanged = form.cleaned_data["name"] == member.first_name
    if not unchanged:
        member.first_name = form.cleaned_data["name"]
        member.save(update_fields=["first_name"])
    if not wants_the_fragment_alone(request):
        if unchanged:
            return redirect("members")
        return _stepped(request, _said_renamed(before, member))
    # The dialog slot emptied, which closes the dialog, and the role cards swapped out of band.
    response = HttpResponse(
        render_to_string("members/_roles.html", {**_roles(), "oob": True}, request)
    )
    return response if unchanged else announce(response, _said_renamed(before, member))


def _said_renamed(before: str, member) -> str:
    return _("%(before)s is now %(after)s.") % {"before": before, "after": _name(member)}


def _confirm(request, kind: str, pk):
    """The inline confirmation of making a Member an admin (`kind` "admin") or deactivating them: alone for HTMX,
    else the page with it under their row."""
    member = get_object_or_404(get_user_model(), pk=pk)
    if not wants_the_fragment_alone(request):
        return _members_page(request, confirm=(kind, member.pk))
    return render(request, "members/_confirm_member.html", {"m": member, "kind": kind})


def _stepped(request, said: str, *, refused=False):
    """After a step on a Member: with HTMX the role cards again and the step announced, else the page by redirect."""
    if not wants_the_fragment_alone(request):
        (messages.error if refused else messages.success)(request, said)
        return redirect("members")
    return announce(_members_page(request), said)


def _name(member) -> str:
    return member.get_full_name() or member.get_username()


def _locked_member(pk):
    # Lock every active admin too, so two admins can't demote each other at the same time.
    Member = get_user_model()
    list(Member.objects.select_for_update().filter(is_active=True, is_admin=True).order_by("pk"))
    return get_object_or_404(Member.objects.select_for_update(), pk=pk)


def _is_last_active_admin(member):
    others = get_user_model().objects.filter(is_active=True, is_admin=True).exclude(pk=member.pk)
    return member.is_active and member.is_admin and not others.exists()


class SetPasswordView(auth_views.PasswordResetConfirmView):
    """Where an invite or password-reset link lands: the Member chooses their own password."""

    template_name = "members/set_password.html"
    success_url = reverse_lazy("login")

    def get_user(self, uidb64):
        user = super().get_user(uidb64)
        # A deactivated Member's links stop working.
        return user if user is not None and user.is_active else None

    def form_valid(self, form):
        response = super().form_valid(form)
        reset(username=form.user.get_username())
        messages.success(self.request, _("Your password is set. Log in with it."))
        return response
