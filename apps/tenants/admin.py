from django.contrib import admin
from .models import ClientCD, ClientCCD, ClientCDSMTPConfig

@admin.register(ClientCD)
class ClientCDAdmin(admin.ModelAdmin):
    list_display = ("id", "tenant_id", "name", "poc_email", "created_at")
    search_fields = ("tenant_id", "name", "poc_email")

@admin.register(ClientCCD)
class ClientCCDAdmin(admin.ModelAdmin):
    list_display = ("id", "tenant_id", "cd", "org_name", "email", "created_at")
    search_fields = ("tenant_id", "org_name", "email")
    list_filter = ("cd",)

@admin.register(ClientCDSMTPConfig)
class ClientCDSMTPConfigAdmin(admin.ModelAdmin):
    list_display = ("cd", "host", "port", "username", "use_tls", "use_ssl", "updated_at")
    search_fields = ("cd__tenant_id", "host", "username")