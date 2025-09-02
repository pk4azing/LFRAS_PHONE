# payments/admin.py
from django.contrib import admin
from .models import PaymentRecord, PaymentTransaction


@admin.register(PaymentRecord)
class PaymentRecordAdmin(admin.ModelAdmin):
    list_display = (
        "evaluator",
        "plan",
        "amount_yearly",
        "status",
        "start_date",
        "end_date",
        "created_at",
    )
    list_filter = ("plan", "status", "currency")
    search_fields = ("evaluator__name", "subscription_id", "notes")


@admin.register(PaymentTransaction)
class PaymentTransactionAdmin(admin.ModelAdmin):
    list_display = (
        "record",
        "paid_on",
        "amount",
        "currency",
        "method",
        "external_id",
        "created_at",
    )
    list_filter = ("method", "currency")
    search_fields = ("external_id", "notes", "record__evaluator__name")
