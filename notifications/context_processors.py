from .models import Notification


def notifications_context(request):
    """Provide recent notifications + unread count without filtering a sliced QS."""
    user = getattr(request, "user", None)
    if not user or not user.is_authenticated:
        return {}

    base_qs = Notification.objects.filter(recipient=user)
    # Compute unread on the full queryset (no slice yet)
    unread = base_qs.filter(read_at__isnull=True).count()
    # Slice only after all filters are applied
    recent = list(base_qs.order_by("-created_at")[:10])

    return {
        "notifications_recent": recent,
        "notifications_unread": unread,
    }
