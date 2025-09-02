# payments/management/commands/expire_subscriptions.py
from django.core.management.base import BaseCommand
from django.utils import timezone
from payments.models import PaymentRecord


class Command(BaseCommand):
    help = "Mark PaymentRecords past end_date as expired."

    def handle(self, *args, **options):
        today = timezone.localdate()
        qs = PaymentRecord.objects.filter(status="active", end_date__lt=today)
        count = qs.update(status="expired")
        self.stdout.write(self.style.SUCCESS(f"{count} subscriptions expired."))
