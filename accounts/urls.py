from django.urls import reverse_lazy
from django.urls import path
from django.contrib.auth.views import (
    LogoutView,
    PasswordResetView,
    PasswordResetDoneView,
    PasswordResetConfirmView,
    PasswordResetCompleteView,
    PasswordChangeView,
)
from .views import (
    LoginViewCustom,
    VerifyEmailView,
    ResendOTPView,
    ForcePasswordChangeView,
    my_profile,
    change_password,
    users_list,
    create_lucid_user,
    logout_get,
    user_toggle_active,
    verify_email,
)

urlpatterns = [
    # Session auth
    path("login/", LoginViewCustom.as_view(), name="login"),
    path("logout/", logout_get, name="logout"),

    path("verify-email/", verify_email, name="verify_email"),

    # Forgot / reset password (built-in)
    path(
        "password-reset/",
        PasswordResetView.as_view(
            template_name="auth/password_reset_form.html",
            email_template_name="auth/password_reset_email.html",
            subject_template_name="registration/password_reset_subject.txt",
            success_url=reverse_lazy("accounts:password_reset_done"),
        ),
        name="password_reset",
    ),
    path(
        "password-reset/done/",
        PasswordResetDoneView.as_view(
            template_name="auth/password_reset_done.html",
        ),
        name="password_reset_done",
    ),
    path(
        "reset/<uidb64>/<token>/",
        PasswordResetConfirmView.as_view(
            template_name="auth/password_reset_confirm.html",
            success_url=reverse_lazy("accounts:password_reset_complete"),
        ),
        name="password_reset_confirm",
    ),
    path(
        "reset/done/",
        PasswordResetCompleteView.as_view(
            template_name="auth/password_reset_complete.html",
        ),
        name="password_reset_complete",
    ),
    # Change password (while logged in, normal use)
    path("password/change/", change_password, name="change_password"),
    # First-login flows
    path("verify-email/", VerifyEmailView.as_view(), name="verify_email"),
    path("resend-otp/", ResendOTPView.as_view(), name="resend_otp"),
    path("staff/", users_list, name="staff"),
    path("staff/create/", create_lucid_user, name="create_staff"),
    path("staff/<int:pk>/edit/", create_lucid_user, name="user_edit"),
    path(
        "force-password-change/",
        ForcePasswordChangeView.as_view(),
        name="force_password_change",
    ),
    path("me/", my_profile, name="my_profile"),
    path("profile/", my_profile, name="profile"),

    path("staff/<int:pk>/toggle/", user_toggle_active, name="user_toggle_active"),
]
