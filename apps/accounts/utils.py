from typing import Iterable, Optional, Any
from django.contrib.auth import get_user_model
from django.db import transaction

User = get_user_model()

# --- Notifications & Audit helpers (thin wrappers) ---

def add_notification(user, cd, message: str, event: str, actor: Optional[Any] = None):
    """
    Create an in-app one-liner notification for a user.
    Expects apps.notifications.models.Notification(user, cd, message, event, actor)
    """
    try:
        from apps.notifications.models import Notification
        Notification.objects.create(user=user, cd=cd, message=message, event=event, actor=actor)
    except Exception:
        # Soft-fail if notifications app is absent; you can log this
        pass

def add_audit(actor: Optional[Any], cd, event: str, target_user: Optional[Any] = None, meta: Optional[dict] = None):
    """
    Save an audit row. Expects apps.audit.models.AuditLog(actor, cd, event, target_user, meta)
    """
    try:
        from apps.audit.models import AuditLog
        AuditLog.objects.create(actor=actor, cd=cd, event=event, target_user=target_user, meta=meta or {})
    except Exception:
        pass

def cd_poc_emails(cd) -> list[str]:
    """
    Returns best-guess emails for CD POCs:
    - cd.email if present
    - all CD_ADMIN emails in this tenant
    """
    emails = set()
    if getattr(cd, "email", None):
        emails.add(cd.email)
    if cd:
        for u in User.objects.filter(cd=cd, role="CD_ADMIN").values_list("email", flat=True):
            if u:
                emails.add(u)
    return list(emails)

def ld_superadmin_emails() -> list[str]:
    return list(User.objects.filter(role="LD", is_superuser=True).values_list("email", flat=True))