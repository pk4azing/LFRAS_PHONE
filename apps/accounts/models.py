from django.contrib.auth.models import AbstractUser
from django.db import models


class Roles(models.TextChoices):
    LD = "LD", "Lucid Employee"
    CD_ADMIN = "CD_ADMIN", "CD Admin"
    CD_STAFF = "CD_STAFF", "CD Staff"
    CCD = "CCD", "CCD User"


class User(AbstractUser):
    # core identity
    email = models.EmailField(unique=True)
    username = models.CharField(max_length=150, unique=True)

    # profile
    name = models.CharField(max_length=255, null=True, blank=True)
    address = models.CharField(max_length=255, null=True, blank=True)
    city = models.CharField(max_length=100, null=True, blank=True)
    phone = models.CharField(max_length=20, null=True, blank=True)

    # role & tenant
    role = models.CharField(max_length=16, choices=Roles.choices, default=Roles.CCD)
    cd = models.ForeignKey('tenants.ClientCD', null=True, blank=True,
                           on_delete=models.SET_NULL, related_name='users')

    # security
    must_change_password = models.BooleanField(default=False)

    # authentication: email-as-username
    USERNAME_FIELD = 'email'
    REQUIRED_FIELDS = ['username']  # prompted on createsuperuser

    class Meta:
        indexes = [
            models.Index(fields=['role']),
            models.Index(fields=['cd']),
        ]

    def __str__(self):
        return f"{self.email} ({self.role})"