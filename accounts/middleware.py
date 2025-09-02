# accounts/middleware.py
from django.shortcuts import redirect
from django.urls import reverse

WHITELIST_NAMES = {
    "accounts:change_password",
    "accounts:logout",
    "accounts:login",
}


class MustChangePasswordMiddleware:
    """
    If user.must_change_password is True, force them to the change-password page
    except for a small whitelist (login/logout/static).
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        u = getattr(request, "user", None)
        if u and u.is_authenticated and getattr(u, "must_change_password", False):
            # allow whitelisted urls
            try:
                match = request.resolver_match
                if match and f"{match.namespace}:{match.url_name}" in WHITELIST_NAMES:
                    return self.get_response(request)
            except Exception:
                pass
            # allow static/media
            p = request.path
            if p.startswith("/static/") or p.startswith("/media/"):
                return self.get_response(request)
            return redirect(reverse("accounts:change_password"))
        return self.get_response(request)
