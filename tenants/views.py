from django.contrib.auth.decorators import user_passes_test
from django.core.paginator import Paginator
from .forms import (
    PaymentForm,
    CreateEvaluatorForm,
    CreateSupplierForm,
    CreateEvaluatorUserForm,
    SupplierForm,
)
from .models import Evaluator
from .services import (
    create_ead_for_evaluator,
    create_sus_for_supplier,
    create_evaluator_user,
)
from django.db.models import Q
from accounts.utils import invite_user
from auditlog.services import log_event
from notifications.services import notify
from notifications.models import Level

import csv, io
from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, render, redirect
from django.contrib import messages
from django.db import transaction

from accounts.models import Roles
from .models import Supplier, Evaluator
from validation.models import (
    SupplierValidationRule,
)


def _can_edit_supplier(user, supplier: Supplier) -> bool:
    # Allow Lucid admins (LAD/LUS) or the Evaluator staff owning this supplier.
    if user.role in ("LAD", "LUS"):
        return False
    # Example: if your Supplier has a foreign key to evaluator and your
    # EVS/EAD should edit only their suppliers, scope here:
    if user.role in ("EVS", "EAD") and supplier.evaluator_id == getattr(user, "evaluator_id", None):
        return True
    return False

def _ensure_ead_scope(user, supplier: Supplier):
    # LAD/LUS always allowed; EAD/EVS limited to own evaluator; SUS never allowed
    if user.role in (Roles.LAD, Roles.LUS):
        return True
    if user.role in (Roles.EAD, Roles.EVS):
        return supplier.evaluator_id == user.evaluator_id
    return False


def is_LAD(user):
    return user.is_authenticated and user.role == Roles.LAD


def is_EAD(user):
    return user.is_authenticated and user.role == Roles.EAD


def is_LAD_or_LUS(user):
    return getattr(user, "role", None) in ("LAD", "LUS")


# ---- LAD: Create Payment then Evaluator (auto EAD POC user) ----
@login_required
@user_passes_test(is_LAD)
def new_payment(request):
    form = PaymentForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        pay = form.save()
        log_event(
            request=request,
            actor=request.user,
            verb="created",
            action="payment.create",
            target=pay,
        )
        messages.success(request, f"Payment saved: {pay.payment_id}")
        return redirect("tenants:new_evaluator")
    return render(request, "tenants/new_payment.html", {"form": form})


@login_required
@user_passes_test(is_LAD)
def new_evaluator(request):
    form = CreateEvaluatorForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        evaluator = form.save()
        ead_user = create_ead_for_evaluator(evaluator)
        log_event(
            request=request,
            actor=request.user,
            verb="created",
            action="evaluator.create",
            target=evaluator,
            evaluator_id=evaluator.id,
            metadata={"poc_email": evaluator.poc_email, "plan": evaluator.plan},
        )
        notify(
            ead_user,
            title="Your Evaluator admin account is ready",
            body=f"Evaluator: {evaluator.name}. Please verify email and change your password.",
            level=Level.SUCCESS,
            link_url="/auth/login/",
        )
        messages.success(
            request, f"Evaluator '{evaluator.name}' created. POC user: {ead_user.email}"
        )
        return redirect("router:lad")
    return render(request, "tenants/new_evaulator.html", {"form": form})


# ---- EAD: Create Supplier (auto SUS) ----
@login_required
@user_passes_test(is_EAD)
def new_supplier(request):
    form = CreateSupplierForm(
        request.POST or None, initial={"evaluator": request.user.evaluator}
    )
    form.fields["evaluator"].queryset = Evaluator.objects.filter(
        id=request.user.evaluator_id
    )
    if request.method == "POST" and form.is_valid():
        supplier = form.save()
        sus = create_sus_for_supplier(supplier)
        log_event(
            request=request,
            actor=request.user,
            verb="created",
            action="supplier.create",
            target=supplier,
            evaluator_id=supplier.evaluator_id,
            supplier_id=supplier.id,
            metadata={"sus_email": sus.email},
        )
        u, temp, created = invite_user(
            email=sus.email,
            role=Roles.SUS,
            supplier=supplier,
            evaluator=supplier.evaluator,
        )
        notify(
            sus,
            title="Your Supplier account is ready",
            body=f"Email: {u.email}\nTemporary password: {temp}\nPlease log in and change your password.",
            level=Level.SUCCESS,
            link_url="/auth/login/",
        )
        messages.success(
            request, f"Supplier '{supplier.name}' created. SUS: {sus.email}"
        )
        return redirect("router:ead")
    return render(request, "tenants/new_supplier.html", {"form": form})


# ---- EAD: Create EAD/EVS users ----
@login_required
@user_passes_test(is_EAD)
def new_evaluator_user(request):
    form = CreateEvaluatorUserForm(
        request.POST or None, initial={"evaluator": request.user.evaluator}
    )
    form.fields["evaluator"].queryset = Evaluator.objects.filter(
        id=request.user.evaluator_id
    )
    if request.method == "POST" and form.is_valid():
        evaluator = form.cleaned_data["evaluator"]
        email = form.cleaned_data["email"].lower().strip()
        role = form.cleaned_data["role"]
        profile = {
            "first_name": form.cleaned_data.get("first_name", ""),
            "last_name": form.cleaned_data.get("last_name", ""),
        }
        user = create_evaluator_user(evaluator, email, role, **profile)
        log_event(
            request=request,
            actor=request.user,
            verb="created",
            action="user.create",
            target=user,
            evaluator_id=evaluator.id,
            metadata={"role": role},
        )
        notify(
            user,
            title="Your Evaluator account is ready",
            body=f"Role: {role}, Evaluator: {evaluator.name}. Please verify email and change your password.",
            level=Level.SUCCESS,
            link_url="/auth/login/",
        )
        messages.success(request, f"User {user.email} created as {role}.")
        return redirect("router:ead_dashboard")
    return render(request, "tenants/new_evaluator_user.html", {"form": form})


@login_required
def supplier_detail(request, pk: int):
    supplier = get_object_or_404(Supplier.objects.select_related("evaluator"), pk=pk)
    if not _ensure_ead_scope(request.user, supplier):
        messages.error(request, "Not allowed.")
        return redirect("router:index")

    rules = SupplierValidationRule.objects.filter(supplier_id=supplier.id).order_by(
        "id"
    )
    return render(
        request, "tenants/supplier_detail.html", {"supplier": supplier, "rules": rules}
    )


@login_required
def rules_upload(request, pk: int):
    supplier = get_object_or_404(Supplier.objects.select_related("evaluator"), pk=pk)
    if not _ensure_ead_scope(request.user, supplier):
        messages.error(request, "Not allowed.")
        return redirect("router:index")

    if request.method != "POST":
        messages.error(request, "Upload a CSV file.")
        return redirect("tenants:supplier_detail", pk=supplier.id)

    f = request.FILES.get("file")
    if not f:
        messages.error(request, "No file selected.")
        return redirect("tenants:supplier_detail", pk=supplier.id)

    # Expect CSV header: expected_name,required,keywords,extensions
    try:
        txt = io.TextIOWrapper(f.file, encoding="utf-8", errors="ignore")
        reader = csv.DictReader(txt)
    except Exception:
        messages.error(request, "Invalid CSV file.")
    else:
        rows = []
        line_no = 1
        for row in reader:
            line_no += 1
            name = (row.get("expected_name") or row.get("name") or "").strip()
            required = str(row.get("required") or "").strip().lower() in (
                "1",
                "true",
                "yes",
                "y",
            )
            keywords = (row.get("keywords") or "").strip()
            extensions = (
                row.get("extensions") or row.get("allowed_extensions") or ""
            ).strip()
            if not name:
                messages.error(request, f"Row {line_no}: 'expected_name' is required.")
                return redirect("tenants:supplier_detail", pk=supplier.id)
            rows.append(
                dict(
                    expected_name=name,
                    required=required,
                    keywords=keywords,
                    extensions=extensions,
                )
            )

        with transaction.atomic():
            SupplierValidationRule.objects.filter(supplier_id=supplier.id).delete()
            objs = [
                SupplierValidationRule(
                    supplier_id=supplier.id,
                    expected_name=r["expected_name"],
                    required=r["required"],
                    keywords=r["keywords"],
                    extensions=r["extensions"],
                )
                for r in rows
            ]
            SupplierValidationRule.objects.bulk_create(objs)

        messages.success(request, f"Replaced {len(rows)} validation rule(s).")

    return redirect("tenants:supplier_detail", pk=supplier.id)


@login_required
@user_passes_test(is_LAD_or_LUS)  # adjust if EAD should also view
def evaluators_list(request):
    """List Evaluators with search + pagination."""
    qs = Evaluator.objects.all().order_by("-created_at")

    q = request.GET.get("q", "").strip()
    if q:
        qs = qs.filter(
            Q(name__icontains=q)
            | Q(poc_name__icontains=q)
            | Q(poc_email__icontains=q)
            | Q(website__icontains=q)
            | Q(city__icontains=q)
            | Q(state__icontains=q)
            | Q(subdomain__icontains=q)
        )

    paginator = Paginator(qs, 20)
    page_number = request.GET.get("page")
    page_obj = paginator.get_page(page_number)

    ctx = {
        "page_obj": page_obj,
        "q": q,
        "total": qs.count(),
    }
    return render(request, "tenants/evaluators_list.html", ctx)


@login_required
def suppliers_list(request):
    """
    List Suppliers with search/pagination.
    LAD/LUS: see all suppliers.
    EAD: only suppliers under their evaluator.
    """
    qs = Supplier.objects.select_related("evaluator").all().order_by("-id")

    # Scope for EAD
    if getattr(request.user, "role", None) == Roles.EAD:
        qs = qs.filter(evaluator_id=request.user.evaluator_id)

    # Simple search
    q = request.GET.get("q", "").strip()
    if q:
        qs = qs.filter(
            Q(name__icontains=q) | Q(evaluator__name__icontains=q)
        )

    paginator = Paginator(qs, 20)
    page_number = request.GET.get("page")
    page_obj = paginator.get_page(page_number)

    ctx = {
        "page_obj": page_obj,
        "q": q,
        "total": qs.count(),
    }
    return render(request, "tenants/suppliers_list.html", ctx)


@login_required
def supplier_edit(request, pk: int):
    supplier = get_object_or_404(Supplier, pk=pk)
    if not _can_edit_supplier(request.user, supplier):
        messages.error(request, "You don’t have permission to edit this supplier.")
        return redirect("tenants:suppliers_list")

    if request.method == "POST":
        form = SupplierForm(request.POST, instance=supplier)
        if form.is_valid():
            form.save()
            messages.success(request, "Supplier details updated.")
            # Go to a detail page if you have it; otherwise back to list
            return redirect("tenants:suppliers_detail", pk=supplier.pk) if \
                "tenants:suppliers_detail" in request.resolver_match.namespace or True else \
                redirect("tenants:suppliers_list")
    else:
        form = SupplierForm(instance=supplier)

    ctx = {"form": form, "supplier": supplier}
    return render(request, "tenants/supplier_edit.html", ctx)