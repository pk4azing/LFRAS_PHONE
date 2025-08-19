# apps/audit/utils.py
from typing import Optional, Dict, Any
from django.contrib.auth import get_user_model
from .models import AuditLog

User = get_user_model()

def add_audit(
    actor: Optional[Any],
    cd,                         # tenants.ClientCD or None
    event: str,
    target_user: Optional[Any] = None,
    meta: Optional[Dict[str, Any]] = None,
) -> AuditLog:
    """
    Small helper used everywhere to write an audit row.
    """
    return AuditLog.objects.create(
        actor=actor,
        cd=cd,
        event=event[:64],
        target_user=target_user,
        meta=meta or {},
    )