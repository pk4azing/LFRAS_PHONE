import random, string
from typing import Optional
from django.core.mail import EmailMultiAlternatives, get_connection
from django.conf import settings
from django.template.defaultfilters import truncatechars
from .models import ClientCD, ClientCDSMTPConfig

def gen_password(length: int = 12) -> str:
    alphabet = string.ascii_letters + string.digits + "!@#$%^&*"
    return "".join(random.SystemRandom().choice(alphabet) for _ in range(length))

def gen_tenant_id(prefix: str, seq: int) -> str:
    return f"{prefix}-{seq:05d}"

def s3_ensure_paths(cd: ClientCD, ccd: Optional[object] = None):
    """
    Hook: create required S3 folders/keys for a CD (and CCD if provided).
    Implement with boto3 if needed; left as a no-op placeholder.
    """
    # from storages.backends.s3boto3 import S3Boto3Storage
    # storage = S3Boto3Storage()
    # base = f"tenants/{cd.tenant_id}/"
    # if ccd:
    #     base = f"tenants/{cd.tenant_id}/ccd/{ccd.tenant_id}/"
    # storage.save(base + ".keep", ContentFile(b""))
    return True

def _smtp_connection_for_cd(cd: ClientCD):
    cfg = getattr(cd, "smtp_config", None)
    if cfg:
        return get_connection(
            host=cfg.host,
            port=cfg.port,
            username=cfg.username or None,
            password=cfg.password or None,
            use_tls=cfg.use_tls,
            use_ssl=cfg.use_ssl,
        ), (cfg.from_email or cfg.username or settings.DEFAULT_FROM_EMAIL)
    # Fallback to project email settings
    return get_connection(), getattr(settings, "DEFAULT_FROM_EMAIL", "no-reply@example.com")

def email_with_tenant(cd: ClientCD, to_email: str, subject: str, body_text: str, body_html: Optional[str] = None):
    conn, from_email = _smtp_connection_for_cd(cd)
    msg = EmailMultiAlternatives(subject=truncatechars(subject, 255), body=body_text, from_email=from_email, to=[to_email], connection=conn)
    if body_html:
        msg.attach_alternative(body_html, "text/html")
    try:
        msg.send()
        return True
    except Exception:
        return False