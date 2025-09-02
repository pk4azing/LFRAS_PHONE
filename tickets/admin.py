from django.contrib import admin
from .models import Ticket, TicketComment, TicketAttachment

@admin.register(Ticket)
class TicketAdmin(admin.ModelAdmin):
    list_display = ("id", "title", "status", "priority", "assignee", "created_by", "created_at")
    list_filter = ("status", "priority", "assignee")
    search_fields = ("title", "description")

admin.site.register(TicketComment)
admin.site.register(TicketAttachment)