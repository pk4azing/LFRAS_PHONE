# documents/management/commands/send_expiry_notifications.py
from __future__ import annotations

from datetime import timedelta
from typing import Iterable, List, Set

from django.conf import settings
from django.core.mail import send_mail
from django.core.management.base import BaseCommand
from django.template.loader import render_to_string
from django.utils import timezone

from accounts.models import Roles
from documents.models import Document  # adjust if your app label differs
from notifications.models import EmailEvent  # <-- used for dashboard counts

# Optional in-app notification integration (best-effort)
try:
    from notifications.utils import notify, Level  # type: ignore
except Exception:  # graceful fallback

    class Level:
        INFO = "info"
        WARNING = "warning"
        ERROR = "error"

    def notify(*args, **kwargs):  # no-op fallback
        return None


# Settings-driven cadence
REMINDER_OFFSETS: List[int] = getattr(
    settings, "LUCID_EXPIRY_REMINDER_OFFSETS", [30, 14, 7, 1]
)
POST_INTERVAL: int = getattr(settings, "LUCID_EXPIRY_POST_INTERVAL_DAYS", 7)

FROM_EMAIL = getattr(settings, "DEFAULT_FROM_EMAIL", "noreply@lucidcompliances.com")
SITE_URL = getattr(settings, "SITE_URL", "https://lfras.lucidcompliances.com")


# --------------------------- helpers -----------------------------------------
def _collect_recipients(doc) -> List[str]:
    """
    Recipients:
      - Evaluator users: EAD + EVS
      - Supplier users: SUS
    """
    emails: Set[str] = set()

    if getattr(doc, "evaluator_id", None):
        for u in doc.evaluator.users.filter(
            is_active=True, role__in=[Roles.EAD, Roles.EVS]
        ):
            if u.email:
                emails.add(u.email)

    if getattr(doc, "supplier_id", None):
        for u in doc.supplier.users.filter(is_active=True, role=Roles.SUS):
            if u.email:
                emails.add(u.email)

    return list(emails)


def _render_email(subject: str, doc) -> tuple[str, str]:
    """
    Returns (text_body, html_body). Falls back to simple text if templates missing.
    """
    ctx = {"doc": doc, "subject": subject, "site_url": SITE_URL}
    try:
        txt = render_to_string("emails/expiry_reminder.txt", ctx)
        html = render_to_string("emails/expiry_reminder.html", ctx)
        return txt, html
    except Exception:
        txt = (
            f"{subject}\n\n"
            f"Document: {getattr(doc, 'title', '-')}\n"
            f"Expires on: {getattr(doc, 'expiry_date', '-')}\n"
            f"Evaluator: {getattr(getattr(doc, 'evaluator', None), 'name', '-')}\n"
            f"Supplier: {getattr(getattr(doc, 'supplier', None), 'name', '-')}\n\n"
            f"Open: {SITE_URL}/documents/{doc.id}/\n"
            f"— Lucid Compliances"
        )
        return txt, ""


def _notify_and_email(
    recipients: Iterable[str],
    subject: str,
    text_body: str,
    html_body: str,
    link_url: str,
) -> int:
    """
    Try in-app notification + email via `notify` if available.
    Fall back to Django send_mail. Returns the number of recipients attempted.
    """
    sent = 0
    for em in recipients:
        try:
            # Primary path: notify helper (in-app + email if your notify supports email=True)
            notify(
                em,
                subject,
                body=text_body,
                level=Level.WARNING,
                link_url=link_url,
                email=True,
                html_body=html_body or None,
            )
            sent += 1
        except Exception:
            # Fallback: direct email
            try:
                send_mail(
                    subject=subject,
                    message=text_body,
                    from_email=FROM_EMAIL,
                    recipient_list=[em],
                    html_message=html_body or None,
                    fail_silently=True,
                )
                sent += 1
            except Exception:
                # swallow & continue with other recipients
                continue
    return sent


# --------------------------- command -----------------------------------------
class Command(BaseCommand):
    help = "Send document expiry reminders (pre & post expiry) based on settings-defined cadence."

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Compute targets and render, but do not send or log.",
        )

    def handle(self, *args, **options):
        dry_run = bool(options.get("dry_run"))
        today = timezone.localdate()

        total_docs = 0
        total_sent = 0

        # -------- pre-expiry reminders (D-30/14/7/1 by default) --------
        for d in REMINDER_OFFSETS:
            target_date = today + timedelta(days=d)
            qs = Document.objects.filter(
                is_active=True, expiry_date=target_date
            ).select_related("evaluator", "supplier")

            for doc in qs:
                total_docs += 1
                subject = f"[Lucid] Document expiring in {d} day(s): {getattr(doc, 'title', f'#{doc.pk}')}"
                link_url = f"/documents/{doc.id}/"
                text_body, html_body = _render_email(subject, doc)
                recipients = _collect_recipients(doc)

                if dry_run:
                    self.stdout.write(
                        f"DRY-RUN pre-expiry: doc {doc.id} → {len(recipients)} recipients (D-{d})"
                    )
                    continue

                sent = _notify_and_email(
                    recipients, subject, text_body, html_body, link_url
                )
                total_sent += sent

                # Log each attempted recipient for LAD dashboard counts
                for em in recipients:
                    try:
                        EmailEvent.objects.create(
                            category="expiry",
                            subject=subject,
                            recipient_email=em,
                            meta={"document_id": doc.id, "phase": "pre", "days": d},
                        )
                    except Exception:
                        # Do not block the run if logging fails
                        pass

        # -------- post-expiry reminders (every N days after expiry) --------
        if POST_INTERVAL and POST_INTERVAL > 0:
            qs = Document.objects.filter(
                is_active=True, expiry_date__lt=today
            ).select_related("evaluator", "supplier")
            for doc in qs:
                days_since = (today - doc.expiry_date).days
                # Only trigger on exact cadence multiples (e.g., every 7 days)
                if days_since % POST_INTERVAL != 0:
                    continue

                total_docs += 1
                subject = f"[Lucid] Document expired {days_since} day(s) ago: {getattr(doc, 'title', f'#{doc.pk}')}"
                link_url = f"/documents/{doc.id}/"
                text_body, html_body = _render_email(subject, doc)
                recipients = _collect_recipients(doc)

                if dry_run:
                    self.stdout.write(
                        f"DRY-RUN post-expiry: doc {doc.id} → {len(recipients)} recipients ({days_since}d)"
                    )
                    continue

                sent = _notify_and_email(
                    recipients, subject, text_body, html_body, link_url
                )
                total_sent += sent

                # Log each attempted recipient for LAD dashboard counts
                for em in recipients:
                    try:
                        EmailEvent.objects.create(
                            category="expiry",
                            subject=subject,
                            recipient_email=em,
                            meta={
                                "document_id": doc.id,
                                "phase": "post",
                                "days_since": days_since,
                            },
                        )
                    except Exception:
                        pass

        summary = (
            f"Documents matched: {total_docs}, notifications attempted: {total_sent}"
        )
        if dry_run:
            self.stdout.write(
                self.style.WARNING("Expiry reminders DRY-RUN complete — " + summary)
            )
        else:
            self.stdout.write(self.style.SUCCESS("Expiry reminders sent — " + summary))
