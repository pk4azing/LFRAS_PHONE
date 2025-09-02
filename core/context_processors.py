# core/context_processors.py
from django.conf import settings
from notifications.models import Notification


def role_theme(request):
    role = getattr(getattr(request, "user", None), "role", "") or ""
    return {"role_theme_class": settings.ROLE_THEME_CLASS.get(role, "")}


def unread_notifications(request):
    try:
        u = getattr(request, "user", None)
        if not (u and u.is_authenticated):
            return {"unread_notifications": 0}
        return {
            "unread_notifications": Notification.objects.filter(
                recipient=u, is_read=False
            ).count()
        }
    except Exception:
        return {"unread_notifications": 0}
