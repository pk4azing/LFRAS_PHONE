from django.contrib import admin
from .models import SupplierValidationRule


@admin.register(SupplierValidationRule)
class SupplierValidationRuleAdmin(admin.ModelAdmin):
    list_display = (
        "expected_name",
        "supplier",
        "evaluator",
        "required",
        "active",
        "created_at",
    )
    list_filter = ("evaluator", "supplier", "required", "active")
    search_fields = ("expected_name",)
