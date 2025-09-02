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


@login_required
def list_payments(request):
    if not can_view_payments(request.user):
        return HttpResponseForbidden("Not allowed.")
    qs = PaymentRecord.objects.select_related("evaluator").all()

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
    trxs = rec.transactions.all()
    return render(request, "payments/detail.html", {"rec": rec, "trxs": trxs})
