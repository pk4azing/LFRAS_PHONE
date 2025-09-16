from django.contrib.auth.views import LoginView, PasswordChangeView
from django.urls import reverse_lazy
from django.contrib.auth import logout

from django.views.generic import FormView, View
from django.shortcuts import redirect, render, get_object_or_404
from django.core.paginator import Paginator
from django.contrib.auth.decorators import login_required, user_passes_test
from django.views.decorators.http import require_POST
from django.db.models import Q
from django.contrib import messages
from django import forms

from .forms import (
    EmailAuthenticationForm,
    ProfileForm,
    PasswordChangeSimpleForm,
    LucidUserForm,
)
from .models import User
from django.conf import settings
from django.core.mail import send_mail
from tenants.models import EmailOTP
from tenants.services import send_otp

# Audit & notifications
from auditlog.services import log_event
from notifications.services import notify
from notifications.models import Level


class LoginViewCustom(LoginView):
    authentication_form = EmailAuthenticationForm
    template_name = "auth/login.html"
    redirect_authenticated_user = True
    success_url = reverse_lazy("router:role_redirect")


@login_required
def logout_get(request):
    logout(request)
    return redirect("accounts:login")  # or "router:dashboard" if you prefer


# ----- OTP verification (first login email verification) -----


class OTPForm(forms.Form):
    code = forms.CharField(max_length=8, label="Enter the 6-digit code")


class VerifyEmailView(FormView):
    template_name = "auth/verify_email.html"
    form_class = OTPForm
    success_url = reverse_lazy("router:role_redirect")

    def dispatch(self, request, *args, **kwargs):
        if not request.user.is_authenticated:
            return redirect("accounts:login")
        if request.user.email_verified:
            return redirect("router:role_redirect")
        return super().dispatch(request, *args, **kwargs)

    def form_valid(self, form):
        user: User = self.request.user
        code = form.cleaned_data["code"].strip()

        # Get most recent OTP for this email
        otp = EmailOTP.objects.filter(email=user.email).order_by("-created_at").first()
        if not otp:
            messages.error(self.request, "No OTP found. Please request a new code.")
            return redirect("accounts:resend_otp")

        if not otp.is_valid():
            messages.error(
                self.request, "OTP expired or too many attempts. Request a new code."
            )
            return redirect("accounts:resend_otp")

        if code != otp.code:
            otp.attempts += 1
            otp.save(update_fields=["attempts"])
            messages.error(self.request, "Invalid code. Please try again.")
            return self.form_invalid(form)

        # Success — mark verified
        user.email_verified = True
        user.save(update_fields=["email_verified"])

        # Audit + notify (in‑app)
        log_event(
            request=self.request,
            actor=user,
            verb="verified_email",
            action="auth.verify_email",
            target=user,
        )
        notify(
            user,
            title="Email verified",
            body="Your email has been verified successfully.",
            level=Level.SUCCESS,
            email=False,  # no outbound email needed here
        )

        messages.success(self.request, "Email verified successfully.")
        return super().form_valid(form)


class ResendOTPView(View):
    def post(self, request):
        if not request.user or not request.user.is_authenticated:
            return redirect("accounts:login")
        send_otp(request.user.email)
        messages.info(request, "A new OTP has been sent to your email.")
        return redirect("accounts:verify_email")

    # Allow GET as a convenience
    def get(self, request):
        return self.post(request)


# ----- Force password change (first login) -----


class ForcePasswordChangeView(PasswordChangeView):
    template_name = "auth/force_password_change.html"
    success_url = reverse_lazy("router:role_redirect")

    def dispatch(self, request, *args, **kwargs):
        if not request.user.is_authenticated:
            return redirect("accounts:login")
        if not request.user.email_verified:
            messages.warning(request, "Please verify your email first.")
            return redirect("accounts:verify_email")
        return super().dispatch(request, *args, **kwargs)

    def form_valid(self, form):
        resp = super().form_valid(form)

        user: User = self.request.user
        if user.must_change_password:
            user.must_change_password = False
            user.save(update_fields=["must_change_password"])

        # Audit + notify (in‑app)
        log_event(
            request=self.request,
            actor=user,
            verb="password_changed",
            action="auth.force_password_change",
            target=user,
        )

        notify(
            user,
            title="Password updated",
            body="Your password has been changed.",
            level=Level.SUCCESS,
            email=False,
        )

        messages.success(self.request, "Password updated successfully.")
        return resp


@login_required
def my_profile(request):
    u = request.user

    # If the avatar-only form was used, do not bind the full ProfileForm
    if request.method == "POST" and request.POST.get("_save_avatar"):
        # Handle remove checkbox
        if request.POST.get("remove_photo") and u.profile_photo:
            u.profile_photo.delete(save=False)
            u.profile_photo = None
            u.save(update_fields=["profile_photo"])
            messages.success(request, "Profile photo removed.")
            return redirect("accounts:my_profile")

        # Handle new upload
        file_obj = request.FILES.get("profile_photo")
        if file_obj:
            u.profile_photo = file_obj
            u.save(update_fields=["profile_photo"])
            messages.success(request, "Profile photo updated.")
        else:
            messages.info(request, "No file selected.")
        return redirect("accounts:my_profile")

    # Otherwise, process the full profile form
    if request.method == "POST":
        form = ProfileForm(request.POST, request.FILES, instance=u)
        if form.is_valid():
            prof = form.save(commit=False)
            # Respect remove-photo from the full form too
            if form.cleaned_data.get("remove_photo") and prof.profile_photo:
                prof.profile_photo.delete(save=False)
                prof.profile_photo = None
            prof.save()
            messages.success(request, "Profile updated.")
            return redirect("accounts:my_profile")
        else:
            messages.error(request, "Please correct the errors below.")
    else:
        form = ProfileForm(instance=u)

    return render(request, "account/my_profile.html", {"form": form})


@login_required
def change_password(request):
    form = PasswordChangeSimpleForm(request.user, request.POST or None)
    if request.method == "POST" and form.is_valid():
        request.user.set_password(form.cleaned_data["new_password1"])
        request.user.must_change_password = False  # if you use that flag
        request.user.save(update_fields=["password", "must_change_password"])
        messages.success(request, "Password changed. Please log in again.")
        return redirect("accounts:login")
    return render(request, "account/change_password.html", {"form": form})


def is_LAD(user):
    return getattr(user, "role", None) == "LAD"


@login_required
@user_passes_test(is_LAD)
def users_list(request):
    """List Lucid employees (LUS) with search + pagination. LAD can view/manage."""
    from .models import User

    qs = User.objects.filter(role__in=["LAD", "LUS"]).order_by("-created_at")

    q = request.GET.get("q", "").strip()
    if q:
        qs = qs.filter(
            Q(email__icontains=q)
            | Q(first_name__icontains=q)
            | Q(last_name__icontains=q)
            | Q(phone__icontains=q)
        )

    status = request.GET.get("status")
    if status == "active":
        qs = qs.filter(is_active=True)
    elif status == "inactive":
        qs = qs.filter(is_active=False)

    role = request.GET.get("role") or ""
    if role:
        qs = qs.filter(role=role)

    paginator = Paginator(qs, 20)
    page_obj = paginator.get_page(request.GET.get("page"))

    ctx = {
        "page_obj": page_obj,
        "q": q,
        "status": status,
        "role": role,
        "total": qs.count(),
    }
    return render(request, "account/users_list.html", ctx)


@login_required
@user_passes_test(is_LAD)  # only Lucid Admins can create
def create_lucid_user(request, pk: int | None = None):
    # If a pk is passed (route used for edit), delegate to the edit view
    if pk is not None:
        return user_edit(request, pk)

    instance = None  # creation flow only
    if request.method == "POST":
        form = LucidUserForm(
            request.POST or None,
            instance=instance,
            request_user=request.user,
        )
        if form.is_valid():
            user = form.save(commit=False)
            # generate password
            raw_pw = User.objects.make_random_password(length=10)
            user.set_password(raw_pw)
            user.save()
            # email the credentials
            send_mail(
                "Your LucidCompliances account",
                (
                    f"Hello {user.first_name},\n\n"
                    f"Your account has been created.\n"
                    f"Username: {user.email}\nPassword: {raw_pw}\n"
                ),
                settings.DEFAULT_FROM_EMAIL,
                [user.email],
            )
            messages.success(
                request, f"Lucid user {user.email} created and password sent."
            )
            return redirect("accounts:staff")
        else:
            messages.error(request, "Please correct the errors below.")
    else:
        form = LucidUserForm(request_user=request.user)

    return render(request, "account/create_lucid_user.html", {"form": form})


@login_required
@user_passes_test(is_LAD)  # only Lucid Admins can edit Lucid staff
def user_edit(request, pk: int):
    user = get_object_or_404(User, pk=pk, role__in=["LAD", "LUS"])
    if request.method == "POST":
        form = LucidUserForm(request.POST, instance=user, request_user=request.user)
        if form.is_valid():
            form.save()
            messages.success(request, "User updated successfully.")
            return redirect("accounts:staff")
        else:
            messages.error(request, "Please correct the errors below.")
    else:
        form = LucidUserForm(instance=user, request_user=request.user)
    # Reuse the create template for editing; it already has a form layout
    return render(request, "account/create_lucid_user.html", {"form": form, "is_edit": True, "editing_user": user})



@login_required
@user_passes_test(is_LAD)
@require_POST
def user_toggle_active(request, pk: int):
    user = get_object_or_404(User, pk=pk, role__in=["LAD", "LUS"])
    if user.id == request.user.id:
        messages.warning(request, "You cannot deactivate your own account.")
        return redirect("accounts:staff")
    user.is_active = not user.is_active
    user.save(update_fields=["is_active"])
    messages.success(request, f"{'Activated' if user.is_active else 'Deactivated'} {user.email}.")
    return redirect("accounts:staff")