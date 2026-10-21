"""What a response tells the shell's swap script (static/swap.js) through HTMX's headers."""

import json
from urllib.parse import urlsplit

from django.contrib.auth.middleware import LoginRequiredMiddleware
from django.contrib.auth.views import redirect_to_login
from django.http import HttpResponse
from django.shortcuts import resolve_url
from django.utils.http import url_has_allowed_host_and_scheme


def announce(response: HttpResponse, message: str) -> HttpResponse:
    """Has the shell read `message` out through its polite live region, just after the swap: the new state in the
    page's own words, without figures. Keeps any other `HX-Trigger` events the response already sets."""
    triggers = _triggers(response.get("HX-Trigger", ""))
    triggers["announce"] = message
    # ASCII-escaped, as a header can't carry "–" or "›" as they are; HTMX parses the escapes back.
    response["HX-Trigger"] = json.dumps(triggers)
    return response


def _triggers(header: str) -> dict:
    """`HX-Trigger`'s events, from its JSON form or its comma-separated names."""
    if header.startswith("{"):
        return json.loads(header)
    return {name.strip(): None for name in header.split(",") if name.strip()}


class SwapAwareLoginRequiredMiddleware(LoginRequiredMiddleware):
    """Django's login requirement, except that an HTMX swap after the session expired gets a 401 that sends the
    whole page to log in, rather than a redirect that HTMX would follow and swap the login form into the region."""

    def handle_no_permission(self, request, view_func):
        if not request.headers.get("HX-Request"):
            return super().handle_no_permission(request, view_func)
        login = redirect_to_login(
            _page_shown(request),
            resolve_url(self.get_login_url(view_func)),
            self.get_redirect_field_name(view_func),
        )
        response = HttpResponse(status=401)
        response["HX-Redirect"] = login["Location"]
        return response


def _page_shown(request) -> str:
    """The path of the page the swap was made from, so that logging in goes back to it rather than to a fragment."""
    current = request.headers.get("HX-Current-URL", "")
    if not url_has_allowed_host_and_scheme(current, allowed_hosts={request.get_host()}):
        return request.get_full_path()
    url = urlsplit(current)
    return f"{url.path}?{url.query}" if url.query else url.path
