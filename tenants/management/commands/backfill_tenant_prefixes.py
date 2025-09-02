from django.core.management.base import BaseCommand
from tenants.models import Evaluator, Supplier
from tenants.services import ensure_evaluator_folders, ensure_supplier_folders


class Command(BaseCommand):
    help = "Create S3 prefixes for all existing Evaluators and Suppliers."

    def handle(self, *args, **options):
        ec = sc = 0
        for e in Evaluator.objects.all():
            ensure_evaluator_folders(e)
            ec += 1
        for s in Supplier.objects.all():
            ensure_supplier_folders(s)
            sc += 1
        self.stdout.write(
            self.style.SUCCESS(f"Ensured prefixes: {ec} evaluators, {sc} suppliers")
        )
