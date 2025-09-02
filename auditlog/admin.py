from django.contrib import admin
from .models import AuditEvent


@admin.register(AuditEvent)
class AuditEventAdmin(admin.ModelAdmin):
    list_display = (
        "created_at",
        "actor",
        "verb",
        "action",
        "evaluator_id",
        "supplier_id",
    )
    list_filter = ("action", "verb")
    search_fields = (
        "metadata",
        "actor__email",
        "action",
        "verb",
        "user_agent",
        "ip_address",
        "target_id",
    )
    readonly_fields = ("created_at",)
