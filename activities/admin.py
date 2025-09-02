from django.contrib import admin
from .models import Activity, ActivityFile, ActivityZip


class ActivityFileInline(admin.TabularInline):
    model = ActivityFile
    extra = 0
    readonly_fields = (
        "uploaded_at",
        "file_size",
        "status",
        "failure_reason",
        "version",
    )


@admin.register(Activity)
class ActivityAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "evaluator",
        "supplier",
        "status",
        "started_by",
        "started_at",
        "ended_at",
        "total_files",
        "failed_files",
        "reuploaded_files",
    )
    list_filter = ("status", "evaluator", "supplier")
    inlines = [ActivityFileInline]


@admin.register(ActivityZip)
class ActivityZipAdmin(admin.ModelAdmin):
    list_display = ("activity", "generated_at")
