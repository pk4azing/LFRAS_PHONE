# preferences/views.py
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.shortcuts import redirect, render
from accounts.models import Roles
from .forms import SiteSettingsForm, EvaluatorSettingsForm, SupplierSettingsForm


@login_required
def index(request):
    u = request.user
    role = u.role

    # LAD/LUS: site settings
    if role in (Roles.LAD, Roles.LUS):
        form = SiteSettingsForm(request.POST or None)
        if request.method != "POST":
            form.load_from_store()
        if request.method == "POST" and form.is_valid():
            form.save_to_store()
            messages.success(request, "Site settings saved.")
            return redirect("preferences:index")
        return render(
            request,
            "settings/index.html",
            {"scope": "site", "title": "Lucid Site Settings", "form": form},
        )

    # EAD/EVS: evaluator settings (bound to user.evaluator)
    if role in (Roles.EAD, Roles.EVS):
        if not u.evaluator:
            messages.error(request, "No evaluator linked to your account.")
            return redirect("router:index")
        form = EvaluatorSettingsForm(request.POST or None, instance=u.evaluator)
        if request.method == "POST" and form.is_valid():
            form.save()
            messages.success(request, "Evaluator settings saved.")
            return redirect("preferences:index")
        return render(
            request,
            "settings/index.html",
            {"scope": "evaluator", "title": "Evaluator Settings", "form": form},
        )

    # SUS: supplier settings (bound to user.supplier)
    if role == Roles.SUS:
        if not u.supplier:
            messages.error(request, "No supplier linked to your account.")
            return redirect("router:index")
        form = SupplierSettingsForm(request.POST or None, instance=u.supplier)
        if request.method == "POST" and form.is_valid():
            form.save()
            messages.success(request, "Supplier settings saved.")
            return redirect("preferences:index")
        return render(
            request,
            "settings/index.html",
            {"scope": "supplier", "title": "Supplier Settings", "form": form},
        )

    # default
    messages.error(request, "No settings available for your role.")
    return redirect("router:index")
