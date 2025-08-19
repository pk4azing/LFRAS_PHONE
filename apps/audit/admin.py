from django.contrib import admin
from .models import AuditLog
for m in [AuditLog]: admin.site.register(m)
