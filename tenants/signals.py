from django.db.models.signals import post_save
from django.dispatch import receiver
from .models import Evaluator, Supplier
from .services import ensure_evaluator_folders, ensure_supplier_folders


@receiver(post_save, sender=Evaluator)
def evaluator_created(sender, instance: Evaluator, created, **kwargs):
    if created:
        ensure_evaluator_folders(instance)


@receiver(post_save, sender=Supplier)
def supplier_created(sender, instance: Supplier, created, **kwargs):
    if created:
        ensure_supplier_folders(instance)
