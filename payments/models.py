from django.db import models
from django.utils import timezone
from decimal import Decimal

PLAN_CHOICES = [
    ("enterprise", "Enterprise ($9,999/yr)"),
    ("professional", "Professional ($8,888/yr)"),
    ("essentials", "Essentials ($7,777/yr)"),
]

PLAN_DEFAULT_AMOUNTS = {
    "enterprise": Decimal("9999.00"),
    "professional": Decimal("8888.00"),
    "essentials": Decimal("7777.00"),
}

STATUS_CHOICES = [
    ("pending", "Pending"),
    ("active", "Active"),
    ("cancelled", "Cancelled"),
    ("expired", "Expired"),
]

PAYMENT_METHODS = [
    ("manual", "Manual"),
    ("wire", "Wire"),
    ("ach", "ACH"),
    ("card", "Card"),
    ("other", "Other"),
]


class PaymentRecord(models.Model):
    """Subscription-like record for an Evaluator"""

    evaluator = models.ForeignKey(
        "tenants.Evaluator", on_delete=models.CASCADE, related_name="payment_records"
    )
    plan = models.CharField(max_length=20, choices=PLAN_CHOICES)
    amount_yearly = models.DecimalField(max_digits=10, decimal_places=2)
    currency = models.CharField(max_length=8, default="USD")

    status = models.CharField(max_length=12, choices=STATUS_CHOICES, default="pending")
    start_date = models.DateField(default=timezone.localdate)
    end_date = models.DateField(null=True, blank=True)

    subscription_id = models.CharField(max_length=64, blank=True)  # your internal id
    notes = models.TextField(blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    created_by = models.ForeignKey(
        "accounts.User",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="+",
    )
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.evaluator.name} — {self.get_plan_display()}"

    def ensure_end_date_default(self):
        if not self.end_date and self.start_date:
            self.end_date = self.start_date.replace(year=self.start_date.year + 1)


class PaymentTransaction(models.Model):
    record = models.ForeignKey(
        PaymentRecord, on_delete=models.CASCADE, related_name="transactions"
    )
    paid_on = models.DateField(default=timezone.localdate)
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    currency = models.CharField(max_length=8, default="USD")

    method = models.CharField(max_length=12, choices=PAYMENT_METHODS, default="manual")
    external_id = models.CharField(max_length=64, blank=True)  # gateway ref if any
    notes = models.TextField(blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    created_by = models.ForeignKey(
        "accounts.User",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="+",
    )

    class Meta:
        ordering = ["-paid_on", "-id"]

    def __str__(self):
        return f"{self.record_id} — {self.amount} {self.currency} on {self.paid_on}"
