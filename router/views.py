from __future__ import annotations
from datetime import timedelta, date
from django.db import models

from django.contrib import messages
from django.contrib.auth.decorators import login_required, user_passes_test
from django.db.models import Count, Sum
from django.db.models.functions import TruncMonth
from django.shortcuts import redirect, render
from django.utils import timezone

from accounts.models import Roles
from documents.models import Document


# ---------- helpers ----------


def _parse_range(request):
    """Parse ?range=7d|30d|90d (default 30d). Returns (start, end, label)."""
    end = timezone.now()
    rng = (request.GET.get("range") or "").lower()
    days = 30 if rng not in {"7d", "90d"} else (7 if rng == "7d" else 90)
    start = end - timedelta(days=days)
    return start, end, f"last{days}"


def _shift_month(d: date, delta_months: int) -> date:
    """First day of month shifted by delta_months (can be negative)."""
    y = d.year + (d.month - 1 + delta_months) // 12
    m = (d.month - 1 + delta_months) % 12 + 1
    return date(y, m, 1)


def _last_12_month_labels():
    end = date.today().replace(day=1)
    labels = []
    for i in range(11, -1, -1):
        labels.append(_shift_month(end, -i).strftime("%b %Y"))
    return labels


def _human_bytes(n: int) -> str:
    if not n:
        return "0 B"
    units = ["B", "KB", "MB", "GB", "TB", "PB"]
    i = 0
    f = float(n)
    while f >= 1024 and i < len(units) - 1:
        f /= 1024.0
        i += 1
    return f"{f:.2f} {units[i]}"


def _monthly_count_series(qs, ts_field: str, labels):
    if qs is None:
        return [0] * len(labels)
    agg = (
        qs.annotate(m=TruncMonth(ts_field))
        .values("m")
        .annotate(c=Count("id"))
        .order_by("m")
    )
    m = {k: 0 for k in labels}
    for row in agg:
        if row["m"]:
            key = row["m"].strftime("%b %Y")
            if key in m:
                m[key] = int(row["c"] or 0)
    return [m[k] for k in labels]


def _monthly_sum_series(qs, ts_field: str, amount_field: str, labels):
    if qs is None:
        return [0] * len(labels)
    agg = (
        qs.annotate(m=TruncMonth(ts_field))
        .values("m")
        .annotate(s=Sum(amount_field))
        .order_by("m")
    )
    m = {k: 0 for k in labels}
    for row in agg:
        if row["m"]:
            key = row["m"].strftime("%b %Y")
            if key in m:
                m[key] = float(row["s"] or 0)
    return [m[k] for k in labels]


# role checks
def is_LAD(u):
    return u.is_authenticated and u.role == Roles.LAD


def is_LUS(u):
    return u.is_authenticated and u.role == Roles.LUS


def is_EAD(u):
    return u.is_authenticated and u.role == Roles.EAD


def is_EVS(u):
    return u.is_authenticated and u.role == Roles.EVS


def is_SUS(u):
    return u.is_authenticated and u.role == Roles.SUS


def _require_evaluator(user):
    return getattr(user, "evaluator", None)


def _require_supplier(user):
    return getattr(user, "supplier", None)


# ---------- entry ----------


def index(request):
    if not request.user.is_authenticated:
        return redirect("marketing:home")
    role = getattr(request.user, "role", None)
    if role == Roles.LAD:
        return redirect("router:lad")
    if role == Roles.LUS:
        return redirect("router:lus")
    if role == Roles.EAD:
        return redirect("router:ead")
    if role == Roles.EVS:
        return redirect("router:evs")
    if role == Roles.SUS:
        return redirect("router:sus")
    messages.error(request, "No dashboard available for your role.")
    return redirect("accounts:logout")


# ---------- LAD ----------


@login_required
@user_passes_test(is_LAD)
def lad_dashboard(request):
    start, end, label = _parse_range(request)

    from tenants.models import Evaluator, Supplier
    from accounts.models import User

    try:
        from documents.models import Document
    except Exception:
        Document = None
    try:
        from tickets.models import Ticket, TicketAttachment
    except Exception:
        Ticket = TicketAttachment = None
    try:
        from activities.models import ActivityFile
    except Exception:
        ActivityFile = None
    try:
        from notifications.models import Notification
    except Exception:
        Notification = None
    try:
        from payments.models import PaymentTransaction
    except Exception:
        PaymentTransaction = None

    eval_count = Evaluator.objects.filter(is_active=True).count()
    supplier_count = Supplier.objects.count()
    lucid_staff = User.objects.filter(role__in=[Roles.LAD, Roles.LUS]).count()
    docs_range = (
        Document.objects.filter(uploaded_at__range=(start, end)).count()
        if Document
        else 0
    )
    open_tickets = (
        Ticket.objects.exclude(status__in=["resolved", "closed"]).count()
        if Ticket
        else 0
    )
    notif_sent = (
        Notification.objects.filter(created_at__range=(start, end)).count()
        if Notification
        else 0
    )

    # ---- recent rows (pre-sliced; no further filtering in templates) ----
    recent_evaluators = list(Evaluator.objects.order_by("-created_at")[:5])
    recent_suppliers = list(Supplier.objects.order_by("-created_at")[:5])
    recent_tickets = (
        list(
            Ticket.objects.exclude(status__in=["resolved", "closed"])  # filter first
            .select_related("evaluator", "supplier")
            .order_by("-created_at")[:6]
        )
        if Ticket
        else []
    )

    # storage
    doc_bytes = (
        Document.objects.filter(uploaded_at__range=(start, end)).aggregate(
            s=Sum("file_size")
        )["s"]
        or 0
        if Document
        else 0
    )
    attach_bytes = 0
    if TicketAttachment:
        try:
            # If the model has a persisted file_size field, use the DB to sum it.
            field_names = {f.name for f in TicketAttachment._meta.get_fields()}
            if "file_size" in field_names:
                attach_bytes = TicketAttachment.objects.aggregate(s=Sum("file_size")).get("s") or 0
            else:
                # Fall back to summing the in-storage sizes (no DB column). This keeps the
                # dashboard working without altering the schema.
                attach_bytes = sum((a.file.size or 0) for a in TicketAttachment.objects.only("file"))
        except Exception:
            attach_bytes = 0
    act_bytes = (
        ActivityFile.objects.aggregate(s=Sum("file_size"))["s"] or 0
        if ActivityFile
        else 0
    )
    total_bytes = (
        ActivityFile.objects.aggregate(total=models.Sum("file_size")).get("total") or 0
    )
    s3_used = _human_bytes(total_bytes)

    # charts
    labels = _last_12_month_labels()
    chart_revenue = _monthly_sum_series(
        PaymentTransaction.objects.all() if PaymentTransaction else None,
        "paid_on",
        "amount",
        labels,
    )
    total_revenue = float(sum(chart_revenue or []))
    chart_evals = _monthly_count_series(Evaluator.objects.all(), "created_at", labels)

    recent_payments = (
        list(PaymentTransaction.objects.all().order_by("-paid_on")[:6])
        if PaymentTransaction
        else []
    )

    ctx = dict(
        range_label=label,
        start=start,
        end=end,
        eval_count=eval_count,
        supplier_count=supplier_count,
        lucid_staff=lucid_staff,
        docs_range=docs_range,
        open_tickets=open_tickets,
        notif_sent=notif_sent,
        storage_bytes=total_bytes,
        chart_labels=labels,
        chart_revenue=chart_revenue,
        total_revenue=total_revenue,
        chart_evals=chart_evals,
        recent_evaluators=recent_evaluators,
        recent_suppliers=recent_suppliers,
        recent_tickets=recent_tickets,
        recent_payments=recent_payments,
    )
    return render(request, "dash/lad.html", ctx)


# ---------- LUS ----------


@login_required
@user_passes_test(is_LUS)
def lus_dashboard(request):
    start, end, label = _parse_range(request)

    from tenants.models import Evaluator, Supplier
    from accounts.models import User

    try:
        from documents.models import Document
    except Exception:
        Document = None
    try:
        from tickets.models import Ticket
    except Exception:
        Ticket = None

    eval_count = Evaluator.objects.count()
    supplier_count = Supplier.objects.count()
    lucid_staff = User.objects.filter(role__in=[Roles.LAD, Roles.LUS]).count()
    docs_range = (
        Document.objects.filter(uploaded_at__range=(start, end)).count()
        if Document
        else 0
    )
    tickets_open = (
        Ticket.objects.exclude(status__in=["resolved", "closed"]).count()
        if Ticket
        else 0
    )

    # simple chart: tickets opened per month
    labels = _last_12_month_labels()
    chart_tickets = _monthly_count_series(
        Ticket.objects.all() if Ticket else None, "created_at", labels
    )

    ctx = dict(
        range_label=label,
        start=start,
        end=end,
        eval_count=eval_count,
        supplier_count=supplier_count,
        lucid_staff=lucid_staff,
        docs_range=docs_range,
        tickets_open=tickets_open,
        chart_labels=labels,
        chart_tickets=chart_tickets,
    )
    return render(request, "dash/lus.html", ctx)


# ---------- EAD ----------


@login_required
@user_passes_test(is_EAD)
def ead_dashboard(request):
    start, end, label = _parse_range(request)
    ev = _require_evaluator(request.user)
    if not ev:
        messages.error(request, "No Evaluator associated with your account.")
        return redirect("accounts:logout")

    from tenants.models import Supplier

    try:
        from documents.models import Document
    except Exception:
        Document = None
    try:
        from activities.models import Activity
    except Exception:
        Activity = None
    from accounts.models import User

    try:
        from payments.models import PaymentRecord
    except Exception:
        PaymentRecord = None

    supplier_count = Supplier.objects.filter(evaluator=ev).count()
    evs_count = User.objects.filter(
        evaluator=ev, role=Roles.EVS, is_active=True
    ).count()
    docs_count = (
        Document.objects.filter(evaluator=ev, uploaded_at__range=(start, end)).count()
        if Document
        else 0
    )
    act_count = (
        Activity.objects.filter(evaluator=ev, started_at__range=(start, end)).count()
        if Activity
        else 0
    )

    if Document:
        today = timezone.localdate()
        week_end = today + timedelta(days=7)
        expiring_week = Document.objects.filter(
            evaluator=ev,
            is_active=True,
            expiry_date__range=(today, week_end),
        ).count()
    else:
        expiring_week = 0

    active_plan = (
        PaymentRecord.objects.filter(evaluator=ev, status="active")
        .order_by("-end_date")
        .first()
        if PaymentRecord
        else None
    )

    labels = _last_12_month_labels()
    chart_docs = _monthly_count_series(
        Document.objects.filter(evaluator=ev) if Document else None,
        "uploaded_at",
        labels,
    )
    chart_acts = _monthly_count_series(
        Activity.objects.filter(evaluator=ev) if Activity else None,
        "started_at",
        labels,
    )

    # plan limits (from your pricing tiers)
    plan_key = getattr(active_plan, "plan", None) if active_plan else None
    usage_limits = {"suppliers": None, "users": None}
    if plan_key == "essentials":
        usage_limits = {"suppliers": 100, "users": 10}
    elif plan_key == "professional":
        usage_limits = {"suppliers": 500, "users": None}
    elif plan_key == "enterprise":
        usage_limits = {"suppliers": None, "users": None}

    ctx = dict(
        range_label=label,
        start=start,
        end=end,
        evaluator=ev,
        active_plan=active_plan,
        supplier_count=supplier_count,
        evs_count=evs_count,
        docs_count=docs_count,
        act_count=act_count,
        expiring_week=expiring_week,
        chart_labels=labels,
        chart_docs=chart_docs,
        chart_acts=chart_acts,
        usage_limits=usage_limits,
    )
    return render(request, "dash/ead.html", ctx)


# ---------- EVS ----------


@login_required
@user_passes_test(is_EVS)
def evs_dashboard(request):
    start, end, label = _parse_range(request)
    ev = _require_evaluator(request.user)
    if not ev:
        messages.error(request, "No Evaluator associated with your account.")
        return redirect("accounts:logout")

    from tenants.models import Supplier

    try:
        from documents.models import Document
    except Exception:
        Document = None
    try:
        from activities.models import Activity
    except Exception:
        Activity = None
    from accounts.models import User

    try:
        from payments.models import PaymentRecord
    except Exception:
        PaymentRecord = None

    supplier_count = Supplier.objects.filter(evaluator=ev, is_active=True).count()
    evs_count = User.objects.filter(
        evaluator=ev, role=Roles.EVS, is_active=True
    ).count()
    act_count = (
        Activity.objects.filter(evaluator=ev, started_at__range=(start, end)).count()
        if Activity
        else 0
    )
    docs_count = (
        Document.objects.filter(evaluator=ev, uploaded_at__range=(start, end)).count()
        if Document
        else 0
    )

    labels = _last_12_month_labels()
    chart_docs = _monthly_count_series(
        Document.objects.filter(evaluator=ev) if Document else None,
        "uploaded_at",
        labels,
    )
    chart_acts = _monthly_count_series(
        Activity.objects.filter(evaluator=ev) if Activity else None,
        "started_at",
        labels,
    )

    active_plan = (
        PaymentRecord.objects.filter(evaluator=ev, status="active")
        .order_by("-end_date")
        .first()
        if PaymentRecord
        else None
    )

    ctx = {
        "range_label": label,
        "start": start,
        "end": end,
        "evaluator": ev,
        "supplier_count": supplier_count,
        "evs_count": evs_count,
        "act_count": act_count,
        "docs_count": docs_count,
        "chart_labels": labels,
        "chart_docs": chart_docs,
        "chart_acts": chart_acts,
        "active_plan": active_plan,
    }
    return render(request, "dash/evs.html", ctx)


# ---------- SUS ----------


@login_required
@user_passes_test(is_SUS)
def sus_dashboard(request):
    start, end, label = _parse_range(request)
    ev = _require_evaluator(request.user)
    sup = _require_supplier(request.user)
    if not (ev and sup):
        messages.error(request, "No Supplier/Evaluator associated with your account.")
        return redirect("accounts:logout")

    try:
        from activities.models import Activity, ActivityFile
    except Exception:
        Activity = ActivityFile = None
    try:
        from documents.models import Document
    except Exception:
        Document = None

    act_count = (
        Activity.objects.filter(
            evaluator=ev, supplier=sup, started_at__range=(start, end)
        ).count()
        if Activity
        else 0
    )
    files_count = (
        ActivityFile.objects.filter(
            activity__evaluator=ev, activity__supplier=sup
        ).count()
        if ActivityFile
        else 0
    )
    docs_count = (
        Document.objects.filter(
            evaluator=ev, supplier=sup, uploaded_at__range=(start, end)
        ).count()
        if Document
        else 0
    )

    # chart: activities per month for this supplier
    labels = _last_12_month_labels()
    chart_acts = _monthly_count_series(
        Activity.objects.filter(evaluator=ev, supplier=sup) if Activity else None,
        "started_at",
        labels,
    )

    ctx = dict(
        range_label=label,
        start=start,
        end=end,
        evaluator=ev,
        supplier=sup,
        act_count=act_count,
        files_count=files_count,
        docs_count=docs_count,
        chart_labels=labels,
        chart_acts=chart_acts,
    )
    return render(request, "dash/sus.html", ctx)
