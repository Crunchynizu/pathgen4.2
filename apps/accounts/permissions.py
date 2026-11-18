"""Server-side role checks for every protected view (docs/user_features.md, "Permissions")."""
from functools import wraps

from django.contrib.auth.views import redirect_to_login
from django.core.exceptions import PermissionDenied
from django.urls import reverse

ADMIN = "admin"
TEACHER = "teacher"
STUDENT = "student"


def role_required(*roles):
    """Signed-out visitors go to sign-in; a signed-in account with another role gets 403."""

    def decorator(view):
        @wraps(view)
        def wrapped(request, *args, **kwargs):
            if not request.user.is_authenticated:
                return redirect_to_login(request.get_full_path(), reverse("accounts:login"))
            if request.user.role not in roles:
                raise PermissionDenied
            return view(request, *args, **kwargs)

        return wrapped

    return decorator


def landing_url(user):
    """Where each role starts after sign-in."""
    if user.role == ADMIN:
        return reverse("dashboards:admin", args=["overview"])
    if user.role == TEACHER:
        return reverse("dashboards:teacher", args=["overview"])
    return reverse("dashboards:learn")
