from django.contrib import admin
from django.urls import path, include
from django.views.generic import RedirectView

urlpatterns = [
    path("admin/", admin.site.urls),
    # … your other routes …
    path("__reload__/", include("django_browser_reload.urls")),

    # Auth (session-based, templates)
    path("auth/", include(("accounts.urls", "accounts"), namespace="accounts")),
    # Role redirect + dashboards (template views)
    path("", include(("router.urls", "router"), namespace="router")),
    # Marketing landing (temporary here; subdomain routing later)
    path("", include(("marketing.urls", "marketing"), namespace="marketing")),
    # Convenience: root → landing for now
    path("", RedirectView.as_view(pattern_name="marketing_home", permanent=False)),
    path("tenants/", include(("tenants.urls", "tenants"), namespace="tenants")),
    path(
        "notifications/",
        include(("notifications.urls", "notifications"), namespace="notifications"),
    ),
    path("documents/", include(("documents.urls", "documents"), namespace="documents")),
    path("tickets/", include(("tickets.urls", "tickets"), namespace="tickets")),
    path(
        "activities/",
        include(("activities.urls", "activities"), namespace="activities"),
    ),
    path(
        "validation/",
        include(("validation.urls", "validation"), namespace="validation"),
    ),
    path(
        "settings/",
        include(("preferences.urls", "preferences"), namespace="preferences"),
    ),
    path("audit/", include(("auditlog.urls", "auditlog"), namespace="audit")),
    path("payments/", include(("payments.urls", "payments"), namespace="payments")),
]
