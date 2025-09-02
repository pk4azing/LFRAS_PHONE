from django import forms
from .models import PaymentRecord, PaymentTransaction, PLAN_DEFAULT_AMOUNTS


class PaymentRecordForm(forms.ModelForm):
    class Meta:
        model = PaymentRecord
        fields = [
            "evaluator",
            "plan",
            "amount_yearly",
            "currency",
            "status",
            "start_date",
            "end_date",
            "subscription_id",
            "notes",
        ]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # default amount when plan chosen (JS can also assist on template)
        if not self.instance.pk:
            plan = self.initial.get("plan") or self.data.get("plan")
            if plan in PLAN_DEFAULT_AMOUNTS and not (
                self.data.get("amount_yearly") or self.initial.get("amount_yearly")
            ):
                self.fields["amount_yearly"].initial = PLAN_DEFAULT_AMOUNTS[plan]

    def clean(self):
        cleaned = super().clean()
        start = cleaned.get("start_date")
        end = cleaned.get("end_date")
        if start and end and end <= start:
            raise forms.ValidationError("End date must be after start date.")
        return cleaned


class PaymentTransactionForm(forms.ModelForm):
    class Meta:
        model = PaymentTransaction
        fields = [
            "record",
            "paid_on",
            "amount",
            "currency",
            "method",
            "external_id",
            "notes",
        ]
