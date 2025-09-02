# payments/cron.py
from django.core.management import call_command
from django_cron import CronJobBase, Schedule


class ExpireSubscriptionsCron(CronJobBase):
    """
    Mark subscriptions expired at 1:00 AM US/Central.
    Calls your expire_subscriptions management command.
    """

    RUN_AT_TIMES = ["01:00"]
    schedule = Schedule(run_at_times=RUN_AT_TIMES)
    code = "payments.expire_subscriptions_cron"

    def do(self):
        call_command("expire_subscriptions")
