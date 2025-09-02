from django.db import models
from django.conf import settings
from django.utils import timezone

User = settings.AUTH_USER_MODEL


class DocCategory(models.TextChoices):
    GENERAL = "general", "General"
    CERT = "cert", "Certificate"
    POLICY = "policy", "Policy"
    REPORT = "report", "Report"


class Document(models.Model):
    evaluator = models.ForeignKey(
        "tenants.Evaluator", on_delete=models.CASCADE, related_name="documents"
    )
    supplier = models.ForeignKey(
        "tenants.Supplier",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="documents",
    )

    title = models.CharField(max_length=200)
    category = models.CharField(
        max_length=20, choices=DocCategory.choices, default=DocCategory.GENERAL
    )
    file = models.FileField(upload_to="docs/%Y/%m/")
    file_size = models.BigIntegerField(default=0)
    uploaded_by = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, related_name="uploaded_documents"
    )
    uploaded_at = models.DateTimeField(auto_now_add=True)

    # Expiry/renewal tracking
    expires_at = models.DateTimeField(null=True, blank=True)
    remind_days_before = models.PositiveIntegerField(default=30)
    last_expiry_notified_at = models.DateTimeField(null=True, blank=True)

    is_active = models.BooleanField(default=True)

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        # ensure file_size is captured once file exists
        if self.file and (not self.file_size or self.file_size <= 0):
            try:
                self.file_size = self.file.size
                super().save(update_fields=["file_size"])
            except Exception:
                pass

    def __str__(self):
        scope = f"{self.evaluator.name}"
        if self.supplier_id:
            scope += f" / {self.supplier.name}"
        return f"{self.title} ({scope})"

    class Meta:
        ordering = ["-uploaded_at"]

    @property
    def is_expired(self):
        return bool(self.expires_at and timezone.now() > self.expires_at)

    @property
    def days_to_expiry(self):
        if not self.expires_at:
            return None
        delta = self.expires_at.date() - timezone.now().date()
        return delta.days


from django.conf import settings
from pathlib import Path

TENANT_BASE = getattr(settings, "LUCID_S3_BASE_PREFIX", "lucid/").strip("/")
TENANT_BASE = (TENANT_BASE + "/") if TENANT_BASE else ""


def document_upload_path(instance, filename):
    """
    evaluators/<EID>/documents/... or
    evaluators/<EID>/suppliers/<SID>/documents/...
    """
    name = Path(filename).name  # sanitize
    if instance.supplier_id:
        return f"{TENANT_BASE}evaluators/{instance.evaluator_id}/suppliers/{instance.supplier_id}/documents/{timezone.now():%Y/%m}/{name}"
    return f"{TENANT_BASE}evaluators/{instance.evaluator_id}/documents/{timezone.now():%Y/%m}/{name}"
