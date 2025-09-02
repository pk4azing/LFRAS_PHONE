# documents/cron.py
from datetime import timedelta
from django.core.management import call_command
from django_cron import CronJobBase, Schedule


class SendExpiryNotificationsCron(CronJobBase):
    """
    Send document expiry notifications at 1:00 AM US/Central.
    Uses your existing management command: send_expiry_notifications
    """

    RUN_AT_TIMES = ["01:00"]  # Central time, see settings.DJANGO_CRON_TIME_ZONE
    schedule = Schedule(run_at_times=RUN_AT_TIMES)
    code = "documents.send_expiry_notifications_cron"

    def do(self):
        # You already have this command implemented.
        # If you named it differently, change here.
        call_command("send_expiry_notifications")
