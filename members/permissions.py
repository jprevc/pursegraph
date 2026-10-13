from functools import wraps

from django.core.exceptions import PermissionDenied


def admin_required(view):
    """Only admins may use the view; any other Member gets a 403."""

    @wraps(view)
    def wrapper(request, *args, **kwargs):
        if not request.user.is_admin:
            raise PermissionDenied
        return view(request, *args, **kwargs)

    return wrapper
