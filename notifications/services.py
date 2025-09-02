from django.utils import timezone
from django.core.mail import send_mail
from django.conf import settings
from .models import Notification, Level


def notify(
    recipient,
    title: str,
    body: str = "",
    *,
    level: Level = Level.INFO,
    link_url: str = "",
    email: bool = True,
):
    n = Notification.objects.create(
        recipient=recipient,
        title=title,
        body=body,
        level=level,
        link_url=link_url or "",
    )
    if email and getattr(recipient, "email", None):
        subject = f"[Lucid] {title}"
        msg = f"{body}\n\n{link_url}" if link_url else body
        send_mail(
            subject,
            msg,
            getattr(settings, "DEFAULT_FROM_EMAIL", "noreply@lucidcompliances.com"),
            [recipient.email],
            fail_silently=True,
        )
    return n


def mark_read(notification: Notification):
    if not notification.read_at:
        notification.read_at = timezone.now()
        notification.save(update_fields=["read_at"])


def mark_all_read(recipient):
    recipient.notifications.filter(read_at__isnull=True).update(read_at=timezone.now())
