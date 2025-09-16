# documents/forms.py (or wherever your upload form lives)
from django import forms
from .models import Document  # adjust import


class DocumentUploadForm(forms.ModelForm):
    class Meta:
        model = Document
        fields = ["title", "file", "expires_at", "supplier"]  # include supplier and expires_at

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            field.widget.attrs.update({"class": "form-control"})