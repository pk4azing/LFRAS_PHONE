from django.db import models
from django.conf import settings

class ClientCD(models.Model):
    tenant_id = models.CharField(max_length=16, unique=True, db_index=True)
    name = models.CharField(max_length=255)
    poc_name = models.CharField(max_length=255)
    poc_email = models.EmailField()
    poc_phone = models.CharField(max_length=64, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.tenant_id} {self.name}"


class ClientCCD(models.Model):
    cd = models.ForeignKey(ClientCD, on_delete=models.CASCADE, related_name="ccds")
    tenant_id = models.CharField(max_length=20, unique=True, db_index=True)
    org_name = models.CharField(max_length=255)
    email = models.EmailField(help_text="Primary login email for CCD user")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        unique_together = [("cd", "email")]

    def __str__(self):
        return f"{self.tenant_id} {self.org_name}"


class ClientCDSMTPConfig(models.Model):
    cd = models.OneToOneField(ClientCD, on_delete=models.CASCADE, related_name="smtp_config")
    host = models.CharField(max_length=255)
    port = models.IntegerField(default=587)
    username = models.CharField(max_length=255, blank=True)
    password = models.CharField(max_length=255, blank=True)
    use_tls = models.BooleanField(default=True)
    use_ssl = models.BooleanField(default=False)
    from_email = models.EmailField(blank=True, help_text="Optional explicit from address")

    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"SMTP({self.cd.tenant_id}) {self.host}:{self.port}"