from django import forms
from .models import SupplierValidationRule


class _CommaListField(forms.CharField):
    """Accepts comma/space/newline separated tokens and returns a list of strings."""

    def to_python(self, value):
        if not value:
            return []
        # accept comma or newline separated
        raw = [p.strip() for chunk in value.split("\n") for p in chunk.split(",")]
        return [p for p in raw if p]


class RuleForm(forms.ModelForm):
    # Make list fields user-friendly in the UI
    required_keywords_text = _CommaListField(
        required=False, help_text="Example: iso, 9001"
    )
    allowed_extensions_text = _CommaListField(
        required=False, help_text="e.g. pdf, docx, jpg (no dot)"
    )

    class Meta:
        model = SupplierValidationRule
        fields = [
            "expected_name",
            "required",
            "active",
            "required_keywords_text",
            "allowed_extensions_text",
        ]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Initialize text fields from JSON lists
        if self.instance and self.instance.pk:
            self.fields["required_keywords_text"].initial = ", ".join(
                self.instance.required_keywords or []
            )
            self.fields["allowed_extensions_text"].initial = ", ".join(
                self.instance.allowed_extensions or []
            )

    def save(self, commit=True):
        obj = super().save(commit=False)
        obj.required_keywords = self.cleaned_data.get("required_keywords_text", [])
        obj.allowed_extensions = self.cleaned_data.get("allowed_extensions_text", [])
        if commit:
            obj.save()
        return obj
