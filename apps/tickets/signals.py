from django.db.models.signals import pre_save, post_save
from django.dispatch import receiver
from django.utils import timezone
from django.contrib.auth import get_user_model
from .models import Ticket
from apps.accounts.utils import add_notification, add_audit
from apps.tenants.utils import email_with_tenant

User = get_user_model()

@receiver(pre_save, sender=Ticket)
def _capture_old_ticket(sender, instance: Ticket, **kwargs):
    if instance.pk:
        try:
            old = Ticket.objects.get(pk=instance.pk)
            instance._old_status = old.status
            instance._old_assignee_id = old.assigned_to_id
        except Ticket.DoesNotExist:
            instance._old_status = None
            instance._old_assignee_id = None
    else:
        instance._old_status = None
        instance._old_assignee_id = None

@receiver(post_save, sender=Ticket)
def _ticket_post_save(sender, instance: Ticket, created: bool, **kwargs):
    # This is a safety net in case tickets are mutated outside the ViewSet
    if created:
        return  # creation is fully handled in perform_create
    prev_status = getattr(instance, "_old_status", None)
    prev_assignee_id = getattr(instance, "_old_assignee_id", None)

    if prev_status != instance.status and instance.status == "CLOSED" and not instance.closed_at:
        instance.closed_at = timezone.now()
        instance.save(update_fields=['closed_at'])