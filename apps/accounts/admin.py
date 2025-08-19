from django.contrib import admin
from .models import User
for m in [User]: admin.site.register(m)
