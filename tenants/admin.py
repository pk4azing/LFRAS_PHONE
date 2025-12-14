from django.contrib import admin
from .models import Evaluator, Supplier, PaymentTransaction


@admin.register(PaymentTransaction)
class PaymentAdmin(admin.ModelAdmin):
    list_display = ("payment_id", "amount_cents", "currency", "paid_at")
    search_fields = ("payment_id",)


@admin.register(Evaluator)
class EvaluatorAdmin(admin.ModelAdmin):
    list_display = (
        "name",
        "email_domain",
        "subdomain",
        "plan",
        "is_active",
        "poc_email",
    )
    search_fields = ("name", "email_domain", "poc_email", "subdomain")
    list_filter = ("plan", "is_active")


@admin.register(Supplier)
class SupplierAdmin(admin.ModelAdmin):
    list_display = ("name", "evaluator", "primary_email", "is_active", "created_at")
    list_filter = ("evaluator", "is_active")
    search_fields = ("name", "primary_email")


