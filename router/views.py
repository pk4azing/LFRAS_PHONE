from __future__ import annotations
from datetime import timedelta, date
from django.db import models

from django.contrib import messages
from django.contrib.auth.decorators import login_required, user_passes_test
from django.db.models import Count, Sum
from django.db.models.functions import TruncDate
from django.db.models.functions import TruncMonth
from django.shortcuts import redirect, render
from django.utils import timezone

from accounts.models import Roles
from documents.models import Document


# ---------- helpers ----------


def _parse_range(request):
    """Parse ?range=day|week|month or 7d|30d|90d (default month=30d). Returns (start, end, label)."""
    end = timezone.now()
    rng = (request.GET.get("range") or "").lower()
    if rng in {"day", "1d"}:
        days, label = 1, "last 1 day"
    elif rng in {"week", "7d"}:
        days, label = 7, "last 7 days"
    elif rng in {"90d"}:
        days, label = 90, "last 90 days"
    else:  # month or default
        days, label = 30, "last 30 days"
    start = end - timedelta(days=days)
    return start, end, label


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
    try:
        from payments.models import PaymentRecord
    except Exception:
        PaymentRecord = None

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

    # ----- RANGE-AWARE CHARTS (Evaluators / Payments count / Payments amount) -----
    # Map range to granularity and window
    rng = (request.GET.get("range") or "week").lower()
    if rng not in {"day", "week", "month", "7d", "30d", "90d", "1d"}:
        rng = "week"
    # Normalize aliases
    if rng == "7d":
        rng = "week"
    if rng in {"30d", "90d", "1d"}:  # collapse 30d->month (approx), 1d->day, keep 90d as 90d window with day granularity
        rng = {"30d": "month", "90d": "month", "1d": "day"}[rng]

    now = timezone.localtime()
    start_dt = start  # from _parse_range
    end_dt = end
    gran = "hour" if rng == "day" else "day"

    from collections import OrderedDict
    from datetime import datetime as _dt, date as _date

    def bucket_keys():
        keys = []
        if gran == "hour":
            cur = start_dt.replace(minute=0, second=0, microsecond=0)
            till = end_dt.replace(minute=0, second=0, microsecond=0)
            while cur <= till:
                keys.append(cur)
                cur += timedelta(hours=1)
        else:
            cur = start_dt.date()
            till = end_dt.date()
            while cur <= till:
                # store as datetime for consistent keys
                keys.append(_dt.combine(cur, _dt.min.time(), tzinfo=now.tzinfo))
                cur += timedelta(days=1)
        return keys

    def label_for(dt):
        return dt.strftime("%b %d, %H:00") if gran == "hour" else dt.strftime("%b %d")

    def to_bucket(v):
        d = v
        if isinstance(d, str):
            for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S.%f%z", "%Y-%m-%dT%H:%M:%S%z", "%Y-%m-%d"):
                try:
                    d = _dt.strptime(d[:len(fmt)], fmt)
                    break
                except Exception:
                    continue
        if isinstance(d, _date) and not isinstance(d, _dt):
            d = _dt.combine(d, _dt.min.time(), tzinfo=now.tzinfo)
        if not isinstance(d, _dt):
            return None
        return d.replace(minute=0, second=0, microsecond=0, tzinfo=now.tzinfo) if gran == "hour" else _dt.combine(d.date(), _dt.min.time(), tzinfo=now.tzinfo)

    keys = bucket_keys()

    # Evaluators Created
    eval_series = OrderedDict((k, 0) for k in keys)
    for r in (
        Evaluator.objects
        .filter(created_at__gte=start_dt, created_at__lte=end_dt)
        .values("created_at")
    ):
        b = to_bucket(r["created_at"])
        if b in eval_series:
            eval_series[b] += 1
    eval_labels = [label_for(k) for k in eval_series.keys()]
    eval_data = list(eval_series.values())

    # Payments (count & amount) — detect model/fields
    try:
        from payments.models import PaymentTransaction
    except Exception:
        PaymentTransaction = None
    try:
        from payments.models import PaymentRecord
    except Exception:
        PaymentRecord = None

    def detect_fields(model):
        if not model:
            return None, None
        names = {f.name for f in model._meta.get_fields()}
        date_f = "paid_on" if "paid_on" in names else ("created_at" if "created_at" in names else None)
        amt_f = "amount" if "amount" in names else ("total_amount" if "total_amount" in names else None)
        return date_f, amt_f

    pay_model = PaymentTransaction or PaymentRecord
    pay_date_field, pay_amount_field = detect_fields(pay_model)

    pay_count_series = OrderedDict((k, 0) for k in keys)
    pay_amount_series = OrderedDict((k, 0.0) for k in keys)

    if pay_model and pay_date_field:
        rows_qs = pay_model.objects.filter(**{f"{pay_date_field}__gte": start_dt, f"{pay_date_field}__lte": end_dt})
        if pay_amount_field:
            rows_qs = rows_qs.values(pay_date_field, pay_amount_field)
        else:
            rows_qs = rows_qs.values(pay_date_field)
        for r in rows_qs:
            b = to_bucket(r.get(pay_date_field))
            if b in pay_count_series:
                pay_count_series[b] += 1
                if pay_amount_field:
                    amt = r.get(pay_amount_field) or 0
                    try:
                        pay_amount_series[b] += float(amt)
                    except Exception:
                        from decimal import Decimal
                        try:
                            pay_amount_series[b] += float(Decimal(amt))
                        except Exception:
                            pass

    pay_count_labels = [label_for(k) for k in pay_count_series.keys()]
    pay_count_data = list(pay_count_series.values())
    pay_amount_labels = [label_for(k) for k in pay_amount_series.keys()]
    pay_amount_data = list(pay_amount_series.values())

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
        range=rng,
        eval_labels=eval_labels,
        eval_data=eval_data,
        pay_count_labels=pay_count_labels,
        pay_count_data=pay_count_data,
        pay_amount_labels=pay_amount_labels,
        pay_amount_data=pay_amount_data,
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
            expires_at__date__range=(today, week_end),
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

    # Usage tracking: how many suppliers, users, documents, and activities are used
    usage_used = {
        "suppliers": supplier_count,
        "users": evs_count,
        "documents": docs_count,
        "activities": act_count,
    }
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
        usage_used=usage_used,
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

    # Activities in selected range for this supplier/evaluator
    act_count = (
        Activity.objects.filter(
            evaluator_id=ev.id,
            supplier_id=sup.id,
            started_at__range=(start, end),
        ).count()
        if Activity
        else 0
    )

    # Files across activities for this supplier/evaluator, filtered by the file's uploaded timestamp
    failed_statuses = []
    if ActivityFile:
        # Build failure set dynamically to avoid attribute errors
        try:
            failed_statuses = [ActivityFile.status.VALID_FAILED]  # if inner enum exists
        except Exception:
            from activities.models import FileStatus as _FS  # fallback if status is module-level
            failed_statuses = [_FS.VALID_FAILED]
        # Add UPLOAD_FAILED if present
        try:
            # handle both enum-on-model and module-level constant
            failed_statuses.append(ActivityFile.FileStatus.UPLOAD_FAILED)
        except Exception:
            try:
                from activities.models import FileStatus as _FS
                if hasattr(_FS, "UPLOAD_FAILED"):
                    failed_statuses.append(_FS.UPLOAD_FAILED)
            except Exception:
                pass

    files_valid_ok = (
        ActivityFile.objects.filter(
            activity__evaluator_id=ev.id,
            activity__supplier_id=sup.id,
            status=getattr(ActivityFile.status, "VALID_OK", "VALID_OK"),
            uploaded_at__range=(start, end),
        ).count()
        if ActivityFile
        else 0
    )

    files_failed = (
        ActivityFile.objects.filter(
            activity__evaluator_id=ev.id,
            activity__supplier_id=sup.id,
            status__in=failed_statuses,
            uploaded_at__range=(start, end),
        ).count()
        if ActivityFile and failed_statuses
        else 0
    )

    # Total documents uploaded by this supplier in range (optional card)
    docs_count = (
        Document.objects.filter(
            evaluator_id=ev.id,
            supplier_id=sup.id,
            uploaded_at__range=(start, end),
        ).count()
        if Document
        else 0
    )

    # For completeness, also compute total files regardless of range (useful for secondary info)
    files_count = (
        ActivityFile.objects.filter(
            activity__evaluator_id=ev.id, activity__supplier_id=sup.id
        ).count()
        if ActivityFile
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
        docs_count=docs_count,
        chart_labels=labels,
        chart_acts=chart_acts,
        files_ok=files_valid_ok,
        files_failed=files_failed,
        files_count=files_count,
    )
    return render(request, "dash/sus.html", ctx)
