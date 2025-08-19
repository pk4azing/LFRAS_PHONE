from django.db.models.signals import pre_save, post_save
from django.dispatch import receiver
from django.utils import timezone
from django.contrib.auth import get_user_model

from django.db.models.signals import post_save
from .models import ActivityFileReminder
from .models import Activity, ActivityFile
from apps.accounts.utils import add_notification, add_audit
from apps.tenants.utils import email_with_tenant

User = get_user_model()

@receiver(pre_save, sender=Activity)
def _capture_old_activity(sender, instance: Activity, **kwargs):
    if instance.pk:
        try:
            old = Activity.objects.get(pk=instance.pk)
            instance._old_status = old.status
        except Activity.DoesNotExist:
            instance._old_status = None
    else:
        instance._old_status = None

@receiver(post_save, sender=Activity)
def _on_activity_saved(sender, instance: Activity, created: bool, **kwargs):
    cd = instance.cd
    ccd_user = instance.ccd
    status_now = instance.status
    status_was = getattr(instance, "_old_status", None)

    if created:
        # in-app
        if ccd_user:
            add_notification(ccd_user, cd, f"Activity {instance.id} created (period={instance.period}).",
                             "ACTIVITY_CREATED", actor=None)
        for poc in User.objects.filter(cd=cd, role="CD_ADMIN"):
            add_notification(poc, cd, f"Activity {instance.id} created for period {instance.period}.",
                             "ACTIVITY_CREATED", actor=None)
        # audit
        add_audit(actor=None, cd=cd, event="ACTIVITY_CREATED",
                  meta={'activity_id': instance.id, 'period': instance.period, 'status': status_now})
        return

    # status change
    if status_was and status_was != status_now:
        msg = f"Activity {instance.id} status: {status_was} → {status_now}."
        if ccd_user:
            add_notification(ccd_user, cd, msg, "ACTIVITY_STATUS_CHANGED", actor=None)
        for poc in User.objects.filter(cd=cd, role="CD_ADMIN"):
            add_notification(poc, cd, msg, "ACTIVITY_STATUS_CHANGED", actor=None)
        add_audit(actor=None, cd=cd, event="ACTIVITY_STATUS_CHANGED",
                  meta={'activity_id': instance.id, 'from': status_was, 'to': status_now})

        # mark completion time & email on completion-like states
        if status_now.lower() in {"completed", "ready", "done"}:
            if not instance.completed_at:
                instance.completed_at = timezone.now()
                instance.save(update_fields=['completed_at'])
            subject = f"LFRAS: Activity {instance.id} completed"
            text = f"Activity {instance.id} is completed for period {instance.period}."
            html = f"<p>Activity <b>{instance.id}</b> is <b>completed</b> for period <b>{instance.period}</b>.</p>"
            if ccd_user and ccd_user.email:
                email_with_tenant(cd, ccd_user.email, subject, text, html)
            for poc_email in User.objects.filter(cd=cd, role="CD_ADMIN").values_list('email', flat=True):
                if poc_email:
                    email_with_tenant(cd, poc_email, subject, text, html)

@receiver(post_save, sender=ActivityFile)
def _on_activityfile_saved(sender, instance: ActivityFile, created: bool, **kwargs):
    act = instance.activity
    cd = act.cd
    ccd_user = act.ccd

    if created:
        # in-app
        msg = f"File '{instance.original_name}' uploaded for Activity {act.id}."
        if ccd_user:
            add_notification(ccd_user, cd, msg, "ACTIVITYFILE_UPLOADED", actor=None)
        for poc in User.objects.filter(cd=cd, role="CD_ADMIN"):
            add_notification(poc, cd, msg, "ACTIVITYFILE_UPLOADED", actor=None)
        # audit
        add_audit(actor=None, cd=cd, event="ACTIVITYFILE_UPLOADED",
                  meta={'activity_id': act.id, 'file_id': instance.id, 'name': instance.original_name})
        

@receiver(post_save, sender=ActivityFile)
def _ensure_reminder_state(sender, instance: ActivityFile, created: bool, **kwargs):
    if created:
        ActivityFileReminder.objects.get_or_create(file=instance)