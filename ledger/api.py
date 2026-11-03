"""The Categorizer API: how Categorizers fetch the Transactions waiting for a Suggestion and send Suggestions back
(docs/adr/0001-categorizers-pull-suggestions-through-an-api.md).

A Categorizer authenticates with `Authorization: Bearer <token>`, a token an admin created on the Categorizers page.
It has two calls:

- `GET /api/categorizer/v1/transactions/?limit=50`: the Transactions waiting for a Suggestion, oldest first, with
  the Subcategories to choose from and, for each, the Household's earlier manual outcomes as examples. Read-only:
  the same Transactions come back until Suggestions for them arrive.
- `POST /api/categorizer/v1/transactions/<id>/suggestion/` with a JSON body `{"subcategory": <id>, "confidence":
  <0 to 1>}`, or `{"subcategory": null}` for no suggestion.

It answers `{"stored": <bool>, "accepted": <bool>}`: not stored when the Transaction already had an outcome or a
Suggestion (the first one wins), accepted when it cleared the auto-accept threshold and set the outcome.

A missing, wrong or revoked token gets a 401, a malformed request or an unknown Subcategory a 400, an unknown
Transaction a 404 and a wrong method a 405. Errors other than 405 are `{"error": "<why>"}`.
"""

import json
from functools import wraps

from django.contrib.auth.decorators import login_not_required
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_GET, require_POST

from . import categorizers, suggestions
from .models import Subcategory, Transaction

# How many waiting Transactions one fetch returns at most, and by default.
MAX_LIMIT = 200
DEFAULT_LIMIT = suggestions.BATCH_SIZE


def _error(status: int, why: str) -> JsonResponse:
    return JsonResponse({"error": why}, status=status)


def categorizer_token_required(view):
    """Only a request with an active Categorizer token reaches the view, as `request.categorizer_token`; the
    session, CSRF token and login requirement of the rest of the app don't apply."""

    @login_not_required
    @csrf_exempt
    @wraps(view)
    def wrapper(request, *args, **kwargs):
        token = categorizers.authenticate(request.headers.get("Authorization", ""))
        if token is None:
            response = _error(401, "A valid Categorizer token is required.")
            response["WWW-Authenticate"] = "Bearer"
            return response
        request.categorizer_token = token
        return view(request, *args, **kwargs)

    return wrapper


@categorizer_token_required
@require_GET
def waiting(request):
    limit = request.GET.get("limit", str(DEFAULT_LIMIT))
    # isdigit() alone takes "²", which int() doesn't.
    if not (limit.isascii() and limit.isdigit()) or not 1 <= int(limit) <= MAX_LIMIT:
        return _error(400, f"limit must be a whole number from 1 to {MAX_LIMIT}.")
    subcategories, batch = suggestions.waiting(int(limit))
    return JsonResponse(
        {
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
    )


@categorizer_token_required
@require_POST
def suggestion(request, pk):
    try:
        body = json.loads(request.body)
    except ValueError:
        return _error(400, "The body must be JSON.")
    if not isinstance(body, dict) or "subcategory" not in body:
        return _error(400, 'The body must be an object with "subcategory".')
    subcategory_id = body["subcategory"]
    if not Transaction.objects.filter(pk=pk).exists():
        return _error(404, "No such Transaction.")
    if subcategory_id is None:
        result = suggestions.receive(pk, None, request.categorizer_token)
    else:
        confidence = body.get("confidence")
        if type(subcategory_id) is not int:
            return _error(400, '"subcategory" must be a Subcategory id or null.')
        # bool is an int to Python, but not a confidence; NaN fails the range.
        if (
            not isinstance(confidence, int | float)
            or isinstance(confidence, bool)
            or not 0 <= confidence <= 1
        ):
            return _error(400, '"confidence" must be a number from 0 to 1.')
        subcategory = Subcategory.objects.filter(pk=subcategory_id).first()
        if subcategory is None:
            return _error(
                400, "No such Subcategory; fetch the Transactions again for the current ones."
            )
        result = suggestions.receive(
            pk, suggestions.Suggestion(subcategory, float(confidence)), request.categorizer_token
        )
    return JsonResponse({"stored": result.stored, "accepted": result.accepted})
