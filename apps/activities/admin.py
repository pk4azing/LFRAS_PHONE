from django.contrib import admin
from .models import Activity, ActivityFile
from .models import ActivityFileReminder

@admin.register(Activity)
class ActivityAdmin(admin.ModelAdmin):
    list_display = ('id','cd','ccd','period','status','created_at','completed_at')
    list_filter = ('status','cd')
    search_fields = ('period','s3_prefix')

@admin.register(ActivityFile)
class ActivityFileAdmin(admin.ModelAdmin):
    list_display = ('id','activity','original_name','document_type','validation_status','uploaded_at')
    list_filter = ('validation_status',)
    search_fields = ('original_name','document_type','s3_key')


@admin.register(ActivityFileReminder)
class ActivityFileReminderAdmin(admin.ModelAdmin):
    list_display = ("file", "last_step_sent", "last_sent_at")
    search_fields = ("file__original_name",)