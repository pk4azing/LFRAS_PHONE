from django.db import models
import os
from django.utils.text import get_valid_filename
from django.conf import settings
from django.utils import timezone
from pathlib import Path

User = settings.AUTH_USER_MODEL

from django.conf import settings as dj_settings

TENANT_BASE = getattr(dj_settings, "LUCID_S3_BASE_PREFIX", "lucid/").strip("/")
TENANT_BASE = (TENANT_BASE + "/") if TENANT_BASE else ""


def activity_file_upload_path(instance, filename):
    """
    S3 path: Evaluator/{eid}/Supplier/{sid}/Activity/{aid}/Files/<safe_filename_or_versioned>
    """
    a = instance.activity
    eid = a.evaluator_id
    sid = a.supplier_id
    aid = a.id or 0

    # keep original name, but sanitize
    base = get_valid_filename(os.path.basename(filename))
    # when version >1, suffix _vN before extension
    if getattr(instance, "version", 1) and instance.version > 1:
        if "." in base:
            stem, ext = base.rsplit(".", 1)
            base = f"{stem}_v{instance.version}.{ext}"
        else:
            base = f"{base}_v{instance.version}"

    return f"Evaluator/{eid}/Supplier/{sid}/Activity/{aid}/Files/{base}"


def activity_zip_path(instance, filename):
    a = instance.activity
    name = Path(filename).name
    base = f"{TENANT_BASE}evaluators/{a.evaluator_id}/suppliers/{a.supplier_id}/activities/{a.id}/files/zipped/"
    return base + name


class ActivityStatus(models.TextChoices):
    STARTED = "started", "Started"
    IN_PROGRESS = "in_progress", "In Progress"
    COMPLETED = "completed", "Completed"
    CANCELLED = "cancelled", "Cancelled"


class FileStatus(models.TextChoices):
    UPLOADING = "uploading", "Uploading"
    UPLOADED = "uploaded", "Uploaded"
    VALIDATING = "validating", "Validation In Progress"
    VALID_OK = "valid_ok", "Validation Successful"
    VALID_FAILED = "valid_failed", "Validation Failed"
    UPLOAD_FAILED = "upload_failed", "Upload Failed"


class Activity(models.Model):
    evaluator = models.ForeignKey(
        "tenants.Evaluator", on_delete=models.CASCADE, related_name="activities"
    )
    supplier = models.ForeignKey(
        "tenants.Supplier", on_delete=models.CASCADE, related_name="activities"
    )
    status = models.CharField(
        max_length=20, choices=ActivityStatus.choices, default=ActivityStatus.STARTED
    )

    started_by = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, related_name="activities_started"
    )
    ended_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="activities_ended",
    )

    started_at = models.DateTimeField(auto_now_add=True)
    ended_at = models.DateTimeField(null=True, blank=True)

    # denorm counters for report
    total_files = models.PositiveIntegerField(default=0)
    failed_files = models.PositiveIntegerField(default=0)
    reuploaded_files = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ["-started_at"]

    def __str__(self):
        return f"Activity #{self.id} — {self.supplier.name}"


class ActivityFile(models.Model):
    activity = models.ForeignKey(
        Activity, on_delete=models.CASCADE, related_name="files"
    )
    uploaded_by = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, related_name="activity_files"
    )
    original_name = models.CharField(max_length=255)
    file = models.FileField(upload_to=activity_file_upload_path)
    file_size = models.BigIntegerField(default=0)

    status = models.CharField(
        max_length=20, choices=FileStatus.choices, default=FileStatus.UPLOADING
    )
    failure_reason = models.TextField(blank=True)
    version = models.PositiveIntegerField(default=1)
    reupload_of = models.ForeignKey(
        "self", null=True, blank=True, on_delete=models.SET_NULL
    )

    uploaded_at = models.DateTimeField(auto_now_add=True)
    validated_at = models.DateTimeField(null=True, blank=True)

    # Optional expiry date (set by uploader when required by rules)
    expires_on = models.DateField(null=True, blank=True)

    @property
    def is_expired(self) -> bool:
        return bool(self.expires_on and self.expires_on < timezone.localdate())

    class Meta:
        ordering = ["uploaded_at"]
        indexes = [
            models.Index(fields=["expires_on"]),
            models.Index(fields=["status", "uploaded_at"]),
        ]

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        if self.file and (not self.file_size or self.file_size <= 0):
            try:
                self.file_size = self.file.size
                super().save(update_fields=["file_size"])
            except Exception:
                pass


class ActivityZip(models.Model):
    activity = models.OneToOneField(
        Activity, on_delete=models.CASCADE, related_name="archive"
    )
    zip_file = models.FileField(upload_to=activity_zip_path)
    generated_at = models.DateTimeField(auto_now_add=True)
