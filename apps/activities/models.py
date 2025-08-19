from django.conf import settings
from django.db import models


class Activity(models.Model):
    cd = models.ForeignKey('tenants.ClientCD', on_delete=models.CASCADE, related_name='activities')

    # CCD user (accounts.User with role='CCD')
    ccd = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name='activities_as_ccd',
        limit_choices_to={'role': 'CCD'},
        help_text='The CCD user associated with this activity'
    )

    period = models.CharField(max_length=32)
    status = models.CharField(max_length=20, default='in_progress')
    created_at = models.DateTimeField(auto_now_add=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    s3_prefix = models.CharField(max_length=500, blank=True)

    def __str__(self):
        return f"A{self.id} {self.status}"


class ActivityFile(models.Model):
    activity = models.ForeignKey(Activity, on_delete=models.CASCADE, related_name='files')
    original_name = models.CharField(max_length=255)
    document_type = models.CharField(max_length=64)
    s3_key = models.CharField(max_length=500, blank=True)
    size_bytes = models.BigIntegerField(default=0)
    uploaded_at = models.DateTimeField(auto_now_add=True)
    validation_status = models.CharField(max_length=16, default='pending')
    validation_message = models.TextField(blank=True)
    expiry_at = models.DateTimeField(null=True, blank=True)
    reminder_due = models.BooleanField(default=False)

    def __str__(self):
        return f"F{self.id} {self.validation_status}"
    

class ActivityFileReminder(models.Model):
    file = models.OneToOneField(
        ActivityFile, on_delete=models.CASCADE, related_name="reminder_state"
    )
    last_step_sent = models.IntegerField(default=0)   # 0 = none sent yet; 1..10 = steps below
    last_sent_at = models.DateTimeField(null=True, blank=True)

    def __str__(self):
        return f"ReminderState(file={self.file_id}, last_step={self.last_step_sent})"