from django import forms


class ActivityFileUploadForm(forms.Form):
    file = forms.FileField()


class ActivityStartForm(forms.Form):
    """Supplier (SUS) starts an activity; if the user is SUS we can infer evaluator/supplier in the view."""

    evaluator = forms.ModelChoiceField(queryset=None, required=True)
    supplier = forms.ModelChoiceField(queryset=None, required=True)

    def __init__(self, *args, **kwargs):
        user = kwargs.pop("user", None)
        super().__init__(*args, **kwargs)

        # Lazy imports to avoid circulars
        from tenants.models import Evaluator, Supplier

        self.fields["evaluator"].queryset = Evaluator.objects.all()
        self.fields["supplier"].queryset = Supplier.objects.all()

        # If SUS, preselect & lock choices to their own evaluator/supplier
        if user and getattr(user, "role", None) == getattr(
            __import__("accounts").accounts.models.Roles, "SUS"
        ):
            ev = getattr(user, "evaluator_id", None)
            sp = getattr(user, "supplier_id", None)
            if ev:
                self.fields["evaluator"].queryset = Evaluator.objects.filter(id=ev)
            if sp:
                self.fields["supplier"].queryset = Supplier.objects.filter(id=sp)
