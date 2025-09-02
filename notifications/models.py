from django.db import models
from django.conf import settings

User = settings.AUTH_USER_MODEL


class Level(models.TextChoices):
    INFO = "info", "Info"
    SUCCESS = "success", "Success"
    WARNING = "warning", "Warning"
    ERROR = "error", "Error"


class Notification(models.Model):
    recipient = models.ForeignKey(
        User, on_delete=models.CASCADE, related_name="notifications"
    )
    title = models.CharField(max_length=200)
    body = models.TextField(blank=True)
    level = models.CharField(max_length=10, choices=Level.choices, default=Level.INFO)
    link_url = models.CharField(max_length=500, blank=True)
    read_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.recipient} — {self.title}"


class EmailEvent(models.Model):
    """
    Lightweight log for outbound emails we care about counting on dashboards.
    """

    category = models.CharField(max_length=50, db_index=True)  # e.g. "expiry"
    subject = models.CharField(max_length=255)
    recipient_email = models.EmailField()
    created_at = models.DateTimeField(auto_now_add=True)

    # optional context
    meta = models.JSONField(null=True, blank=True)

    class Meta:
        indexes = [models.Index(fields=["category", "-created_at"])]
        ordering = ["-created_at"]

    def __str__(self):
        return f"[{self.category}] {self.subject} → {self.recipient_email}"
