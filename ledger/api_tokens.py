"""API tokens: what a program outside Pursegraph, such as a Categorizer, authenticates with to its API
(ledger/api.py).

An admin creates one per program and sees its secret once; only the secret's SHA-256 is stored. So far the API is
the Categorizer API alone, so a token can do nothing but fetch the Transactions waiting for a Suggestion and send
Suggestions back.
"""

import hashlib
import secrets

from django.db.models import QuerySet
from django.utils import timezone

from .models import ApiToken

# Marks a secret as a Pursegraph API token, such as in a secret scanner.
PREFIX = "pgc_"


def create(name: str, created_by) -> tuple[ApiToken, str]:
    """A new token named `name`, and its secret, which isn't stored and can't be shown again."""
    secret = PREFIX + secrets.token_urlsafe(32)
    token = ApiToken.objects.create(name=name, digest=_digest(secret), created_by=created_by)
    return token, secret


def active() -> "QuerySet[ApiToken]":
    return ApiToken.objects.filter(revoked_at__isnull=True)


def revoke(pk: int) -> ApiToken | None:
    """Revokes the token `pk`, if it is active: calls made with it get a 401 from now on."""
    token = active().filter(pk=pk).first()
    if token:
        token.revoked_at = timezone.now()
        token.save(update_fields=["revoked_at"])
    return token


def authenticate(authorization: str) -> ApiToken | None:
    """The active token an `Authorization: Bearer <secret>` header names, marked as used now; None for any other
    header."""
    scheme, _, secret = authorization.partition(" ")
    if scheme.lower() != "bearer" or not secret.strip():
        return None
    token = active().filter(digest=_digest(secret.strip())).first()
    if token:
        token.last_used_at = timezone.now()
        token.save(update_fields=["last_used_at"])
    return token


def _digest(secret: str) -> str:
    return hashlib.sha256(secret.encode()).hexdigest()
