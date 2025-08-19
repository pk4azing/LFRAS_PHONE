from django.contrib import admin
from .models import Notification


@admin.register(Notification)
class NotificationAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "recipient",
        "message",
        "level",
        "is_read",
        "created_at",
    )
    list_filter = ("level", "is_read", "created_at")
    search_fields = ("recipient__email", "message")
    ordering = ("-created_at",)