import secrets, string
from datetime import timedelta
from django.utils import timezone
from django.core.mail import get_connection, EmailMessage, EmailMultiAlternatives
from django.template.loader import render_to_string
from django.urls import reverse, NoReverseMatch
import os
import logging
import smtplib
from email.mime.text import MIMEText
from email.utils import formataddr
from django.conf import settings
from accounts.models import User, Roles, EmailOtp
from .models import Evaluator, Supplier
from django.core.files.base import ContentFile
from django.core.files.storage import default_storage

logger = logging.getLogger("lfras")

# Build absolute URLs using SITE_BASE_URL from settings (configured in .env)
SITE_BASE_URL = getattr(settings, "SITE_BASE_URL", "http://127.0.0.1:5372").rstrip("/")

def _abs(url_name: str, default_path: str) -> str:
    """Return absolute URL for a named route; falls back to default_path if reverse fails."""
    try:
        return SITE_BASE_URL + reverse(url_name)
    except NoReverseMatch:
        # If a plain path was passed or the route is missing, normalize and join
        path = url_name if url_name.startswith("/") else default_path
        if not path.startswith("/"):
            path = "/" + path
        return SITE_BASE_URL + path


def _btn(url: str, label: str) -> str:
    return (
        f'<a href="{url}" '
        'style="display:inline-block;padding:12px 18px;border-radius:10px;'
        'text-decoration:none;background:#2563eb;color:#fff;font-weight:600">'
        f'{label}</a>'
    )


def send_welcome_email_generic(to_email: str, temp_password: str, role: str, display_name: str = "", context_note: str = "") -> bool:
    """Send one consolidated welcome email for any role (Evaluator, Supplier, Lucid User)."""
    # Create OTP (15 minutes expiry)
    code = EmailOtp.generate_code(6)
    EmailOtp.objects.create(
        email=to_email,
        code=code,
        expires_at=timezone.now() + timedelta(minutes=15),
    )

    title_role = role.strip() or "User"
    subject = f"Welcome to Lucid Compliances – {title_role}"
    sender_login = getattr(settings, "EMAIL_HOST_USER", None) or getattr(settings, "DEFAULT_FROM_EMAIL", "")
    branded_from = getattr(settings, "DEFAULT_FROM_EMAIL", sender_login)

    login_url  = _abs("accounts:login", "/auth/login/")
    verify_url = _abs("accounts:verify_email", "/accounts/verify-email/")

    extra_html = f"<p><strong>{context_note}</strong></p>" if context_note else ""
    person_label = (display_name or title_role)

    # Plain text fallback
    text_body = (
        f"Welcome {title_role}\n\n"
        f"Please confirm your email address and then sign in.\n\n"
        f"Email: {to_email}\n"
        f"Temporary password: {temp_password}\n"
        f"Role: {title_role}\n"
        + (f"{context_note}\n" if context_note else "") +
        f"Verify: {verify_url}\n"
        f"Login: {login_url}\n\n"
        f"OTP Code: {code} (expires in 15 minutes)\n"
    )

    # HTML primary body (reuse the evaluator template styling)
    html_body = f"""
    <!doctype html>
    <html>
    <head>
    <meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
    <title>{subject}</title>
    <style>
     body {{margin:0;background:#f6f9fc;font-family:Inter,Segoe UI,Arial,sans-serif;color:#0f172a;}}
     .wrap {{padding:24px}}
     .card {{max-width:640px;margin:0 auto;background:#fff;border:1px solid #e5e7eb;border-radius:14px;box-shadow:0 4px 14px rgba(0,0,0,.06);overflow:hidden}}
     .brand {{padding:20px 24px;border-bottom:1px solid #eef2f7;background:#0f172a;color:#fff;text-align:center}}
     .brand h1 {{margin:0;font-size:20px;letter-spacing:.5px}}
     .content {{padding:32px}}
     h2 {{font-size:22px;margin:0 0 16px 0;color:#111827}}
     p {{font-size:15px;line-height:1.5;margin:0 0 12px 0}}
     .kbd {{display:inline-block;padding:6px 10px;border-radius:8px;background:#111827;color:#fff;font-weight:600;letter-spacing:.5px;font-size:14px}}
     .muted {{color:#6b7280;font-size:12px;margin-top:20px}}
     .hr {{height:1px;background:#eef2f7;margin:24px 0}}
     .row {{margin:16px 0}}
     .btns a {{margin-right:10px}}
     .footer {{text-align:center;padding:16px;font-size:12px;color:#9ca3af;background:#f9fafb}}
    </style>
    </head>
    <body>
      <div class="wrap"> 
        <div class="card">
          <div class="brand"><h1>LFRAS – A Lucid Compliances Product</h1></div>
          <div class="content">
            <h2>Welcome, {person_label}!</h2>
            <p>You’ve been onboarded as a <strong>{title_role}</strong>. Please confirm your email and then sign in to your dashboard.</p>
            <div class="row btns">{_btn(verify_url, 'Confirm email')}</div>
            <div class="hr"></div>
            <p><strong>Email:</strong> {to_email}</p>
            <p><strong>Temporary password:</strong> <span class="kbd">{temp_password}</span></p>
            {extra_html}
            <p><strong>OTP Code:</strong> <span class="kbd">{code}</span> <span class="muted">(expires in 15 minutes)</span></p>
            <div class="row btns">{_btn(login_url, 'Go to login')}</div>
            <div class="hr"></div>
            <p class="muted">If you didn’t request this, you can safely ignore this email.</p>
          </div>
          <div class="footer">© 2025 Lucid Compliances – All rights reserved</div>
        </div>
      </div>
    </body>
    </html>
    """

    try:
        msg = EmailMultiAlternatives(
            subject=subject,
            body=text_body,
            from_email=sender_login,
            to=[to_email],
            reply_to=[branded_from],
        )
        msg.attach_alternative(html_body, "text/html")
        conn = get_connection(fail_silently=False)
        sent = (conn.send_messages([msg]) or 0) > 0
        logger.info("email.welcome_generic status=%s to=%s", "SENT" if sent else "NOT_SENT", to_email)
        return sent
    except Exception as exc:
        logger.error("email.welcome_generic error: %s", exc, exc_info=True)
        return False


def send_welcome_email_supplier(to_email: str, temp_password: str, supplier_name: str, evaluator_name: str = "") -> bool:
    ctx = f"Evaluator: {evaluator_name}" if evaluator_name else ""
    return send_welcome_email_generic(to_email, temp_password, role="Supplier", display_name=supplier_name, context_note=ctx)

def send_welcome_email_lucid_user(to_email: str, temp_password: str, display_name: str = "", department: str = "") -> bool:
    ctx = f"Department: {department}" if department else ""
    return send_welcome_email_generic(to_email, temp_password, role="Lucid User", display_name=display_name, context_note=ctx)


def send_welcome_email(to_email: str, temp_password: str, evaluator_name: str = "") -> bool:
    """Send one consolidated welcome email containing Verify + Login buttons, account details, and OTP."""
    # Create OTP (15 minutes expiry)
    code = EmailOtp.generate_code(6)
    EmailOtp.objects.create(
        email=to_email,
        code=code,
        expires_at=timezone.now() + timedelta(minutes=15),
    )

    subject = "Welcome to Lucid Compliances"
    sender_login = getattr(settings, "EMAIL_HOST_USER", None) or getattr(settings, "DEFAULT_FROM_EMAIL", "")
    branded_from = getattr(settings, "DEFAULT_FROM_EMAIL", sender_login)

    login_url  = _abs("accounts:login", "/auth/login/")
    verify_url = _abs("accounts:verify_email", "/accounts/verify-email/")

    # Plain text fallback
    text_body = (
        "Welcome to Lucid Compliances\n\n"
        "Please confirm your email address and then sign in.\n\n"
        f"Email: {to_email}\n"
        f"Temporary password: {temp_password}\n"
        f"Evaluator: {evaluator_name}\n\n"
        f"Verify: {verify_url}\n"
        f"Login: {login_url}\n\n"
        f"OTP Code: {code} (expires in 15 minutes)\n"
    )

    # HTML primary body
    html_body = f"""
    <!doctype html>
    <html>
    <head>
    <meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
    <title>{subject}</title>
    <style>
     body {{margin:0;background:#f6f9fc;font-family:Inter,Segoe UI,Arial,sans-serif;color:#0f172a;}}
     .wrap {{padding:24px}}
     .card {{max-width:640px;margin:0 auto;background:#fff;border:1px solid #e5e7eb;border-radius:14px;box-shadow:0 4px 14px rgba(0,0,0,.06);overflow:hidden}}
     .brand {{padding:20px 24px;border-bottom:1px solid #eef2f7;background:#0f172a;color:#fff;text-align:center}}
     .brand h1 {{margin:0;font-size:20px;letter-spacing:.5px}}
     .content {{padding:32px}}
     h2 {{font-size:22px;margin:0 0 16px 0;color:#111827}}
     p {{font-size:15px;line-height:1.5;margin:0 0 12px 0}}
     .kbd {{display:inline-block;padding:6px 10px;border-radius:8px;background:#111827;color:#fff;font-weight:600;letter-spacing:.5px;font-size:14px}}
     .muted {{color:#6b7280;font-size:12px;margin-top:20px}}
     .hr {{height:1px;background:#eef2f7;margin:24px 0}}
     .row {{margin:16px 0}}
     .btns a {{margin-right:10px}}
     .footer {{text-align:center;padding:16px;font-size:12px;color:#9ca3af;background:#f9fafb}}
    </style>
    </head>
    <body>
      <div class="wrap"> 
        <div class="card">
          <div class="brand"><h1>LFRAS – A Lucid Compliances Product</h1></div>
          <div class="content">
            <h2>Welcome to LFRAS</h2>
            <p>We’re excited to have you onboard! Please confirm your email and then sign in to your dashboard.</p>
            <div class="row btns">{_btn(verify_url, 'Confirm email')}</div>
            <div class="hr"></div>
            <p><strong>Email:</strong> {to_email}</p>
            <p><strong>Temporary password:</strong> <span class="kbd">{temp_password}</span></p>
            {f'<p><strong>Evaluator:</strong> {evaluator_name}</p>' if evaluator_name else ''}
            <p><strong>OTP Code:</strong> <span class="kbd">{code}</span> <span class="muted">(expires in 15 minutes)</span></p>
            <div class="row btns">{_btn(login_url, 'Go to login')}</div>
            <div class="hr"></div>
            <p class="muted">If you didn’t request this, you can safely ignore this email.</p>
          </div>
          <div class="footer">© 2025 Lucid Compliances – All rights reserved</div>
        </div>
      </div>
    </body>
    </html>
    """

    try:
        msg = EmailMultiAlternatives(
            subject=subject,
            body=text_body,
            from_email=sender_login,
            to=[to_email],
            reply_to=[branded_from],
        )
        msg.attach_alternative(html_body, "text/html")
        conn = get_connection(fail_silently=False)
        sent = (conn.send_messages([msg]) or 0) > 0
        print(f"[EMAIL] welcome to={to_email} status={'SENT' if sent else 'NOT_SENT'}")
        logger.info("email.welcome status=%s to=%s", "SENT" if sent else "NOT_SENT", to_email)
        return sent
    except Exception as exc:
        print(f"[EMAIL] welcome error={type(exc).__name__}:{exc}")
        logger.error("email.welcome error: %s", exc, exc_info=True)
        return False


def generate_password(length=10):
    alphabet = string.ascii_letters + string.digits
    return "".join(secrets.choice(alphabet) for _ in range(length))


def send_credentials(to_email: str, password: str, context_note: str = "") -> bool:
    subject = "Your Lucid Compliances account"

    # Consolidated single message replaces separate credentials + OTP flows
    return send_welcome_email(
        to_email,
        password,
        context_note.replace("Evaluator:", "").strip() if context_note else "",
    )


def send_otp(email):
    # OTP is now included in the consolidated welcome email.
    code = EmailOtp.generate_code(6)
    otp = EmailOtp.objects.create(
        email=email,
        code=code,
        expires_at=timezone.now() + timedelta(minutes=15),
    )
    logger.info("email.otp stored-only (welcome email handles delivery) for=%s code=%s", email, code)
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
    send_welcome_email_generic(user.email, pwd, role="Evaluator POC (EAD)", display_name=evaluator.name)
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
    send_welcome_email_supplier(user.email, pwd, supplier_name=supplier.name, evaluator_name=supplier.evaluator.name)
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
    send_welcome_email_generic(user.email, pwd, role=role, display_name=evaluator.name)
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
