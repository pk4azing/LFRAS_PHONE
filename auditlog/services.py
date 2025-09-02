from typing import Any, Optional
from django.contrib.contenttypes.models import ContentType
from .models import AuditEvent


def _ctx(request) -> dict:
    if not request:
        return {}
    return {
        "ip_address": request.META.get("REMOTE_ADDR"),
        "user_agent": request.META.get("HTTP_USER_AGENT", "")[:5000],
    }


def log_event(
    *,
    request=None,
    actor=None,
    verb: str,
    action: str,
    target: Optional[Any] = None,
    evaluator_id: Optional[int] = None,
    supplier_id: Optional[int] = None,
    metadata: dict | None = None,
) -> AuditEvent:
    """
    Usage:
        log_event(request=request, actor=request.user, verb="created",
                  action="supplier.create", target=supplier,
                  evaluator_id=supplier.evaluator_id, supplier_id=supplier.id,
                  metadata={"sus_email": sus.email})
    """
    ev = AuditEvent(
        actor=actor,
        verb=verb,
        action=action,
        evaluator_id=evaluator_id,
        supplier_id=supplier_id,
        metadata=metadata or {},
        **_ctx(request),
    )
    if target is not None:
        ev.target_ct = ContentType.objects.get_for_model(target.__class__)
        ev.target_id = str(getattr(target, "pk", None))
    ev.save()
    return ev
