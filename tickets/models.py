from __future__ import annotations

from django.conf import settings
from django.db import models
from django.utils import timezone

# Always reference the configured user model
USER_MODEL = settings.AUTH_USER_MODEL


class TicketStatus(models.Model):
    """Catalog of statuses (e.g., Open, Pending, Running, Done, Cancelled)."""

    STATUS_CHOICES = [
        ("OPEN", "Open"),
        ("PENDING", "Pending"),
        ("RUNNING", "Running"),
        ("DONE", "Done"),
        ("CANCELLED", "Cancelled"),
    ]
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, unique=True)

    class Meta:
        ordering = ["id"]

    def __str__(self) -> str:  # pragma: no cover - simple repr
        return dict(self.STATUS_CHOICES).get(self.status, self.status.title())


class TicketPriority(models.Model):
    PRIORITY_CHOICES = [
        ("low", "Low"),
        ("medium", "Medium"),
        ("high", "High"),
        ("critical", "Critical"),
    ]
    priority = models.CharField(max_length=20, choices=PRIORITY_CHOICES, unique=True)

    class Meta:
        ordering = ["id"]

    def __str__(self) -> str:  # pragma: no cover
        return dict(self.PRIORITY_CHOICES).get(self.priority, self.priority.title())


# --------- helpers ---------

def attachment_upload_to(instance: "TicketAttachment", filename: str) -> str:
    """Store attachments under a stable path per-ticket and month.

    tickets/ticket=<id or tmp>/year=YYYY/month=MM/<uuid>.<ext>
    """
    import uuid as _uuid

    ticket_id = getattr(instance.ticket, "id", None) or "tmp"
    today = timezone.now()
    ext = filename.split(".")[-1].lower()
    return (
        f"tickets/ticket={ticket_id}/year={today:%Y}/month={today:%m}/"
        f"{_uuid.uuid4().hex}.{ext}"
    )


# --------- core models ---------

class Ticket(models.Model):
    """Core support ticket."""

    STATUS_CHOICES = [
        ("OPEN", "Open"),
        ("PENDING", "Pending"),
        ("RUNNING", "Running"),
        ("DONE", "Done"),
        ("CANCELLED", "Cancelled"),
    ]

    title = models.CharField(max_length=200)
    description = models.TextField(blank=True)

    priority = models.CharField(
        max_length=20,
        choices=TicketPriority.PRIORITY_CHOICES,
        default="medium",
    )

    # NOTE: previously a trailing comma turned this into a tuple.
    # This is a proper ForeignKey field now.
    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default="OPEN",
        help_text=(
            "If left empty, application logic should default this to the initial "
            "status (e.g., Open)."
        ),
    )

    # assignments / relations
    assignee = models.ForeignKey(
        USER_MODEL,
        on_delete=models.PROTECT,
        related_name="tickets_assigned",
        help_text="Assigned LAD/LUS.",
    )
    evaluator = models.ForeignKey(
        USER_MODEL,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="tickets_as_evaluator",
        help_text="EVS/EAD when applicable.",
    )
    supplier = models.ForeignKey(
        USER_MODEL,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="tickets_as_supplier",
        help_text="SUS when applicable.",
    )
    created_by = models.ForeignKey(
        USER_MODEL,
        on_delete=models.PROTECT,
        related_name="tickets_created",
    )

    due_date = models.DateField(null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["created_at"]),
            models.Index(fields=["assignee"]),
            models.Index(fields=["status"]),
            models.Index(fields=["priority"]),
        ]

    def __str__(self) -> str:  # pragma: no cover
        return f"#{self.pk or '—'} {self.title}"


class TicketComment(models.Model):
    ticket = models.ForeignKey(Ticket, on_delete=models.CASCADE, related_name="comments")
    author = models.ForeignKey(USER_MODEL, on_delete=models.PROTECT, related_name="ticket_comments")
    body = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["created_at"]

    def __str__(self) -> str:  # pragma: no cover
        return f"Comment by {self.author} on {self.ticket}"


class TicketAttachment(models.Model):
    ticket = models.ForeignKey(Ticket, on_delete=models.CASCADE, related_name="attachments")
    uploaded_by = models.ForeignKey(USER_MODEL, on_delete=models.PROTECT, related_name="ticket_attachments")
    file = models.FileField(upload_to=attachment_upload_to)
    uploaded_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["uploaded_at"]

    def __str__(self) -> str:  # pragma: no cover
        return f"Attachment {self.file.name} for {self.ticket}"