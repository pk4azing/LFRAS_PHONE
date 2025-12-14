from datetime import datetime
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import HttpResponseForbidden
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.db.models import Q

from .models import PaymentRecord, PaymentTransaction, PLAN_DEFAULT_AMOUNTS
from .forms import PaymentRecordForm, PaymentTransactionForm
from .services import can_manage_payments, can_view_payments

from django.conf import settings

try:
    import requests  # for Slack webhook
except Exception:  # very defensive fallback
    requests = None


@login_required
def list_payments(request):
    if not can_view_payments(request.user):
        return HttpResponseForbidden("Not allowed.")
    qs = PaymentRecord.objects.select_related("evaluator").all()

    tab = request.GET.get("tab")

    # Filters: evaluator, plan, status, date range
    eval_id = request.GET.get("evaluator")
    plan = request.GET.get("plan")
    status = request.GET.get("status")
    start = request.GET.get("start")  # YYYY-MM-DD
    end = request.GET.get("end")  # YYYY-MM-DD
    q = request.GET.get("q")

    if eval_id:
        qs = qs.filter(evaluator_id=eval_id)
    if plan:
        qs = qs.filter(plan=plan)
    if status:
        qs = qs.filter(status=status)
    try:
        if start:
            start_dt = datetime.strptime(start, "%Y-%m-%d").date()
            qs = qs.filter(start_date__gte=start_dt)
        if end:
            end_dt = datetime.strptime(end, "%Y-%m-%d").date()
            qs = qs.filter(start_date__lte=end_dt)
    except Exception:
        pass
    if q:
        qs = qs.filter(
            Q(evaluator__name__icontains=q)
            | Q(subscription_id__icontains=q)
            | Q(notes__icontains=q)
        )

    # Sorting
    sort = request.GET.get("sort") or "-created_at"
    allowed = {
        "created_at",
        "-created_at",
        "amount_yearly",
        "-amount_yearly",
        "start_date",
        "-start_date",
    }
    if sort in allowed:
        qs = qs.order_by(sort)

    # Transactions tab support
    tx_qs = PaymentTransaction.objects.select_related("record", "record__evaluator").all() if tab == "tx" else PaymentTransaction.objects.none()

    if tab == "tx":
        # Reuse the same filter params: evaluator, status, date range, q, sort
        if eval_id:
            tx_qs = tx_qs.filter(record__evaluator_id=eval_id)
        if status:
            tx_qs = tx_qs.filter(status=status)
        try:
            if start:
                start_dt = datetime.strptime(start, "%Y-%m-%d").date()
                tx_qs = tx_qs.filter(created_at__date__gte=start_dt)
            if end:
                end_dt = datetime.strptime(end, "%Y-%m-%d").date()
                tx_qs = tx_qs.filter(created_at__date__lte=end_dt)
        except Exception:
            pass
        if q:
            tx_qs = tx_qs.filter(
                Q(record__evaluator__name__icontains=q)
                | Q(reference__icontains=q)
                | Q(method__icontains=q)
                | Q(notes__icontains=q)
            )
        tx_sort = request.GET.get("sort") or "-created_at"
        tx_allowed = {"created_at", "-created_at", "amount", "-amount"}
        if tx_sort in tx_allowed:
            tx_qs = tx_qs.order_by(tx_sort)
        else:
            tx_qs = tx_qs.order_by("-created_at")

    # For filters UI
    from tenants.models import Evaluator

    evals = Evaluator.objects.order_by("name")

    return render(
        request,
        "payments/list.html",
        {
            "records": qs,
            "evals": evals,
            "today": timezone.localdate(),
            "params": request.GET,
            "transactions": tx_qs,
            "tab": tab,
        },
    )


@login_required
def create_record(request):
    if not can_manage_payments(request.user):
        return HttpResponseForbidden("Not allowed.")
    initial = {}
    if request.method == "POST":
        form = PaymentRecordForm(request.POST)
        if form.is_valid():
            rec = form.save(commit=False)
            if not rec.amount_yearly and rec.plan in PLAN_DEFAULT_AMOUNTS:
                rec.amount_yearly = PLAN_DEFAULT_AMOUNTS[rec.plan]
            rec.created_by = request.user
            rec.ensure_end_date_default()
            rec.save()

            messages.success(request, "Payment record created.")
            # Optional: notify EADs of the evaluator
            try:
                from notifications.services import notify
                from notifications.models import Level

                for u in rec.evaluator.users.filter(is_active=True, role="EAD"):
                    notify(
                        u,
                        f"Subscription created — {rec.get_plan_display()}",
                        body=f"Valid from {rec.start_date} to {rec.end_date}",
                        level=Level.INFO,
                        link_url="/router/ead/",
                        email=True,
                    )
            except Exception:
                pass

            return redirect("payments:list")
    else:
        form = PaymentRecordForm(initial=initial)
    return render(request, "payments/create_record.html", {"form": form})


@login_required
def create_transaction(request):
    if not can_manage_payments(request.user):
        return HttpResponseForbidden("Not allowed.")
    if request.method == "POST":
        form = PaymentTransactionForm(request.POST)
        if form.is_valid():
            trx = form.save(commit=False)
            trx.created_by = request.user
            trx.save()

            # Slack notification (optional via Incoming Webhook)
            try:
                webhook = getattr(settings, "SLACK_WEBHOOK_URL", None)
                if webhook and requests is not None:
                    rec = trx.record
                    who = getattr(request.user, "email", str(request.user))
                    amt = f"{trx.amount:.2f} {getattr(trx, 'currency', 'USD').upper()}"
                    status = getattr(trx, "status", getattr(trx, "state", "recorded"))
                    tx_ref = getattr(trx, "reference", "—")
                    eval_name = getattr(rec.evaluator, "name", "(evaluator)")
                    detail_url = f"/payments/{rec.pk}/?tab=tx"
                    text = (
                        f":money_with_wings: *New Transaction*\n"
                        f"Evaluator: *{eval_name}*\n"
                        f"Amount: *{amt}*\n"
                        f"Status: *{status}*\n"
                        f"Txn ID: `{tx_ref}`\n"
                        f"By: {who}\n"
                        f"<{detail_url}|View in dashboard>"
                    )
                    try:
                        requests.post(webhook, json={"text": text}, timeout=5)
                    except Exception:
                        pass
            except Exception:
                pass

            # If payment covers the yearly amount, activate the record
            rec = trx.record
            if rec.status in ("pending", "cancelled", "expired"):
                # naïve rule: if trx.amount >= rec.amount_yearly, set active and reset dates if missing
                if trx.amount >= rec.amount_yearly:
                    rec.status = "active"
                    if not rec.start_date:
                        rec.start_date = timezone.localdate()
                    if not rec.end_date:
                        rec.ensure_end_date_default()
                    rec.save(update_fields=["status", "start_date", "end_date"])
            messages.success(request, "Transaction saved.")
            return redirect("payments:list")
    else:
        form = PaymentTransactionForm()
    return render(request, "payments/create_transaction.html", {"form": form})


@login_required
def record_detail(request, pk: int):
    if not can_view_payments(request.user):
        return HttpResponseForbidden("Not allowed.")
    rec = get_object_or_404(PaymentRecord.objects.select_related("evaluator"), pk=pk)
    transactions = rec.transactions.order_by("-created_at")
    return render(
        request,
        "payments/detail.html",
        {
            "rec": rec,
            "payment": rec,              # alias for template convenience
            "trxs": transactions,        # legacy name
            "transactions": transactions,
            "params": request.GET,
        },
    )
