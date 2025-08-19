from django.db.models.signals import pre_save, post_save
from django.dispatch import receiver
from django.contrib.auth import get_user_model
from .models import Report
from apps.accounts.utils import add_notification, add_audit
from apps.tenants.utils import email_with_tenant

User = get_user_model()


@receiver(pre_save, sender=Report)
def _capture_old_status(sender, instance: Report, **kwargs):
    if instance.pk:
        try:
            old = Report.objects.get(pk=instance.pk)
            instance._old_status = old.status
        except Report.DoesNotExist:
            instance._old_status = None
    else:
        instance._old_status = None


@receiver(post_save, sender=Report)
def _on_report_saved(sender, instance: Report, created: bool, **kwargs):
    cd = instance.cd
    requester = instance.requested_by
    status_now = instance.status
    status_was = getattr(instance, "_old_status", None)

    if created:
        # handled in perform_create; keep here for extra safety (idempotent)
        if requester:
            add_notification(requester, cd, f"Report requested: {instance.report_type}.",
                             "REPORT_REQUESTED", actor=requester)
        for poc in User.objects.filter(cd=cd, role="CD_ADMIN"):
            add_notification(poc, cd, f"Report requested: {instance.report_type}.",
                             "REPORT_REQUESTED", actor=requester)
        add_audit(actor=requester, cd=cd, event="REPORT_REQUESTED", target_user=requester,
                  meta={"report_id": instance.id, "type": instance.report_type})
        return

    if status_was and status_was != status_now:
        msg = f"Report {instance.id} status: {status_was} → {status_now}."
        if requester:
            add_notification(requester, cd, msg, "REPORT_STATUS_CHANGED", actor=None)
        for poc in User.objects.filter(cd=cd, role="CD_ADMIN"):
            add_notification(poc, cd, msg, "REPORT_STATUS_CHANGED", actor=None)
        add_audit(actor=None, cd=cd, event="REPORT_STATUS_CHANGED", target_user=requester,
                  meta={"report_id": instance.id, "from": status_was, "to": status_now})

        if status_now == "READY":
            subject = f"LFRAS: Report {instance.id} is ready"
            text = f"Your {instance.report_type} report is ready."
            html = f"<p>Your <b>{instance.report_type}</b> report is ready.</p>"
            if requester and requester.email:
                email_with_tenant(cd, requester.email, subject, text, html)
            for poc in User.objects.filter(cd=cd, role="CD_ADMIN").values_list("email", flat=True):
                if poc:
                    email_with_tenant(cd, poc, subject, text, html)