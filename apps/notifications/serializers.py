from rest_framework import serializers
from django.contrib.auth import get_user_model
from .models import Notification

User = get_user_model()

class RecipientMiniSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ["id", "email", "username", "name", "role"]

class NotificationSerializer(serializers.ModelSerializer):
    recipient = RecipientMiniSerializer(read_only=True)

    class Meta:
        model = Notification
        fields = ["id", "recipient", "cd", "message", "event", "level", "is_read", "meta", "created_at"]
        read_only_fields = ["id", "recipient", "created_at"]