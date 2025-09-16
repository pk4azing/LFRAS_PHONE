from django import forms
from django.contrib.auth.forms import AuthenticationForm
from django.contrib.auth import password_validation
from .models import User
from django.core.exceptions import ValidationError

# Creation permissions per role (authoritative server-side map)
ALLOWED_CREATE = {
    "LAD": ["LAD", "LUS"],   # Lucid Admin can create Lucid roles only
    "LUS": ["LUS"],           # Lucid Staff can create Lucid Staff only
    "EAD": ["EAD", "EST"],   # Evaluator Admin can create Evaluator roles
    "EST": [],                 # Evaluator Staff cannot create users
    "SUS": [],                 # Supplier Staff cannot create users
}


class EmailAuthenticationForm(AuthenticationForm):
    # Use email as the username field in the login form
    username = forms.EmailField(label="Email")


class ProfileForm(forms.ModelForm):
    remove_photo = forms.BooleanField(
        required=False, initial=False, help_text="Remove current photo"
    )

    class Meta:
        model = User
        fields = [
            "first_name",
            "last_name",
            "phone",
            "address_line1",
            "address_line2",
            "city",
            "state",
            "postal_code",
            "country",
            "profile_photo",
        ]


# accounts/forms.py (inside ProfileForm)
def clean_profile_photo(self):
    img = self.cleaned_data.get("profile_photo")
    if not img:
        return img
    if img.size > 2 * 1024 * 1024:
        raise forms.ValidationError("Image must be <= 2MB.")
    if not img.content_type in ("image/png", "image/jpeg"):
        raise forms.ValidationError("Only PNG or JPG allowed.")
    return img


class PasswordChangeSimpleForm(forms.Form):
    current_password = forms.CharField(
        widget=forms.PasswordInput(attrs={"class": "form-control"})
    )
    new_password1 = forms.CharField(
        widget=forms.PasswordInput(attrs={"class": "form-control"})
    )
    new_password2 = forms.CharField(
        widget=forms.PasswordInput(attrs={"class": "form-control"})
    )

    def __init__(self, user, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.user = user

    def clean_current_password(self):
        cp = self.cleaned_data["current_password"]
        if not self.user.check_password(cp):
            raise forms.ValidationError("Current password is incorrect.")
        return cp

    def clean(self):
        cleaned = super().clean()
        p1, p2 = cleaned.get("new_password1"), cleaned.get("new_password2")
        if p1 and p2 and p1 != p2:
            raise forms.ValidationError("New passwords do not match.")
        password_validation.validate_password(p1, self.user)
        return cleaned



class LucidUserForm(forms.ModelForm):
    class Meta:
        model = User
        fields = [
            "first_name",
            "last_name",
            "email",
            "role",
            "phone",
            "address_line1",
            "address_line2",
            "city",
            "state",
            "postal_code",
            "country",
        ]

    def __init__(self, *args, request_user=None, **kwargs):
        super().__init__(*args, **kwargs)
        # Keep a reference to the user attempting to create/edit
        self.request_user = request_user
        # Narrow the role choices shown in the UI based on creator's role
        if request_user is not None:
            allowed = ALLOWED_CREATE.get(getattr(request_user, "role", None), [])
            # If allowed is empty, leave choices empty to prevent selection
            if allowed:
                self.fields["role"].choices = [
                    (code, label) for code, label in self.fields["role"].choices if code in allowed
                ]
            else:
                self.fields["role"].choices = []
                self.fields["role"].help_text = "You are not permitted to create users for other organizations."

    def clean_role(self):
        role = self.cleaned_data.get("role")
        creator = getattr(self, "request_user", None)
        allowed = ALLOWED_CREATE.get(getattr(creator, "role", None), [])
        if role not in allowed:
            raise ValidationError("You are not permitted to create a user with this role.")
        return role
