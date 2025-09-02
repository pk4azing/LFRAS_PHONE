# auditlog/views.py
from datetime import datetime
from django.contrib.auth.decorators import login_required
from django.http import HttpResponse
from django.shortcuts import render
from django.utils import timezone

from .models import AuditEvent
from accounts.models import Roles


def _role_scoped_qs(user):
    qs = AuditEvent.objects.all().select_related("actor")
    # Scope by role (as you specified)
    if user.role == Roles.LAD:
        return qs
    if user.role == Roles.LUS:
        return qs.exclude(actor__role=Roles.LAD)  # non-admin info
    if user.role == Roles.EAD:
        return qs.filter(evaluator_id=user.evaluator_id).exclude(
            actor__role__in=[Roles.LAD, Roles.LUS]
        )
    if user.role == Roles.EVS:
        return qs.filter(evaluator_id=user.evaluator_id).exclude(
            actor__role__in=[Roles.LAD, Roles.LUS, Roles.EAD]
        )
    if user.role == Roles.SUS:
        return qs.filter(supplier_id=user.supplier_id).exclude(
            actor__role__in=[Roles.LAD, Roles.LUS, Roles.EAD]
        )
    return AuditEvent.objects.none()


@login_required
def export_form(request):
    # Simple form UI with default last 30 days
    end = timezone.now()
    start = end - timezone.timedelta(days=30)
    return render(request, "audit/export.html", {"start": start, "end": end})


@login_required
def export_csv(request):
    # Parse dates (YYYY-MM-DD). Fallback to last 30 days.
    try:
        start_raw = request.GET.get("start") or ""
        end_raw = request.GET.get("end") or ""
        if start_raw and end_raw:
            start = timezone.make_aware(datetime.strptime(start_raw, "%Y-%m-%d"))
            end = timezone.make_aware(
                datetime.strptime(end_raw, "%Y-%m-%d")
            ) + timezone.timedelta(days=1)
        else:
            end = timezone.now()
            start = end - timezone.timedelta(days=30)
    except Exception:
        end = timezone.now()
        start = end - timezone.timedelta(days=30)

    qs = (
        _role_scoped_qs(request.user)
        .filter(created_at__gte=start, created_at__lt=end)
        .order_by("-created_at")
    )

    # CSV response
    resp = HttpResponse(content_type="text/csv")
    resp["Content-Disposition"] = (
        f'attachment; filename="audit_{start.date()}_{(end-timezone.timedelta(days=1)).date()}.csv"'
    )

    # Write header
    resp.write(
        "timestamp,actor_id,actor_email,verb,action,evaluator_id,supplier_id,metadata\n"
    )
    # Stream rows
    for e in qs.iterator():
        ts = e.created_at.astimezone(timezone.get_current_timezone()).strftime(
            "%Y-%m-%d %H:%M:%S"
        )
        actor_email = getattr(e.actor, "email", "") if e.actor_id else ""
        # Simple JSON compaction for metadata
        try:
            import json

            meta = json.dumps(
                e.metadata or {}, separators=(",", ":"), ensure_ascii=False
            )
        except Exception:
            meta = "{}"
        line = f'{ts},{e.actor_id or ""},{actor_email},{e.verb},{e.action},{e.evaluator_id or ""},{e.supplier_id or ""},{meta}\n'
        resp.write(line)
    return resp
