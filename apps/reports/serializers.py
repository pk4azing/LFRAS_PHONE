from django.contrib.auth import get_user_model
from rest_framework import serializers
from .models import Report

User = get_user_model()


class UserMiniSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ["id", "email", "username", "name", "role"]


class ReportSerializer(serializers.ModelSerializer):
    requested_by = UserMiniSerializer(read_only=True)

    class Meta:
        model = Report
        fields = [
            "id", "cd", "requested_by", "report_type", "status",
            "s3_key", "requested_at", "ready_at", "failed_reason",
        ]
        read_only_fields = [
            "id", "requested_by", "status", "s3_key", "requested_at", "ready_at", "failed_reason",
        ]


class ReportRequestSerializer(serializers.ModelSerializer):
    """Create a report request; LD must pass cd, others auto‑scoped."""
    class Meta:
        model = Report
        fields = ["cd", "report_type"]
        extra_kwargs = {"report_type": {"required": True}}

    def validate(self, attrs):
        u = self.context["request"].user
        if u.role != "LD":
            attrs["cd"] = u.cd
        else:
            if not attrs.get("cd"):
                raise serializers.ValidationError({"cd": "This field is required for LD."})
        return attrs

    def create(self, validated_data):
        req = self.context["request"]
        return Report.objects.create(
            requested_by=req.user,
            status="REQUESTED",
            **validated_data
        )


class ReportUpdateSerializer(serializers.ModelSerializer):
    """Patch report status / keys; used by LD or backoffice flows."""
    class Meta:
        model = Report
        fields = ["status", "s3_key", "ready_at", "failed_reason"]
        extra_kwargs = {
            "status": {"required": False},
            "s3_key": {"required": False, "allow_blank": True},
            "ready_at": {"required": False},
            "failed_reason": {"required": False, "allow_blank": True},
        }

    def validate_status(self, value):
        if value and value not in {"REQUESTED", "PROCESSING", "READY", "FAILED"}:
            raise serializers.ValidationError("Invalid status")
        return value

    def update(self, instance, validated):
        for k, v in validated.items():
            setattr(instance, k, v)
        instance.save()
        return instance