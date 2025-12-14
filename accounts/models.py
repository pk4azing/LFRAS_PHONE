from django.db import models
from django.contrib.auth.models import (
    AbstractBaseUser,
    PermissionsMixin,
    BaseUserManager,
)

import os
import re
import uuid
from django.utils import timezone

import secrets
import string


class Roles(models.TextChoices):
    LAD = "LAD", "Lucid Admin"
    LUS = "LUS", "Lucid Staff"
    EAD = "EAD", "Evaluator Admin"
    EVS = "EVS", "Evaluator Staff"
    SUS = "SUS", "Supplier Staff"


def role_default_is_staff(role: str) -> bool:
    # Admin/staff access to Django admin for Lucid/Evaluator roles (not Supplier by default)
    return role in {Roles.LAD, Roles.LUS, Roles.EAD, Roles.EVS}


def role_redirect_path(role: str) -> str:
    # Where users land after login (template views we already wired in router app)
    mapping = {
        Roles.LAD: "/ld/admin/home",
        Roles.LUS: "/ld/staff/home",
        Roles.EAD: "/evaluator/admin/home",
        Roles.EVS: "/evaluator/staff/home",
        Roles.SUS: "/supplier/staff/home",
    }
    return mapping.get(role, "/")


class UserManager(BaseUserManager):
    def create_user(self, email, password=None, role=Roles.SUS, **extra):
        if not email:
            raise ValueError("Email is required")
        email = self.normalize_email(email)

        extra.setdefault("is_active", True)
        if "is_staff" not in extra:
            extra["is_staff"] = role_default_is_staff(role)

        user = self.model(email=email, role=role, **extra)
        if password:
            user.set_password(password)
        else:
            user.set_unusable_password()
        user.save(using=self._db)
        return user

    def create_superuser(self, email, password=None, **extra):
        # Superuser is LAD by default
        extra.setdefault("role", Roles.LAD)
        extra.setdefault("is_staff", True)
        extra.setdefault("is_superuser", True)
        role = extra.pop("role")
        return self.create_user(email, password, role=role, **extra)


def profile_photo_upload_to(instance, filename):
    """Place profile photos in a stable, readable path.
    Example: profiles/role=LAD/user_email=jane.doe%40acme.com/year=2025/month=09/<uuid>.jpg
    """
    # keep extension
    base, ext = os.path.splitext(filename or "")
    ext = (ext or ".jpg").lower()

    # normalize role/email for path safety
    role = getattr(instance, "role", "UNK") or "UNK"
    email = getattr(instance, "email", "unknown") or "unknown"
    # encode '@' to avoid accidental folder nesting while keeping readability
    safe_email = email.replace("@", "%40")
    # scrub anything not safe for S3 keys
    safe_email = re.sub(r"[^A-Za-z0-9_.%+-]", "_", safe_email)

    now = timezone.now()
    return (
        f"profiles/role={role}/user_email={safe_email}/"
        f"year={now:%Y}/month={now:%m}/{uuid.uuid4().hex}{ext}"
    )


class User(AbstractBaseUser, PermissionsMixin):
    email = models.EmailField(unique=True)
    username = models.CharField(max_length=150, blank=True, null=True, unique=True)
    first_name = models.CharField(max_length=120, blank=True)
    last_name = models.CharField(max_length=120, blank=True)

    role = models.CharField(max_length=3, choices=Roles.choices, default=Roles.SUS)

    # Tenancy associations (nullable for Lucid roles)
    evaluator = models.ForeignKey(
        "tenants.Evaluator",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="users",
    )
    supplier = models.ForeignKey(
        "tenants.Supplier",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="users",
    )

    # First‑login/verification flags
    email_verified = models.BooleanField(default=False)
    must_change_password = models.BooleanField(default=True)

    is_active = models.BooleanField(default=True)
    is_staff = models.BooleanField(default=False)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    profile_photo = models.ImageField(
        upload_to=profile_photo_upload_to, null=True, blank=True
    )
    phone = models.CharField(max_length=32, blank=True)
    address_line1 = models.CharField(max_length=128, blank=True)
    address_line2 = models.CharField(max_length=128, blank=True)
    city = models.CharField(max_length=64, blank=True)
    state = models.CharField(max_length=64, blank=True)
    postal_code = models.CharField(max_length=20, blank=True)
    country = models.CharField(max_length=64, blank=True, default="USA")

    USERNAME_FIELD = "email"
    REQUIRED_FIELDS = []

    objects = UserManager()

    def __str__(self):
        return f"{self.email} ({self.role})"

    @property
    def redirect_path(self) -> str:
        return role_redirect_path(self.role)


# OTP model for email verification
class EmailOtp(models.Model):
    email = models.EmailField()
    code = models.CharField(max_length=10)
    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField()
    verified_at = models.DateTimeField(null=True, blank=True)

    def __str__(self):
        return f"OTP for {self.email} - {self.code}"

    @staticmethod
    def generate_code(length=6):
        return ''.join(secrets.choice(string.digits) for _ in range(length))
