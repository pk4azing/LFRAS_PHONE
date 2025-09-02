from django.contrib.auth.decorators import login_required
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.utils import timezone
from django.http import HttpResponse
from django.http import JsonResponse
from django.utils.http import url_has_allowed_host_and_scheme
from django.conf import settings
from django.views.decorators.http import require_POST
from django.template.loader import render_to_string

from .models import Notification
from .services import mark_read, mark_all_read


def _mark_read(obj: Notification):
    if obj.read_at:
        return False
    obj.read_at = timezone.now()
    obj.save(update_fields=["read_at"])
    return True


@login_required
def inbox(request):
    notes = Notification.objects.order_by("-created_at")
    unread_count = notes.filter(read_at__isnull=True).count()
    return render(
        request,
        "notifications/inbox.html",
        {"notifications": notes, "unread_count": unread_count},
    )


@login_required
@require_POST
def read(request, pk: int):
    n = get_object_or_404(Notification, pk=pk, recipient=request.user)
    changed = _mark_read(n)

    # If this was an AJAX call from the offcanvas, return JSON
    if request.headers.get("x-requested-with") == "XMLHttpRequest":
        return JsonResponse({"ok": True, "changed": changed})

    # Otherwise do a safe redirect (avoid open redirects)
    next_url = n.link_url or ""
    if not url_has_allowed_host_and_scheme(
        next_url, allowed_hosts={request.get_host()}, require_https=request.is_secure()
    ):
        next_url = None

    if changed:
        messages.info(request, "Notification marked as read.")
    # Fallback to an inbox page if you have one; else to home
    return redirect(next_url or getattr(settings, "NOTIFICATIONS_INBOX_URL", "/"))


@login_required
@require_POST
def read_all(request):
    qs = Notification.objects.filter(recipient=request.user, read_at__isnull=True)
    updated = qs.update(read_at=timezone.now())
    if request.headers.get("x-requested-with") == "XMLHttpRequest":
        return JsonResponse({"ok": True, "updated": updated})
    messages.info(request, f"Marked {updated} notification(s) as read.")
    return redirect(getattr(settings, "NOTIFICATIONS_INBOX_URL", "/"))


# Offcanvas panel (slider) endpoints
@login_required
def panel(request):
    html = render_to_string(
        "notifications/panel.html",
        {
            "notifications": request.user.notifications.all().order_by("-created_at")[
                :10
            ],
        },
        request=request,
    )
    return HttpResponse(html)


@login_required
@require_POST
def read_and_redirect(request, pk: int):
    n = get_object_or_404(Notification, pk=pk, recipient=request.user)
    mark_read(n)
    return redirect(n.link_url or "notifications:inbox")
