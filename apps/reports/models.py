from django.db import models
from django.conf import settings


class Report(models.Model):
    STATUS = (
        ("REQUESTED", "REQUESTED"),
        ("PROCESSING", "PROCESSING"),
        ("READY", "READY"),
        ("FAILED", "FAILED"),
    )

    cd = models.ForeignKey("tenants.ClientCD", on_delete=models.CASCADE, related_name="reports")
    requested_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name="reports_requested"
    )
    report_type = models.CharField(max_length=64)
    status = models.CharField(max_length=16, choices=STATUS, default="REQUESTED")
    s3_key = models.CharField(max_length=512, blank=True)   # S3 location when READY
    requested_at = models.DateTimeField(auto_now_add=True)
    ready_at = models.DateTimeField(null=True, blank=True)
    failed_reason = models.TextField(blank=True)

    class Meta:
        ordering = ["-requested_at"]
        indexes = [
            models.Index(fields=["cd", "status"]),
            models.Index(fields=["report_type"]),
        ]

    def __str__(self):
        return f"R{self.id} {self.report_type} [{self.status}]"