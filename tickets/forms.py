from django import forms
from django.utils import timezone

from accounts.models import User, Roles
from .models import (
    Ticket,
    TicketComment,
    TicketAttachment,
    TicketPriority,
)


class _BaseBSFormMixin:
    """
    Adds Bootstrap-compatible classes to common widgets automatically.
    """
    def _add_bs_classes(self):
        for name, field in self.fields.items():
            widget = field.widget
            if isinstance(widget, (forms.TextInput, forms.DateInput)):
                widget.attrs.setdefault("class", "form-control")
            elif isinstance(widget, forms.Textarea):
                widget.attrs.setdefault("class", "form-control")
                widget.attrs.setdefault("rows", 5)
            elif isinstance(widget, (forms.Select, forms.SelectMultiple)):
                widget.attrs.setdefault("class", "form-select")
            elif isinstance(widget, forms.ClearableFileInput):
                widget.attrs.setdefault("class", "form-control")


class TicketForm(_BaseBSFormMixin, forms.ModelForm):
    """
    Creation form. It accepts a 'user' kwarg so we can scope options
    and apply role-based defaults/requirements.
    """
    due_date = forms.DateField(
        required=False,
        widget=forms.DateInput(attrs={"type": "date", "class": "form-control"}),
    )

    class Meta:
        model = Ticket
        fields = [
            "title",
            "description",
            "priority",
            "due_date",
            "assignee",
            "evaluator",
            "supplier",
            "status",
        ]
        widgets = {
            "title": forms.TextInput(),
            "description": forms.Textarea(),
            "priority": forms.Select(),
            "assignee": forms.Select(),
            "evaluator": forms.Select(),
            "supplier": forms.Select(),
            "status": forms.Select(),
        }

    def __init__(self, *args, **kwargs):
        self.user = kwargs.pop("user", None)
        super().__init__(*args, **kwargs)
        self._add_bs_classes()

        # Queryset scoping
        self.fields["assignee"].queryset = User.objects.filter(
            role__in=[Roles.LAD, Roles.LUS], is_active=True
        )
        self.fields["evaluator"].queryset = User.objects.filter(
            role__in=[Roles.EVS, Roles.EAD], is_active=True
        )
        self.fields["supplier"].queryset = User.objects.filter(
            role=Roles.SUS, is_active=True
        )

        # Status & Priority sensible ordering
        self.fields["priority"].queryset = TicketPriority.objects.all().order_by("priority", "id")

        # These are optional at the DB level and role-conditional in business rules
        self.fields["evaluator"].required = False
        self.fields["supplier"].required = False
        self.fields["status"].required = False  # allow the view to set default (e.g., "Open")

        # Placeholder text / accessibility
        self.fields["title"].widget.attrs.setdefault("placeholder", "Brief summary")
        self.fields["description"].widget.attrs.setdefault("placeholder", "Describe the issue or request…")

    def clean(self):
        """
        Apply role-aware soft rules:
          - SUS: supplier defaults to self if not provided.
          - EVS/EAD: supplier must be empty (we null it).
          - LAD/LUS: free to set supplier/evaluator.
        Final guardrails (required/assignment policies) should live in the view.
        """
        cleaned = super().clean()
        user = self.user
        if not user:
            return cleaned

        role = getattr(user, "role", None)

        # SUS defaults to themselves as supplier
        if role == Roles.SUS:
            cleaned["supplier"] = cleaned.get("supplier") or user

        # EVS/EAD should not be allowed to pick a supplier
        if role in (Roles.EVS, Roles.EAD):
            cleaned["supplier"] = None

        # Prevent past-due dates (optional)
        due = cleaned.get("due_date")
        if due and due < timezone.now().date():
            self.add_error("due_date", "Due date cannot be in the past.")

        return cleaned


class TicketUpdateForm(_BaseBSFormMixin, forms.ModelForm):
    due_date = forms.DateField(
        required=False,
        widget=forms.DateInput(attrs={"type": "date", "class": "form-control"}),
    )

    class Meta:
        model = Ticket
        fields = ["status", "priority", "due_date", "assignee", "evaluator", "supplier"]
        widgets = {
            "status": forms.Select(),
            "priority": forms.Select(),
            "assignee": forms.Select(),
            "evaluator": forms.Select(),
            "supplier": forms.Select(),
        }

    def __init__(self, *args, **kwargs):
        self.user = kwargs.pop("user", None)
        super().__init__(*args, **kwargs)
        self._add_bs_classes()

        self.fields["assignee"].queryset = User.objects.filter(
            role__in=[Roles.LAD, Roles.LUS], is_active=True
        )
        self.fields["evaluator"].queryset = User.objects.filter(
            role__in=[Roles.EVS, Roles.EAD], is_active=True
        )
        self.fields["supplier"].queryset = User.objects.filter(
            role=Roles.SUS, is_active=True
        )

        self.fields["evaluator"].required = False
        self.fields["supplier"].required = False


class CommentForm(_BaseBSFormMixin, forms.ModelForm):
    class Meta:
        model = TicketComment
        fields = ["body"]
        widgets = {
            "body": forms.Textarea(attrs={"rows": 4, "placeholder": "Add a comment…"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._add_bs_classes()


class AttachmentForm(_BaseBSFormMixin, forms.ModelForm):
    class Meta:
        model = TicketAttachment
        fields = ["file"]
        widgets = {
            "file": forms.ClearableFileInput(),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._add_bs_classes()