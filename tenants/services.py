import secrets, string
from datetime import timedelta
from django.utils import timezone
from django.core.mail import send_mail
from django.conf import settings
from accounts.models import User, Roles
from .models import Evaluator, Supplier, EmailOTP
import os
from django.conf import settings
from django.core.files.base import ContentFile
from django.core.files.storage import default_storage


def generate_password(length=10):
    alphabet = string.ascii_letters + string.digits
    return "".join(secrets.choice(alphabet) for _ in range(length))


def send_credentials(email, password, context_note=""):
    subject = "Your Lucid Compliances account"
    body = (
        f"Hello,\n\nYour account has been created.\n"
        f"Email: {email}\nPassword: {password}\n\n{context_note}\n\n"
        f"Please sign in and change your password."
    )
    send_mail(
        subject,
        body,
        getattr(settings, "DEFAULT_FROM_EMAIL", "noreply@lucidcompliances.com"),
        [email],
        fail_silently=False,
    )


def send_otp(email):
    code = EmailOTP.generate_code(6)
    otp = EmailOTP.objects.create(
        email=email,
        code=code,
        expires_at=timezone.now() + timedelta(minutes=15),
    )
    subject = "Lucid Compliances: Verify your email"
    body = f"Your OTP code is: {code}\nIt expires in 15 minutes."
    send_mail(
        subject,
        body,
        getattr(settings, "DEFAULT_FROM_EMAIL", "noreply@lucidcompliances.com"),
        [email],
        fail_silently=False,
    )
    return otp


def create_ead_for_evaluator(evaluator: Evaluator):
    """Create POC user (EAD) with auto password, send creds + OTP."""
    pwd = generate_password()
    user = User.objects.create_user(
        email=evaluator.poc_email,
        password=pwd,
        role=Roles.EAD,
        evaluator=evaluator,
        must_change_password=True,
        email_verified=False,
    )
    send_credentials(user.email, pwd, context_note=f"Evaluator: {evaluator.name}")
    send_otp(user.email)
    return user


def create_sus_for_supplier(supplier: Supplier):
    """Create SUS user with auto password, send creds + OTP."""
    pwd = generate_password()
    user = User.objects.create_user(
        email=supplier.primary_email,
        password=pwd,
        role=Roles.SUS,
        evaluator=supplier.evaluator,
        supplier=supplier,
        must_change_password=True,
        email_verified=False,
    )
    send_credentials(
        user.email,
        pwd,
        context_note=f"Supplier: {supplier.name} (Evaluator: {supplier.evaluator.name})",
    )
    send_otp(user.email)
    return user


def create_evaluator_user(evaluator: Evaluator, email: str, role: str, **profile):
    """Create EAD/EVS under same evaluator, auto password, send creds + OTP."""
    pwd = generate_password()
    user = User.objects.create_user(
        email=email,
        password=pwd,
        role=role,
        evaluator=evaluator,
        must_change_password=True,
        email_verified=False,
        **profile,
    )
    send_credentials(user.email, pwd, context_note=f"Evaluator: {evaluator.name}")
    send_otp(user.email)
    return user


TENANT_BASE = getattr(settings, "LUCID_S3_BASE_PREFIX", "lucid/").strip("/")
TENANT_BASE = (TENANT_BASE + "/") if TENANT_BASE else ""


def _touch(key: str, content: bytes | None = None):
    """
    Create an empty (or tiny) object at `key`. Works for S3 or local storage.
    - For true "folder markers" you can also use '.../' as key, but placing a
      small '.keep' is more portable across tools/UIs.
    """
    if key.endswith("/"):
        key = key + ".keep"
    if not default_storage.exists(key):
        default_storage.save(key, ContentFile(content or b""))


def ensure_evaluator_folders(evaluator):
    """
    Creates standard prefixes for an evaluator:
    lucid/evaluators/<EID>/{documents,tickets,reports,activities,suppliers/}
    """
    root = f"{TENANT_BASE}evaluators/{evaluator.id}/"
    for sub in ("documents/", "tickets/", "reports/", "activities/", "suppliers/"):
        _touch(root + sub)

    # Add a small readme marker for clarity
    _touch(
        root + "_README.txt", f"Evaluator {evaluator.id}: {evaluator.name}\n".encode()
    )


def ensure_supplier_folders(supplier):
    """
    Creates standard prefixes for a supplier under its evaluator:
    lucid/evaluators/<EID>/suppliers/<SID>/{documents,tickets,activities}
    """
    root = f"{TENANT_BASE}evaluators/{supplier.evaluator_id}/suppliers/{supplier.id}/"
    for sub in ("documents/", "tickets/", "activities/"):
        _touch(root + sub)
    _touch(
        root + "_README.txt",
        f"Supplier {supplier.id}: {supplier.name} (Evaluator {supplier.evaluator_id})\n".encode(),
    )
