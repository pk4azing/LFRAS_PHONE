from rest_framework import viewsets, permissions, status, filters
from rest_framework.decorators import action
from rest_framework.response import Response
from django.db.models import Q
from django.contrib.auth import get_user_model

from .models import Notification
from .serializers import NotificationSerializer

User = get_user_model()

class NotificationViewSet(viewsets.ModelViewSet):
    """
    /api/v1/notifications/           (GET: list my notifications, POST: create test)
    /api/v1/notifications/<id>/      (GET/DELETE/PATCH)
    /api/v1/notifications/<id>/mark-read/   (POST)
    /api/v1/notifications/mark-all-read/    (POST)
    /api/v1/notifications/unread-count/     (GET)
    """
    permission_classes = [permissions.IsAuthenticated]
    serializer_class = NotificationSerializer
    filter_backends = [filters.SearchFilter]
    search_fields = ["message", "event"]

    def get_queryset(self):
        qs = Notification.objects.select_related("recipient", "cd").filter(recipient=self.request.user)
        # Optional filtering
        if (unread := self.request.query_params.get("unread")):
            if unread.lower() in ("true", "1", "yes"):
                qs = qs.filter(is_read=False)
        if (event := self.request.query_params.get("event")):
            qs = qs.filter(event=event)
        if (level := self.request.query_params.get("level")):
            qs = qs.filter(level=level)
        if (q := self.request.query_params.get("q")):
            qs = qs.filter(Q(message__icontains=q) | Q(event__icontains=q))
        return qs.order_by("-created_at")

    def perform_create(self, serializer):
        # Creating notifications is usually done via utils.add_notification()
        # This allows a simple manual/test creation:
        serializer.save(recipient=self.request.user)

    @action(detail=True, methods=["post"], url_path="mark-read")
    def mark_read(self, request, pk=None):
        obj = self.get_object()
        if not obj.is_read:
            obj.is_read = True
            obj.save(update_fields=["is_read"])
        return Response({"detail": "Notification marked as read"}, status=status.HTTP_200_OK)

    @action(detail=False, methods=["post"], url_path="mark-all-read")
    def mark_all_read(self, request):
        qs = self.get_queryset().filter(is_read=False)
        updated = qs.update(is_read=True)
        return Response({"detail": f"{updated} notifications marked as read"}, status=status.HTTP_200_OK)

    @action(detail=False, methods=["get"], url_path="unread-count")
    def unread_count(self, request):
        count = self.get_queryset().filter(is_read=False).count()
        return Response({"unread": count}, status=status.HTTP_200_OK)