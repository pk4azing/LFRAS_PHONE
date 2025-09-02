from django.contrib import admin
from .models import Notification


@admin.register(Notification)
class NotificationAdmin(admin.ModelAdmin):
    list_display = ("recipient", "title", "level", "created_at", "read_at")
    list_filter = ("level",)
    search_fields = ("recipient__email", "title", "body", "link_url")
    readonly_fields = ("created_at", "read_at")
