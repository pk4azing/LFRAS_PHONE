from django import forms
from django.core.exceptions import ValidationError
from accounts.models import User, Roles
from .models import Evaluator, Supplier, PaymentTransaction
from .policies import get_policy


class PaymentForm(forms.ModelForm):
    class Meta:
        model = PaymentTransaction
        fields = ["payment_id", "amount_cents", "currency", "paid_at", "notes"]


class CreateEvaluatorForm(forms.ModelForm):
    class Meta:
        model = Evaluator
        fields = [
            "name",
            "address",
            "city",
            "state",
            "postal_code",
            "email_domain",
            "website",
            "subdomain",
            "plan",
            "payment",
            "poc_name",
            "poc_email",
        ]

    def clean_poc_email(self):
        email = self.cleaned_data["poc_email"].lower().strip()
        if User.objects.filter(email=email).exists():
            raise ValidationError("A user with this email already exists.")
        domain = self.cleaned_data.get("email_domain", "").lower().strip()
        if domain and not email.endswith("@" + domain):
            raise ValidationError("POC email must match Evaluator email domain.")
        return email


class CreateSupplierForm(forms.ModelForm):
    class Meta:
        model = Supplier
        fields = [
            "evaluator",
            "name",
            "address",
            "city",
            "state",
            "postal_code",
            "phone",
            "primary_email",
        ]

    def clean(self):
        data = super().clean()
        evaluator = data.get("evaluator")
        if not evaluator:
            return data
        policy = get_policy(evaluator.plan)
        current = evaluator.suppliers.filter(is_active=True).count()
        cap = policy.max_vendors_customers
        if cap is not None and current >= cap:
            raise ValidationError(
                f"Plan limit reached: {cap} Suppliers (vendors/customers) for {policy.name}."
            )
        return data

    def clean_primary_email(self):
        email = (self.cleaned_data.get("primary_email") or "").lower().strip()
        if User.objects.filter(email=email).exists():
            raise ValidationError("A user with this email already exists.")
        return email


class CreateEvaluatorUserForm(forms.Form):
    ROLE_CHOICES = [(Roles.EAD, "Evaluator Admin"), (Roles.EVS, "Evaluator Staff")]
    evaluator = forms.ModelChoiceField(
        queryset=Evaluator.objects.filter(is_active=True)
    )
    role = forms.ChoiceField(choices=ROLE_CHOICES)
    first_name = forms.CharField(max_length=120, required=False)
    last_name = forms.CharField(max_length=120, required=False)
    designation = forms.CharField(max_length=120, required=False)
    phone = forms.CharField(max_length=40, required=False)
    email = forms.EmailField()

    def clean(self):
        data = super().clean()
        evaluator = data.get("evaluator")
        email = (data.get("email") or "").lower().strip()
        role = data.get("role")
        if not evaluator or not email or not role:
            return data
        if User.objects.filter(email=email).exists():
            raise ValidationError("A user with this email already exists.")

        # Email domain enforcement for EAD/EVS
        domain = evaluator.email_domain.lower().strip()
        if domain and not email.endswith("@" + domain):
            raise ValidationError("Email must match evaluator email domain.")

        # Cap internal users (EAD + EVS) by plan
        policy = get_policy(evaluator.plan)
        cap = policy.max_internal_users
        if cap is not None:
            current_internal = evaluator.users.filter(
                role__in=[Roles.EAD, Roles.EVS], is_active=True
            ).count()
            if current_internal >= cap:
                raise ValidationError(
                    f"Plan limit reached: {cap} internal users (EAD/EVS) for {policy.name}."
                )

        return data
