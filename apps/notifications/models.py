from django.db import models
from django.conf import settings

class Notification(models.Model):
    LEVELS = (
        ("INFO", "INFO"),
        ("WARNING", "WARNING"),
        ("ERROR", "ERROR"),
        ("SUCCESS", "SUCCESS"),
    )

    recipient = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="notifications",
    )
    cd = models.ForeignKey(
        "tenants.ClientCD",
        on_delete=models.CASCADE,
        related_name="notifications",
        null=True,
        blank=True,
        help_text="Tenant context, if applicable"
    )
    message = models.CharField(max_length=500)
    event = models.CharField(
    max_length=64,
    default="GENERAL",
    help_text="Short event code e.g. TICKET_CREATED"
    )
    level = models.CharField(max_length=16, choices=LEVELS, default="INFO")
    is_read = models.BooleanField(default=False)
    meta = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["recipient", "is_read"]),
            models.Index(fields=["cd", "event"]),
            models.Index(fields=["created_at"]),
        ]

    def __str__(self):
        return f"N{self.id} -> {self.recipient_id} [{self.level}] {self.event}"