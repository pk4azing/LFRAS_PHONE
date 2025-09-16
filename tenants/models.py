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
    """
    Third‑party company that works with an Evaluator (tenant).
    SUS users belong to a Supplier and inherit its Evaluator via FK.
    """
    evaluator = models.ForeignKey(
        Evaluator, on_delete=models.CASCADE, related_name="suppliers"
    )

    # Identity
    name = models.CharField(max_length=200)
    website = models.URLField(blank=True)

    # General contact + optional routing
    email = models.EmailField(blank=True, help_text="General contact email (optional)")
    subdomain = models.SlugField(max_length=50, blank=True, help_text="Optional subdomain used by this supplier")

    # Geography
    country = models.CharField(max_length=64, blank=True)

    # Misc
    notes = models.TextField(blank=True)

    # Primary point of contact for the supplier org
    poc_name = models.CharField(max_length=120, blank=True)
    primary_email = models.EmailField(blank=True)
    phone = models.CharField(max_length=40, blank=True)

    # Address (optional)
    address = models.CharField(max_length=200, blank=True)
    address_line1 = models.CharField(max_length=128, blank=True)
    address_line2 = models.CharField(max_length=128, blank=True)
    city = models.CharField(max_length=64, blank=True)
    state = models.CharField(max_length=64, blank=True)
    postal_code = models.CharField(max_length=20, blank=True)

    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = [
            ("evaluator", "name"),
            # Allow a supplier to optionally reserve a subdomain within an evaluator
            ("evaluator", "subdomain"),
        ]
        indexes = [
            models.Index(fields=["evaluator", "is_active"]),
            models.Index(fields=["name"]),
            models.Index(fields=["subdomain"]),
        ]
        ordering = ["name", "id"]

    def __str__(self) -> str:
        hint = f"@{self.subdomain}" if self.subdomain else self.evaluator.name
        return f"{self.name} ({hint})"

    @property
    def domain(self) -> str:
        """Convenience: domain derived from POC email if present."""
        if self.poc_email and "@" in self.poc_email:
            return self.poc_email.split("@", 1)[1]
        return ""


# --- SupplierValidationRule model ---
class SupplierValidationRule(models.Model):
    supplier = models.ForeignKey(Supplier, on_delete=models.CASCADE, related_name="tenant_validation_rules")
    expected_name = models.CharField(max_length=200, help_text="Expected filename (case-insensitive match)")
    allowed_extensions = models.CharField(max_length=200, blank=True, help_text="Pipe-separated extensions e.g. pdf|png|jpg")
    required_keywords = models.CharField(max_length=200, blank=True, help_text="Pipe-separated keywords that must appear in filename")
    is_required = models.BooleanField(default=False, help_text="If true, this file is mandatory for the supplier")
    expiry_days = models.PositiveIntegerField(null=True, blank=True, help_text="Default number of days until the uploaded file expires (leave blank for no auto-expiry)")
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = [("supplier", "expected_name")]
        indexes = [
            models.Index(fields=["supplier", "is_active"]),
            models.Index(fields=["expected_name"]),
        ]

    def __str__(self):
        return f"{self.expected_name} ({'required' if self.is_required else 'optional'}) for {self.supplier.name}"


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
