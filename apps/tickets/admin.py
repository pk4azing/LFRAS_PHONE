from django.contrib import admin
from .models import Ticket, TicketComment

@admin.register(Ticket)
class TicketAdmin(admin.ModelAdmin):
    list_display = ('id','title','status','priority','cd','assigned_to','created_by','created_at')
    list_filter = ('status','priority','cd')
    search_fields = ('title','description')

@admin.register(TicketComment)
class TicketCommentAdmin(admin.ModelAdmin):
    list_display = ('id','ticket','author','created_at')
    search_fields = ('message',)