"""One-time links that let a Member set their own password: invites and password resets alike.

They are Django's password-reset tokens, so nothing is stored: a link dies once the password
changes (or the Member logs in), and after PASSWORD_RESET_TIMEOUT (7 days).
"""

from django.contrib.auth.tokens import default_token_generator
from django.urls import reverse
from django.utils.encoding import force_bytes
from django.utils.http import urlsafe_base64_encode


def set_password_link(request, member) -> str:
    path = reverse("set_password", kwargs={
        "uidb64": urlsafe_base64_encode(force_bytes(member.pk)),
        "token": default_token_generator.make_token(member),
    })
    return request.build_absolute_uri(path)
