from __future__ import annotations

from django import forms

from accounts.models import Roles, User
from tenants.models import Evaluator, Supplier


class ActivityStartForm(forms.Form):
    """
    Form used on Activities → Start page.
    We pass the logged-in user so we can scope available Evaluators/Suppliers.
    """
    evaluator = forms.ModelChoiceField(
        queryset=Evaluator.objects.none(), label="Evaluator"
    )
    supplier = forms.ModelChoiceField(
        queryset=Supplier.objects.none(), label="Supplier"
    )

    def __init__(self, *args, user: User | None = None, **kwargs):
        super().__init__(*args, **kwargs)
        self.user = user

        # Defaults (for LAD/LUS etc.)
        self.fields["evaluator"].queryset = Evaluator.objects.all().order_by("name")
        self.fields["supplier"].queryset = Supplier.objects.all().order_by("name")

        # Supplier users can only start for their own supplier; evaluator may be
        # restricted to the supplier's assigned evaluator if present.
        if user is not None and user.role == Roles.SUS and user.supplier_id:
            self.fields["supplier"].queryset = Supplier.objects.filter(id=user.supplier_id)
            try:
                sup = Supplier.objects.get(id=user.supplier_id)
                if getattr(sup, "evaluator_id", None):
                    self.fields["evaluator"].queryset = Evaluator.objects.filter(id=sup.evaluator_id)
            except Supplier.DoesNotExist:
                self.fields["evaluator"].queryset = Evaluator.objects.none()

        # Simple styling so it matches your theme
        for f in self.fields.values():
            css = f.widget.attrs.get("class", "")
            f.widget.attrs["class"] = (css + " form-control").strip()


class ActivityFileUploadForm(forms.Form):
    # keep here so the import in views works; adjust if you already have this elsewhere
    file = forms.FileField()