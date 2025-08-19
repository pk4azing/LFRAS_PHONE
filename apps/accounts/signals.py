from django.contrib.auth import get_user_model
from django.db.models.signals import post_save
from django.dispatch import receiver
from apps.tenants.utils import email_with_tenant
from .utils import add_notification, add_audit, cd_poc_emails, ld_superadmin_emails

User = get_user_model()

@receiver(post_save, sender=User)
def user_create_notify_audit(sender, instance: any, created: bool, **kwargs):
    if not created:
        return
    # Welcome/self notification
    add_notification(instance, instance.cd, "Your account was created.", "USER_CREATED", actor=None)

    # Per-role routing
    if instance.role in ("CD_ADMIN", "CD_STAFF", "CCD"):
        cd = instance.cd
        # Notify POCs + LD superadmins by email
        for email in cd_poc_emails(cd) + ld_superadmin_emails():
            email_with_tenant(cd, email,
                              subject="Account created",
                              body_text=f"{instance.role} user {instance.email} was created in tenant {cd.name if cd else '-'}",
                              body_html=f"<p><b>{instance.role}</b> user <b>{instance.email}</b> was created in tenant <b>{cd.name if cd else '-'}</b>.</p>")
        # In-app notifications to POCs
        for poc in User.objects.filter(cd=cd, role="CD_ADMIN"):
            add_notification(poc, cd, f"{instance.role} {instance.email} created.", "USER_CREATED", actor=instance)

    elif instance.role == "LD":
        # Email LD superadmins
        for email in set(ld_superadmin_emails() + [instance.email]):
            email_with_tenant(None, email,
                              subject="LD account created",
                              body_text=f"LD user {instance.email} was created.",
                              body_html=f"<p>LD user <b>{instance.email}</b> was created.</p>")

    # Audit
    add_audit(actor=None, cd=instance.cd, event="USER_CREATED", target_user=instance)