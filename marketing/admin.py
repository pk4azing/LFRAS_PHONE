from django.contrib import admin
from .models import ContactMessage


@admin.register(ContactMessage)
class ContactMessageAdmin(admin.ModelAdmin):
    list_display = ("name", "email", "company", "created_at", "handled")
    search_fields = ("name", "email", "company", "message")
    list_filter = ("handled",)
    readonly_fields = ("created_at",)
