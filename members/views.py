from functools import wraps

from axes.utils import reset
from django.contrib import messages
from django.contrib.auth import get_user_model
from django.contrib.auth import views as auth_views
from django.core.exceptions import PermissionDenied
from django.db import transaction
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse_lazy
from django.utils.translation import gettext as _
from django.views.decorators.http import require_POST

from .forms import NewMemberForm
from .links import set_password_link


def admin_required(view):
    @wraps(view)
    def wrapper(request, *args, **kwargs):
        if not request.user.is_admin:
            raise PermissionDenied
        return view(request, *args, **kwargs)
    return wrapper


@admin_required
def member_list(request):
    members = get_user_model().objects.order_by("-is_active", "username")
    return render(request, "members/members.html", {"members": members})


@admin_required
def new_member(request):
    if request.method == "POST":
        form = NewMemberForm(request.POST)
        if form.is_valid():
            member = form.save()
            return render(request, "members/link.html", {
                "member": member, "link": set_password_link(request, member), "invite": True,
            })
    else:
        form = NewMemberForm()
    return render(request, "members/new_member.html", {"form": form})


@admin_required
@require_POST
def reset_link(request, pk):
    member = get_object_or_404(get_user_model(), pk=pk, is_active=True)
    return render(request, "members/link.html", {"member": member, "link": set_password_link(request, member)})


@admin_required
@require_POST
def set_active(request, pk):
    with transaction.atomic():
        member = _locked_member(pk)
        active = request.POST.get("active") == "1"
        if not active and _is_last_active_admin(member):
            messages.error(request, _("%(name)s is the last active admin and can't be deactivated.") % {
                "name": member.get_username(),
            })
        else:
            # An inactive Member's session stops working: the auth backend no longer returns them.
            member.is_active = active
            member.save(update_fields=["is_active"])
    return redirect("members")


@admin_required
@require_POST
def set_admin(request, pk):
    with transaction.atomic():
        member = _locked_member(pk)
        admin = request.POST.get("admin") == "1"
        if not admin and _is_last_active_admin(member):
            messages.error(request, _("%(name)s is the last active admin and can't lose the admin flag.") % {
                "name": member.get_username(),
            })
        else:
            member.is_admin = admin
            member.save(update_fields=["is_admin"])
    return redirect("members")


def _locked_member(pk):
    # Lock every active admin too, so two admins can't demote each other at the same time.
    Member = get_user_model()
    list(Member.objects.select_for_update().filter(is_active=True, is_admin=True))
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
        reset(username=self.user.get_username())
        messages.success(self.request, _("Your password is set. Log in with it."))
        return response
