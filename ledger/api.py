"""The Categorizer API: how Categorizers fetch the Transactions waiting for a Suggestion and send Suggestions back
(docs/adr/0002-no-bundled-categorizer-webhooks-say-when-transactions-wait.md). Built with Django Ninja, which
validates requests against the schemas below and describes the API at `/api/categorizer/v1/docs` for Members who are
logged in.

A Categorizer authenticates with `Authorization: Bearer <token>`, an API token (ledger/api_tokens.py) an admin created
on the API & Webhooks page. It has two calls:

- `GET /api/categorizer/v1/transactions/?limit=50`: the Transactions waiting for a Suggestion, oldest first, with
  the Subcategories to choose from and, for each, the Household's earlier manual outcomes as examples. Read-only:
  the same Transactions come back until Suggestions for them arrive.
- `POST /api/categorizer/v1/transactions/<id>/suggestion/` with a JSON body `{"subcategory": <id>, "confidence":
  <0 to 1>}`, or `{"subcategory": null}` for no suggestion.

It answers `{"stored": <bool>, "accepted": <bool>}`: not stored when the Transaction already had an outcome or a
Suggestion (the first one wins), accepted when it cleared the auto-accept threshold and set the outcome.

A missing, wrong or revoked token gets a 401, a malformed request or an unknown Subcategory a 400, an unknown
Transaction a 404 and a wrong method a 405, before the token is checked. Errors other than 405 are `{"error": "<why>"}`.
"""

from typing import Annotated, Self

from django.contrib.auth.decorators import login_not_required
from django.urls import URLPattern
from ninja import Field, NinjaAPI, Query, Schema
from ninja.errors import AuthenticationError, HttpError, ValidationError
from ninja.security import HttpBearer
from pydantic import StrictInt, model_validator
from pydantic_core import PydanticCustomError

from . import api_tokens, suggestions
from .models import ApiToken, Subcategory, Transaction

# How many waiting Transactions one fetch returns at most, and by default.
MAX_LIMIT = 200
DEFAULT_LIMIT = suggestions.BATCH_SIZE


class ApiTokenAuth(HttpBearer):
    """An active API token in `Authorization: Bearer <secret>`, which the operations get as `request.auth`."""

    def authenticate(self, request, token: str) -> ApiToken | None:
        return api_tokens.authenticate(token)


api = NinjaAPI(
    title="Pursegraph Categorizer API",
    version="1",
    urls_namespace="categorizer_api",
    auth=ApiTokenAuth(),
)


@api.exception_handler(AuthenticationError)
def _unauthenticated(request, exc):
    response = api.create_response(request, {"error": "A valid API token is required."}, status=401)
    response["WWW-Authenticate"] = "Bearer"
    return response


@api.exception_handler(HttpError)
def _http_error(request, exc):
    return api.create_response(request, {"error": exc.message}, status=exc.status_code)


@api.exception_handler(ValidationError)
def _invalid(request, exc):
    return api.create_response(request, {"error": _why(exc.errors)}, status=400)


def _why(errors: list[dict]) -> str:
    """Pydantic's errors as one sentence each, after the field they are about: `"confidence": Input should be…`."""
    return " ".join(f"{_field(error['loc'])}{error['msg']}." for error in errors)


def _field(loc) -> str:
    """The field an error's location names, such as `"confidence": ` for ("body", "payload", "confidence"), or
    nothing for an error about the whole body."""
    # A location starts with where the value came from; a body's then names the operation's parameter for it.
    where, *path = loc
    if where == "body":
        path = path[1:]
    return f'"{".".join(map(str, path))}": ' if path else ""


class Error(Schema):
    error: str


class SubcategoryOut(Schema):
    id: int
    label: str = Field(description='Its Category and name, such as "Food > Groceries".')


class Example(Schema):
    """An earlier Transaction a Member put in a Subcategory."""

    direction: str = Field(description='"in" or "out".')
    description: str
    detail: str
    subcategory: int


class WaitingTransaction(Schema):
    id: int
    direction: str = Field(description='"in" or "out".')
    amount: str = Field(description='Without a sign, with two decimals, such as "12.30".')
    description: str
    detail: str
    examples: list[Example]


class Waiting(Schema):
    subcategories: list[SubcategoryOut]
    transactions: list[WaitingTransaction]


class SuggestionIn(Schema):
    subcategory: StrictInt | None = Field(
        description="A Subcategory's id, or null for no suggestion."
    )
    confidence: Annotated[float, Field(ge=0, le=1, strict=True, allow_inf_nan=False)] | None = (
        Field(None, description="From 0 to 1; required with a Subcategory.")
    )

    @model_validator(mode="after")
    def _confidence_with_a_subcategory(self) -> Self:
        if self.subcategory is not None and self.confidence is None:
            # Not a ValueError, which Pydantic's message would start with "Value error, ".
            raise PydanticCustomError("missing", '"confidence": Field required with a Subcategory')
        return self


class Received(Schema):
    stored: bool = Field(
        description="False when the Transaction already had an outcome or a Suggestion."
    )
    accepted: bool = Field(
        description="True when it cleared the auto-accept threshold and set the outcome."
    )


@api.get(
    "/transactions/",
    response={200: Waiting, 400: Error, 401: Error},
    url_name="waiting",
    summary="The Transactions waiting for a Suggestion",
)
def waiting(request, limit: int = Query(DEFAULT_LIMIT, ge=1, le=MAX_LIMIT)):
    """Oldest first, with the Subcategories to choose from. Read-only: the same Transactions come back until
    Suggestions for them arrive."""
    subcategories, batch = suggestions.waiting(limit)
    return {
        "subcategories": [{"id": s.pk, "label": suggestions.label(s)} for s in subcategories],
        "transactions": [
            {
                "id": pk,
                "direction": query.direction,
                "amount": f"{query.amount:.2f}",
                "description": query.description,
                "detail": query.detail,
                "examples": [
                    {
                        "direction": example.direction,
                        "description": example.description,
                        "detail": example.detail,
                        "subcategory": example.subcategory.pk,
                    }
                    for example in query.examples
                ],
            }
            for pk, query in batch
        ],
    }


@api.post(
    "/transactions/{int:pk}/suggestion/",
    response={200: Received, 400: Error, 401: Error, 404: Error},
    url_name="suggestion",
    summary="Send a Suggestion for a Transaction",
)
def suggestion(request, pk: int, payload: SuggestionIn):
    """The first Suggestion for a Transaction wins; later ones aren't stored."""
    if not Transaction.objects.filter(pk=pk).exists():
        raise HttpError(404, "No such Transaction.")
    if payload.subcategory is None:
        result = suggestions.receive(pk, None, request.auth)
    else:
        subcategory = Subcategory.objects.filter(pk=payload.subcategory).first()
        if subcategory is None:
            raise HttpError(
                400, "No such Subcategory; fetch the Transactions again for the current ones."
            )
        assert payload.confidence is not None  # the schema requires one with a Subcategory
        result = suggestions.receive(
            pk, suggestions.Suggestion(subcategory, payload.confidence), request.auth
        )
    return {"stored": result.stored, "accepted": result.accepted}


# The OpenAPI description, its docs page and the API's root stay behind the login, for Members.
_FOR_MEMBERS = {"openapi-json", "openapi-view", "api-root"}


def urls():
    """The API's URL patterns, for `path()`: an API token alone reaches its operations, without the session and
    login the rest of the app requires."""
    patterns, app_name, namespace = api.urls
    for pattern in patterns:
        if isinstance(pattern, URLPattern) and pattern.name not in _FOR_MEMBERS:
            login_not_required(pattern.callback)
    return patterns, app_name, namespace
