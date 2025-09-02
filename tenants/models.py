from django.db import models
from django.utils import timezone
import secrets, string


class Plan(models.TextChoices):
    ENTERPRISE = "ENTERPRISE", "Enterprise"
    PROFESSIONAL = "PROFESSIONAL", "Professional"
    ESSENTIALS = "ESSENTIALS", "Essentials"


class PaymentTransaction(models.Model):
    payment_id = models.CharField(max_length=100, unique=True)
    amount_cents = models.PositiveIntegerField(default=0)
    currency = models.CharField(max_length=10, default="USD")
    paid_at = models.DateTimeField(default=timezone.now)
    notes = models.TextField(blank=True)

    def __str__(self):
        return self.payment_id


class Evaluator(models.Model):
    # Lucid's Customer (tenant)
    name = models.CharField(max_length=200, unique=True)
    address = models.CharField(max_length=200, blank=True)

    email_domain = models.CharField(
        max_length=120, help_text="Allowed domain for employees, e.g. 'acme.com'"
    )
    website = models.URLField(blank=True)
    subdomain = models.SlugField(
        max_length=50, unique=True, help_text="Subdomain for employee accounts"
    )

    plan = models.CharField(
        max_length=20, choices=Plan.choices, default=Plan.ESSENTIALS
    )

    payment = models.OneToOneField(
        PaymentTransaction,
        on_delete=models.SET_NULL,  # if a payment is deleted, keep the evaluator
        null=True,
        blank=True,  # allow creating Evaluator before payment exists
        related_name="evaluator",
    )
    poc_name = models.CharField(max_length=120)
    poc_email = models.EmailField(unique=True)

    is_active = models.BooleanField(default=True)
    address_line1 = models.CharField(max_length=128, blank=True)
    address_line2 = models.CharField(max_length=128, blank=True)
    city = models.CharField(max_length=64, blank=True)
    state = models.CharField(max_length=64, blank=True)
    postal_code = models.CharField(max_length=20, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Evaluator (Tenant)"
        verbose_name_plural = "Evaluators (Tenants)"

    @property
    def domain(self):
        """Backward‑compat alias: prefer email_domain, then subdomain, else empty string."""
        return self.email_domain or self.subdomain or ""

    def __str__(self):
        return f"{self.name} [{self.plan}]"


class Supplier(models.Model):
    evaluator = models.ForeignKey(
        Evaluator, on_delete=models.CASCADE, related_name="suppliers"
    )
    name = models.CharField(max_length=200)
    address = models.CharField(max_length=200, blank=True)
    address_line1 = models.CharField(max_length=128, blank=True)
    address_line2 = models.CharField(max_length=128, blank=True)
    city = models.CharField(max_length=64, blank=True)
    state = models.CharField(max_length=64, blank=True)
    postal_code = models.CharField(max_length=20, blank=True)
    phone = models.CharField(max_length=40, blank=True)
    primary_email = models.EmailField(unique=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = [("evaluator", "name")]

    def __str__(self):
        return f"{self.name} ({self.evaluator.name})"


class EmailOTP(models.Model):
    email = models.EmailField()
    code = models.CharField(max_length=8)
    expires_at = models.DateTimeField()
    attempts = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)

    @staticmethod
    def generate_code(length=6):
        alphabet = string.digits
        return "".join(secrets.choice(alphabet) for _ in range(length))

    def is_valid(self):
        return timezone.now() < self.expires_at and self.attempts < 5

    def __str__(self):
        return f"{self.email} - {self.code}"
