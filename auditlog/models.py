from django.db import models
from django.contrib.contenttypes.fields import GenericForeignKey
from django.contrib.contenttypes.models import ContentType
from django.conf import settings

User = settings.AUTH_USER_MODEL


class AuditEvent(models.Model):
    """
    Immutable audit trail entry for key actions.
    """

    actor = models.ForeignKey(
        User,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="audit_events",
    )
    verb = models.CharField(
        max_length=120
    )  # e.g., "created", "updated", "verified_email", "password_changed"
    action = models.CharField(
        max_length=200
    )  # e.g., "evaluator.create", "supplier.create", "user.create", "auth.verify_email"

    # Optional tenancy context
    evaluator_id = models.IntegerField(null=True, blank=True)
    supplier_id = models.IntegerField(null=True, blank=True)

    # Generic target object
    target_ct = models.ForeignKey(
        ContentType, null=True, blank=True, on_delete=models.SET_NULL
    )
    target_id = models.CharField(max_length=64, null=True, blank=True)
    target = GenericForeignKey("target_ct", "target_id")

    # Arbitrary metadata (safe for JSON)
    metadata = models.JSONField(default=dict, blank=True)

    # Request context
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    user_agent = models.TextField(blank=True)

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        who = (
            "system"
            if not self.actor
            else getattr(self.actor, "email", str(self.actor_id))
        )
        return f"[{self.created_at:%Y-%m-%d %H:%M:%S}] {who} {self.verb} {self.action}"
