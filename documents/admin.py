from django.contrib import admin
from django.utils import timezone
from .models import Document


class ExpiryStatusFilter(admin.SimpleListFilter):
    title = "expiry status"
    parameter_name = "exp_status"

    def lookups(self, request, model_admin):
        return [
            ("soon", "Expiring in 30 days"),
            ("expired", "Expired"),
            ("noexp", "No expiry"),
        ]

    def queryset(self, request, queryset):
        now = timezone.now()
        if self.value() == "soon":
            return queryset.filter(
                expires_at__isnull=False,
                expires_at__lte=now + timezone.timedelta(days=30),
                expires_at__gte=now,
            )
        if self.value() == "expired":
            return queryset.filter(expires_at__isnull=False, expires_at__lt=now)
        if self.value() == "noexp":
            return queryset.filter(expires_at__isnull=True)
        return queryset


@admin.register(Document)
class DocumentAdmin(admin.ModelAdmin):
    list_display = (
        "title",
        "category",
        "evaluator",
        "supplier",
        "uploaded_by",
        "uploaded_at",
        "expires_at",
        "is_active",
    )
    list_filter = ("category", "evaluator", "supplier", "is_active", ExpiryStatusFilter)
    search_fields = ("title", "file")
