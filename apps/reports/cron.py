from django_cron import CronJobBase, Schedule
class ReportSchedulerCron(CronJobBase):
    RUN_EVERY_MINS = 60
    schedule = Schedule(run_every_mins=RUN_EVERY_MINS)
    code = 'reports.scheduler_cron'
    def do(self):
        # placeholder; real scheduler would enqueue due reports
        return
