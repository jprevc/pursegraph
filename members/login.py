"""Logging in (docs/design/login.md): the errors linked to their fields, the tries left before django-axes locks a
username on this device, and the locked-out page with the time the lock lifts."""

import math
from datetime import datetime

from axes.handlers.proxy import AxesProxyHandler
from axes.helpers import get_client_ip_address
from axes.models import AccessAttempt
from django.conf import settings
from django.contrib.auth import views as auth_views
from django.contrib.auth.forms import AuthenticationForm
from django.shortcuts import render
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

# From the 3rd wrong try on, the error says how many are left.
SAY_TRIES_LEFT_FROM = 3


class LoginForm(AuthenticationForm):
    error_messages = {
        **AuthenticationForm.error_messages,
        "invalid_login": _("That username and password don't match."),
    }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["username"].error_messages["required"] = _("Enter your username.")
        self.fields["password"].error_messages["required"] = _("Enter your password.")


class LoginView(auth_views.LoginView):
    form_class = LoginForm
    redirect_authenticated_user = True

    def form_invalid(self, form):
        username = form.data.get("username", "")
        tries_left = None
        if form.non_field_errors() and username:
            failures = AxesProxyHandler.get_failures(self.request, {"username": username})
            if failures >= SAY_TRIES_LEFT_FROM:
                tries_left = max(settings.AXES_FAILURE_LIMIT - failures, 0)
        return self.render_to_response(
            self.get_context_data(form=form, tries_left=tries_left, attempted=username)
        )


def lock_lifts_at(request, credentials) -> datetime:
    """When the lock on this username on this device lifts: an hour (AXES_COOLOFF_TIME) after its last wrong try."""
    # Axes counts per username and IP (AXES_LOCKOUT_PARAMETERS), and stamps the attempt with its last wrong try.
    attempt = (
        AccessAttempt.objects.filter(
            username=credentials.get("username"), ip_address=get_client_ip_address(request)
        )
        .order_by("-attempt_time")
        .first()
    )
    return (attempt.attempt_time if attempt else timezone.now()) + settings.AXES_COOLOFF_TIME


def locked_out(request, original_response=None, credentials=None):
    """django-axes's lockout response (AXES_LOCKOUT_CALLABLE)."""
    credentials = credentials or {}
    lifts_at = lock_lifts_at(request, credentials)
    minutes_left = max(1, math.ceil((lifts_at - timezone.now()).total_seconds() / 60))
    return render(
        request,
        "registration/locked_out.html",
        {
            "username": credentials.get("username", ""),
            "minutes_left": minutes_left,
            "lifts_at": lifts_at,
        },
        status=429,
    )
