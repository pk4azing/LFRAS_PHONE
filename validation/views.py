from django.contrib.auth.decorators import login_required, user_passes_test
from django.shortcuts import get_object_or_404, render, redirect
from django.contrib import messages
from accounts.models import Roles
from tenants.models import Supplier
from .models import SupplierValidationRule
from .forms import RuleForm


def is_EAD_or_EVS(u):
    return u.is_authenticated and u.role in (Roles.EAD, Roles.EVS)


@login_required
@user_passes_test(is_EAD_or_EVS)
def rules_list(request, supplier_id: int):
    sup = get_object_or_404(
        Supplier, pk=supplier_id, evaluator_id=request.user.evaluator_id
    )
    rules = sup.validation_rules.all()
    return render(
        request, "validation/rules_list.html", {"supplier": sup, "rules": rules}
    )


@login_required
@user_passes_test(is_EAD_or_EVS)
def rule_create(request, supplier_id: int):
    sup = get_object_or_404(
        Supplier, pk=supplier_id, evaluator_id=request.user.evaluator_id
    )
    if request.method == "POST":
        form = RuleForm(request.POST)
        if form.is_valid():
            r = form.save(commit=False)
            r.supplier = sup
            r.evaluator = sup.evaluator
            r.save()
            messages.success(request, "Validation rule created.")
            return redirect("validation:rules_list", supplier_id=sup.id)
    else:
        form = RuleForm()
    return render(request, "validation/rule_form.html", {"form": form, "supplier": sup})


@login_required
@user_passes_test(is_EAD_or_EVS)
def rule_edit(request, pk: int):
    r = get_object_or_404(
        SupplierValidationRule, pk=pk, evaluator_id=request.user.evaluator_id
    )
    if request.method == "POST":
        form = RuleForm(request.POST, instance=r)
        if form.is_valid():
            form.save()
            messages.success(request, "Validation rule updated.")
            return redirect("validation:rules_list", supplier_id=r.supplier_id)
    else:
        form = RuleForm(instance=r)
    return render(
        request, "validation/rule_form.html", {"form": form, "supplier": r.supplier}
    )


@login_required
@user_passes_test(is_EAD_or_EVS)
def rule_delete(request, pk: int):
    r = get_object_or_404(
        SupplierValidationRule, pk=pk, evaluator_id=request.user.evaluator_id
    )
    sup_id = r.supplier_id
    r.delete()
    messages.success(request, "Validation rule deleted.")
    return redirect("validation:rules_list", supplier_id=sup_id)
