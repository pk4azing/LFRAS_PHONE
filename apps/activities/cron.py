# apps/activities/cron.py
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from django.conf import settings
from django.db.models import Prefetch
from django.utils.timezone import now

from django_cron import CronJobBase, Schedule
from django.contrib.auth import get_user_model

from apps.accounts.utils import add_notification, add_audit
from apps.tenants.utils import email_with_tenant
from .models import ActivityFile, ActivityFileReminder

User = get_user_model()

# Steps mapping:
#  1: 28 days prior  (4 weeks)
#  2: 21 days prior
#  3: 14 days prior
#  4:  7 days prior
#  5:  1 day prior (24h)
#  6:  0 days (on the day)
#  7: +1 day (post-expiry 24h)
#  8: +2 days (48h)
#  9: +3 days (72h)
# 10: +4 days (96h)
DAYS_TO_STEP = {
    -28: 1, -21: 2, -14: 3, -7: 4, -1: 5, 0: 6, 1: 7, 2: 8, 3: 9, 4: 10
}

def _local_today_and_hour():
    tz = ZoneInfo(getattr(settings, "REMINDER_TZ", "America/New_York"))
    _now = now().astimezone(tz)
    return _now.date(), _now.hour, tz


class FileExpiryReminderCron(CronJobBase):
    """
    Runs hourly (RUN_EVERY_MINS), but only sends at 09:00 America/New_York.
    For each ActivityFile with expiry_at set, if today matches one of the steps
    relative to expiry (±28, 21, 14, 7, 1, 0, +1..+4 days), send a single reminder
    if not already sent for that step.
    """
    RUN_EVERY_MINS = 60  # run hourly; we gate by local hour == 9
    schedule = Schedule(run_every_mins=RUN_EVERY_MINS)
    code = "activities.FileExpiryReminderCron"

    def do(self):
        local_date, local_hour, tz = _local_today_and_hour()

        # Only send at exactly 9 AM local time
        if local_hour != 9:
            return

        # Preload reminder state
        qs = (
            ActivityFile.objects
            .select_related("activity", "activity__cd", "activity__ccd")
            .prefetch_related(
                Prefetch("reminder_state", queryset=ActivityFileReminder.objects.all())
            )
            .filter(expiry_at__isnull=False)
        )

        processed = 0

        for f in qs.iterator():
            # Make sure we have a reminder state
            state, _ = ActivityFileReminder.objects.get_or_create(file=f)

            # Compute day difference in local date (expiry date minus today)
            expiry_local_date = f.expiry_at.astimezone(tz).date()
            delta_days = (expiry_local_date - local_date).days

            if delta_days not in DAYS_TO_STEP:
                continue

            step = DAYS_TO_STEP[delta_days]

            # Skip if this step already sent
            if state.last_step_sent >= step:
                continue

            # If the file has been finalized/approved, you might want to skip post-expiry nags:
            # Example: if f.validation_status == "approved": continue
            # (Comment out if you want to keep reminding regardless)

            self._send_reminder(f, step)
            # Update state
            state.last_step_sent = step
            state.last_sent_at = now()
            state.save(update_fields=["last_step_sent", "last_sent_at"])
            processed += 1

        return f"FileExpiryReminderCron: processed={processed}"

    # ------------------------------------------------------------------
    # Message builders
    # ------------------------------------------------------------------
    def _labels(self, step: int):
        return {
            1: ("First Reminder: 4 weeks before expiry", "WARNING"),
            2: ("Second Reminder: 3 weeks before expiry", "WARNING"),
            3: ("Third Reminder: 2 weeks before expiry", "WARNING"),
            4: ("Fourth Reminder: 1 week before expiry", "WARNING"),
            5: ("Fifth Reminder: 24 hours before expiry", "WARNING"),
            6: ("Expiry Day", "EXPIRY"),
            7: ("Post-Expiry: 24 hours", "EXPIRY"),
            8: ("Post-Expiry: 48 hours", "EXPIRY"),
            9: ("Post-Expiry: 72 hours", "EXPIRY"),
            10: ("Final Reminder: 96 hours post-expiry", "EXPIRY"),
        }[step]

    def _send_reminder(self, f: ActivityFile, step: int):
        act = f.activity
        cd = act.cd
        ccd_user = act.ccd

        title, level = self._labels(step)
        subject = f"LFRAS: {title} – {f.original_name}"
        text = (
            f"{title}\n\n"
            f"Activity #{act.id} (period: {act.period})\n"
            f"File: {f.original_name}\n"
            f"Expiry: {f.expiry_at.isoformat()}\n"
        )
        html = (
            f"<p><b>{title}</b></p>"
            f"<p>Activity #{act.id} (period: {act.period})<br/>"
            f"File: <b>{f.original_name}</b><br/>"
            f"Expiry: {f.expiry_at}</p>"
        )

        # In-app notifications
        msg = f"[{title}] {f.original_name} (Activity #{act.id}, period {act.period})"
        if ccd_user:
            add_notification(ccd_user, cd, msg, f"ACTIVITYFILE_{level}", actor=None)
        for poc in User.objects.filter(cd=cd, role="CD_ADMIN"):
            add_notification(poc, cd, msg, f"ACTIVITYFILE_{level}", actor=None)

        # Audit
        add_audit(
            actor=None, cd=cd, event=f"ACTIVITYFILE_{level}_REMINDER",
            target_user=ccd_user,
            meta={"activity_id": act.id, "file_id": f.id, "step": step, "file": f.original_name}
        )

        # Email out (ccd + all CD admins)
        recipients = set()
        if ccd_user and ccd_user.email:
            recipients.add(ccd_user.email)
        for e in User.objects.filter(cd=cd, role="CD_ADMIN").values_list("email", flat=True):
            if e:
                recipients.add(e)
        for to in recipients:
            email_with_tenant(cd, to, subject, text, html)