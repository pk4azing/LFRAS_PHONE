from django.contrib import admin
from .models import Report


@admin.register(Report)
class ReportAdmin(admin.ModelAdmin):
    list_display = ("id", "cd", "report_type", "requested_by", "status", "requested_at", "ready_at")
    list_filter = ("report_type", "status", "requested_at")
    search_fields = ("report_type", "requested_by__email", "s3_key")
    ordering = ("-requested_at",)