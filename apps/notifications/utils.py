from typing import Optional, Dict, Any
from django.contrib.auth import get_user_model
from .models import Notification

User = get_user_model()

def add_notification(
    recipient: Any,
    cd,
    message: str,
    event: str,
    actor: Optional[Any] = None,
    level: str = "INFO",
    meta: Optional[Dict[str, Any]] = None,
) -> Notification:
    """
    Create an in-app notification for a user.
    Used throughout the project: tickets/reports/activities/tenants/accounts flows.
    """
    if recipient is None:
        return None
    return Notification.objects.create(
        recipient=recipient,
        cd=cd,
        message=message[:500],
        event=event[:64],
        level=level,
        meta=meta or {},
    )