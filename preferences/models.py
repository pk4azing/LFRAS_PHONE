# preferences/models.py
from django.db import models
from django.utils import timezone


class SiteSetting(models.Model):
    """
    Simple key/value store for LAD-managed prefs.
    Keys we’ll use (examples):
      - email_from
      - support_email
      - s3_base_prefix  (e.g., 'lucid/')
      - expiry_schedule_days  (JSON list: [30,14,7,1])
    """

    key = models.CharField(max_length=64, unique=True)
    value = models.JSONField(default=dict, blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.key
