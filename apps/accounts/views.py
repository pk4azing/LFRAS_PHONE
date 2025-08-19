# apps/accounts/views.py
from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.auth.tokens import PasswordResetTokenGenerator
from django.utils.encoding import force_bytes, force_str
from django.utils.http import urlsafe_base64_encode, urlsafe_base64_decode

from rest_framework import generics, permissions, status, viewsets, mixins
from rest_framework.response import Response
from rest_framework.decorators import action

from .serializers import (
    UserSerializer,
    LoginSerializer,
    MeUpdateSerializer,
    CDEmployeeCreateSerializer,
    CDEmployeeUpdateSerializer,
    CCDCreateSerializer,
)
from apps.notifications.utils import add_notification
from apps.audit.utils import add_audit
from apps.tenants.utils import email_with_tenant

User = get_user_model()
token_generator = PasswordResetTokenGenerator()


# ---------------------------
# Auth / Profile
# ---------------------------
class LoginView(generics.GenericAPIView):
    """
    POST /api/v1/accounts/login/
    Body: { "email": "<email>", "password": "<password>" }
    Returns individual keys: access, refresh, user fields (flattened as needed).
    """
    permission_classes = [permissions.AllowAny]
    serializer_class = LoginSerializer

    def post(self, request):
        s = self.get_serializer(data=request.data)
        s.is_valid(raise_exception=True)
        user = s.validated_data["user"]

        # Issue JWTs
        from rest_framework_simplejwt.tokens import RefreshToken
        refresh = RefreshToken.for_user(user)

        # You asked for individual keys in response
        payload = {
            "access": str(refresh.access_token),
            "refresh": str(refresh),
            "user": UserSerializer(user).data,
        }

        # Audit (login) – optional, low-noise
        add_audit(actor=user, cd=user.cd, event="USER_LOGIN", meta={"user_id": user.id})

        return Response(payload, status=status.HTTP_200_OK)


class MeView(generics.GenericAPIView):
    """
    GET /api/v1/accounts/me/
    PATCH/PUT /api/v1/accounts/me/
    Allows updating name, address, city, email, username (if unique), etc.
    """
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        return Response(UserSerializer(request.user).data)

    def patch(self, request):
        s = MeUpdateSerializer(request.user, data=request.data, partial=True)
        s.is_valid(raise_exception=True)
        user = s.save()
        # Notify + Audit self changes
        add_notification(user, user.cd, "Your profile was updated.", "USER_PROFILE_UPDATED", actor=user)
        add_audit(actor=user, cd=user.cd, event="USER_PROFILE_UPDATED", target_user=user, meta=s.validated_data)
        return Response(UserSerializer(user).data, status=status.HTTP_200_OK)

    def put(self, request):
        s = MeUpdateSerializer(request.user, data=request.data, partial=False)
        s.is_valid(raise_exception=True)
        user = s.save()
        add_notification(user, user.cd, "Your profile was updated.", "USER_PROFILE_UPDATED", actor=user)
        add_audit(actor=user, cd=user.cd, event="USER_PROFILE_UPDATED", target_user=user, meta=s.validated_data)
        return Response(UserSerializer(user).data, status=status.HTTP_200_OK)


class ChangePasswordView(generics.GenericAPIView):
    """
    POST /api/v1/accounts/change-password/
    Body: {"old_password": "...", "new_password": "..."}
    """
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        old_pw = request.data.get("old_password")
        new_pw = request.data.get("new_password")
        if not old_pw or not new_pw:
            return Response({"detail": "old_password and new_password are required"},
                            status=status.HTTP_400_BAD_REQUEST)
        u = request.user
        if not u.check_password(old_pw):
            return Response({"detail": "Old password is incorrect"}, status=status.HTTP_400_BAD_REQUEST)
        u.set_password(new_pw)
        u.save()

        # Notify + Audit
        add_notification(u, u.cd, "Your password was changed.", "USER_PASSWORD_CHANGED", actor=u)
        add_audit(actor=u, cd=u.cd, event="USER_PASSWORD_CHANGED", target_user=u)

        return Response({"detail": "Password updated successfully"}, status=status.HTTP_200_OK)


# ---------------------------
# Password reset (email flow)
# ---------------------------
class ForgotPasswordView(generics.GenericAPIView):
    """
    POST /api/v1/accounts/forgot-password/
    Body: { "email": "<email>" }
    Always returns 200 to avoid email enumeration.
    Sends a reset link using FRONTEND_RESET_PASSWORD_URL?uid=<uid>&token=<token>
    """
    permission_classes = [permissions.AllowAny]

    def post(self, request):
        email = (request.data.get("email") or "").strip()
        if email:
            try:
                user = User.objects.get(email__iexact=email)
                uidb64 = urlsafe_base64_encode(force_bytes(user.pk))
                token = token_generator.make_token(user)
                base = getattr(settings, "FRONTEND_RESET_PASSWORD_URL",
                               "https://app.example.com/reset-password")
                reset_url = f"{base}?uid={uidb64}&token={token}"

                subject = "LFRAS: Password reset"
                text = f"Use this link to reset your password:\n{reset_url}\n\nIf you didn't request this, ignore."
                html = f"<p>Use this link to reset your password:</p><p><a href='{reset_url}'>{reset_url}</a></p>"

                # Tenant-aware email
                email_with_tenant(user.cd, email, subject, text, html)

                # Audit (no notification to avoid noise)
                add_audit(actor=None, cd=user.cd, event="USER_PASSWORD_RESET_REQUESTED",
                          target_user=user, meta={"email": email})
            except User.DoesNotExist:
                # Intentionally silent to prevent enumeration
                pass

        return Response({"detail": "If the email exists, a reset link has been sent."},
                        status=status.HTTP_200_OK)


class ResetPasswordView(generics.GenericAPIView):
    """
    POST /api/v1/accounts/reset-password/
    Body: { "uid": "<uidb64>", "token": "<token>", "new_password": "<pw>" }
    """
    permission_classes = [permissions.AllowAny]

    def post(self, request):
        uidb64 = request.data.get("uid")
        token = request.data.get("token")
        new_pw = request.data.get("new_password")

        if not uidb64 or not token or not new_pw:
            return Response({"detail": "uid, token and new_password are required"},
                            status=status.HTTP_400_BAD_REQUEST)

        try:
            uid = force_str(urlsafe_base64_decode(uidb64))
            user = User.objects.get(pk=uid)
        except Exception:
            return Response({"detail": "Invalid reset link"}, status=status.HTTP_400_BAD_REQUEST)

        if not token_generator.check_token(user, token):
            return Response({"detail": "Token is invalid or expired"}, status=status.HTTP_400_BAD_REQUEST)

        user.set_password(new_pw)
        user.save()

        # Notify + Audit
        add_notification(user, user.cd, "Your password was reset.", "USER_PASSWORD_RESET", actor=None)
        add_audit(actor=None, cd=user.cd, event="USER_PASSWORD_RESET", target_user=user)

        return Response({"detail": "Password reset successful"}, status=status.HTTP_200_OK)


# ---------------------------
# CD Employees (optional—keep if you expose these here)
# ---------------------------
class CDEmployeeViewSet(mixins.CreateModelMixin,
                        mixins.ListModelMixin,
                        mixins.RetrieveModelMixin,
                        mixins.UpdateModelMixin,
                        viewsets.GenericViewSet):
    """
    /api/v1/accounts/employees/
    """
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        qs = User.objects.all().select_related("cd")
        u = self.request.user
        if u.role != "LD":
            qs = qs.filter(cd_id=u.cd_id or -1)
        # Optional filtering by role/cd
        role = self.request.query_params.get("role")
        if role:
            qs = qs.filter(role=role)
        cd = self.request.query_params.get("cd")
        if cd and u.role == "LD":
            qs = qs.filter(cd_id=cd)
        return qs.order_by("id")

    def get_serializer_class(self):
        if self.action in ("create", "update", "partial_update"):
            return CDEmployeeCreateSerializer if self.action == "create" else CDEmployeeUpdateSerializer
        return UserSerializer

    def perform_create(self, serializer):
        user = serializer.save()
        # Notify POCs
        if user.cd:
            for poc in User.objects.filter(cd=user.cd, role="CD_ADMIN"):
                add_notification(poc, user.cd, f"User {user.email} created.", "USER_CREATED", actor=self.request.user)
        add_audit(actor=self.request.user, cd=user.cd, event="USER_CREATED", target_user=user)

    def perform_update(self, serializer):
        user = serializer.save()
        add_notification(user, user.cd, "Your profile was updated by admin.", "USER_PROFILE_UPDATED", actor=self.request.user)
        add_audit(actor=self.request.user, cd=user.cd, event="USER_PROFILE_UPDATED", target_user=user)


# ---------------------------
# CCD creation (one-per-tenant) via accounts if you expose it here
# ---------------------------
class CCDCreateView(generics.CreateAPIView):
    """
    POST /api/v1/accounts/ccd/
    """
    permission_classes = [permissions.IsAuthenticated]
    serializer_class = CCDCreateSerializer

    def perform_create(self, serializer):
        user = serializer.save()
        # Notify POCs
        if user.cd:
            for poc in User.objects.filter(cd=user.cd, role="CD_ADMIN"):
                add_notification(poc, user.cd, f"CCD user {user.email} created.", "CCD_CREATED", actor=self.request.user)
        add_audit(actor=self.request.user, cd=user.cd, event="CCD_CREATED", target_user=user)