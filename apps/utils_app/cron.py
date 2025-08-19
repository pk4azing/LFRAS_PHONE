from django_cron import CronJobBase, Schedule
from django.utils import timezone
from apps.activities.models import ActivityFile
from apps.notifications.models import Notification
from apps.utils_app.email_utils import send_email_smtp, render_template
from django.conf import settings

class ExpiryReminderCron(CronJobBase):
    RUN_EVERY_MINS = 60
    schedule = Schedule(run_every_mins=RUN_EVERY_MINS)
    code = 'utils_app.expiry_reminder_cron'
    def do(self):
        now = timezone.now()
        candidates = ActivityFile.objects.filter(expiry_at__isnull=False, expiry_at__gte=now, reminder_due=True)[:100]
        for f in candidates:
            # simplified reminder: send once when reminder_due is flagged
            tmpl = '<p>Hello {ccd_name}, your file {filename} expires at {expiry}.</p>'
            body = render_template(tmpl, {'ccd_name': f.activity.ccd.user.username if f.activity.ccd_id else 'User', 'filename': f.original_name, 'expiry': f.expiry_at})
            send_email_smtp(f.activity.ccd.user.email, 'Expiry Reminder', body, {})
            Notification.objects.create(cd=f.activity.cd, kind='Good', message=f'Reminder sent for file {f.id}')
            f.reminder_due=False
            f.save(update_fields=['reminder_due'])
