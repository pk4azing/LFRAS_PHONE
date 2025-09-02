from django.db import models
from django.utils import timezone


class SupplierValidationRule(models.Model):
    evaluator = models.ForeignKey(
        "tenants.Evaluator", on_delete=models.CASCADE, related_name="validation_rules"
    )
    supplier = models.ForeignKey(
        "tenants.Supplier", on_delete=models.CASCADE, related_name="validation_rules"
    )

    # Human label, e.g. "ISO 9001 Certificate"
    expected_name = models.CharField(max_length=200)

    # Store lists as JSON for portability (works on all DBs)
    required_keywords = models.JSONField(default=list, blank=True)  # list[str]
    allowed_extensions = models.JSONField(default=list, blank=True)  # list[str]

    required = models.BooleanField(default=True)
    active = models.BooleanField(default=True)

    created_at = models.DateTimeField(default=timezone.now)

    class Meta:
        unique_together = ("supplier", "expected_name")
        ordering = ["supplier_id", "expected_name"]

    def __str__(self):
        return f"{self.supplier.name} — {self.expected_name}"
