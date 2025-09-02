# preferences/forms.py
from django import forms
from .models import SiteSetting
from tenants.models import Evaluator, Supplier


# ----- LAD/LUS (site) -----
class SiteSettingsForm(forms.Form):
    email_from = forms.EmailField(required=False, label="Default From Email")
    support_email = forms.EmailField(required=False, label="Support Email")
    s3_base_prefix = forms.CharField(
        required=False, max_length=200, label="S3 Base Prefix (e.g., lucid/)"
    )
    expiry_schedule = forms.CharField(
        required=False, label="Expiry reminder days (CSV)", help_text="e.g., 30,14,7,1"
    )

    def load_from_store(self):
        def get(k, default):
            try:
                s = SiteSetting.objects.get(key=k)
                return s.value.get("v", default)
            except SiteSetting.DoesNotExist:
                return default

        self.initial.update(
            {
                "email_from": get("email_from", ""),
                "support_email": get("support_email", ""),
                "s3_base_prefix": get("s3_base_prefix", "lucid/"),
                "expiry_schedule": ",".join(
                    str(x) for x in get("expiry_schedule_days", [30, 14, 7, 1])
                ),
            }
        )

    def save_to_store(self):
        def put(k, v):
            SiteSetting.objects.update_or_create(key=k, defaults={"value": {"v": v}})

        data = self.cleaned_data
        put("email_from", data["email_from"])
        put("support_email", data["support_email"])
        put("s3_base_prefix", data["s3_base_prefix"])
        # normalize schedule
        sched = []
        for token in (data.get("expiry_schedule") or "").split(","):
            token = token.strip()
            if token.isdigit():
                sched.append(int(token))
        sched = sorted(set(sched), reverse=False) or [30, 14, 7, 1]
        put("expiry_schedule_days", sched)


# ----- EAD/EVS (evaluator) -----
class EvaluatorSettingsForm(forms.ModelForm):
    # optional validation defaults toggles for phase‑1
    require_known_extensions = forms.BooleanField(
        required=False, initial=True, label="Disallow unknown file types by default"
    )

    class Meta:
        model = Evaluator
        fields = [
            "name",
            "website",
            "address_line1",
            "address_line2",
            "city",
            "state",
            "postal_code",
        ]


# ----- SUS (supplier) -----
class SupplierSettingsForm(forms.ModelForm):
    class Meta:
        model = Supplier
        fields = [
            "name",
            "phone",
            "address_line1",
            "address_line2",
            "city",
            "state",
            "postal_code",
        ]
