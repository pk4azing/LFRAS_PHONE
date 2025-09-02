# documents/forms.py (or wherever your upload form lives)
from django import forms
from .models import Document  # adjust import


class DocumentUploadForm(forms.ModelForm):
    class Meta:
        model = Document
        fields = ["file", "title"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Add Mofi/Bootstrap-like classes
        self.fields["file"].widget.attrs.update({"class": "form-control"})
        self.fields["title"].widget.attrs.update({"class": "form-control"})
