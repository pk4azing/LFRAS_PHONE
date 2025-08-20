from django.shortcuts import get_object_or_404
from django.http import FileResponse
from rest_framework import viewsets, permissions, status, generics
from django.core.files.storage import default_storage
from rest_framework.response import Response
from rest_framework import serializers
from django.utils.text import slugify
from rest_framework.parsers import MultiPartParser, FormParser
from rest_framework.decorators import action

import yaml

from django.contrib.auth import get_user_model
from .models import ClientCD, ClientCCD, ClientCDSMTPConfig
from .serializers import (
    ClientCDSerializer, ClientCDCreateSerializer,
    ClientCCDSerializer, ClientCCDCreateSerializer,
    ClientCDSMTPConfigSerializer, CDYamlUploadSerializer,
    CDConfigSchemaValidator, CDEmailTemplateYamlUploadSerializer,
    EmailTemplateSchemaValidator
)
from apps.audit.utils import add_audit
from apps.notifications.utils import add_notification
from .permissions import CanCreateCD, CanCreateCCD

User = get_user_model()

class CDViewSet(viewsets.ModelViewSet):
    queryset = ClientCD.objects.all()
    permission_classes = [permissions.IsAuthenticated]
    def get_serializer_class(self):
        return ClientCDCreateSerializer if self.action == "create" else ClientCDSerializer
    def get_permissions(self):
        if self.action == "create":
            return [permissions.IsAuthenticated(), CanCreateCD()]
        return super().get_permissions()
    
    def _assert_can_manage_this_cd(self, request, cd_obj: ClientCD):
        u = request.user
        if not u.is_authenticated:
            from rest_framework.exceptions import PermissionDenied
            raise PermissionDenied("Authentication required.")
        if u.role == "LD":
            return
        if u.role in ("CD_ADMIN", "CD_STAFF"):  # allow both Admin & User as you asked
            if getattr(u, "cd_id", None) == cd_obj.id:
                return
        from rest_framework.exceptions import PermissionDenied
        raise PermissionDenied("You cannot manage this CD.")

    @action(
        detail=True,
        methods=["post"],
        url_path="upload-config",
        parser_classes=[MultiPartParser, FormParser],
        permission_classes=[permissions.IsAuthenticated],
    )
    def upload_config(self, request, pk=None):
        """
        Upload YAML config for this CD.
        Saves to: tenants/<CD_TENANT_ID>/configs/<slug>.yaml
        Persists path to ClientCD.config_s3_path
        Emits Audit + Notifications
        """
        cd = get_object_or_404(ClientCD, pk=pk)
        self._assert_can_manage_this_cd(request, cd)

        ser = CDYamlUploadSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        f = ser.validated_data["file"]

        # Build S3 key
        filename = f.name or "config.yaml"
        base = slugify(filename.rsplit(".", 1)[0]) or "config"
        s3_key = f"tenants/{cd.tenant_id}/configs/{base}.yaml"

        saved_key = default_storage.save(s3_key, f)

        # (Optional) Read back to perform schema validation & fail-fast on bad YAML
        with default_storage.open(saved_key, "rb") as fh:
            try:
                cfg = yaml.safe_load(fh.read()) or {}
                # Enforce a minimal schema (optional)
                CDConfigSchemaValidator.validate(cfg)
            except serializers.ValidationError as e:
                # Remove bad file and surface error
                default_storage.delete(saved_key)
                return Response({"detail": str(e)}, status=status.HTTP_400_BAD_REQUEST)

        cd.config_s3_path = saved_key
        cd.save(update_fields=["config_s3_path"])

        add_audit(actor=request.user, cd=cd, event="CD_CONFIG_UPLOADED", meta={"s3_key": saved_key})
        # Notify all CD admins for this CD
        for poc in request.user.__class__.objects.filter(cd=cd, role__in=("CD_ADMIN",)):
            add_notification(poc, cd, f"Config updated for {cd.name}", "CONFIG_UPDATED", actor=request.user)

        return Response({"detail": "Config uploaded.", "s3_path": saved_key}, status=status.HTTP_200_OK)

    @action(
        detail=True,
        methods=["get"],
        url_path="config",
        permission_classes=[permissions.IsAuthenticated],
    )
    def read_config(self, request, pk=None):
        """
        Read YAML config for this CD.
        - ?raw=1 => returns raw YAML file content (text/yaml)
        - default => returns parsed YAML as JSON
        Permissions: LD or members of this CD (Admin/Staff) can read.
        """
        cd = get_object_or_404(ClientCD, pk=pk)

        # Read allowed to LD and to anyone belonging to this CD
        u = request.user
        if not u.is_authenticated or not (u.role == "LD" or getattr(u, "cd_id", None) == cd.id):
            from rest_framework.exceptions import PermissionDenied
            raise PermissionDenied("You cannot read this CD's config.")

        if not cd.config_s3_path:
            return Response({"detail": "No config uploaded."}, status=status.HTTP_404_NOT_FOUND)

        if request.query_params.get("raw") in ("1", "true", "yes"):
            # Stream raw YAML back
            fh = default_storage.open(cd.config_s3_path, "rb")
            return FileResponse(fh, content_type="text/yaml")

        # Return parsed YAML as JSON
        with default_storage.open(cd.config_s3_path, "rb") as fh:
            try:
                cfg = yaml.safe_load(fh.read()) or {}
            except yaml.YAMLError as e:
                return Response({"detail": f"Invalid YAML: {e}"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

        return Response(cfg, status=status.HTTP_200_OK)
    
    @action(
        detail=True,
        methods=["post"],
        url_path="upload-email-template",
        parser_classes=[MultiPartParser, FormParser],
        permission_classes=[permissions.IsAuthenticated],
    )
    def upload_email_template(self, request, pk=None):
        """
        Upload YAML email template for this CD.
        Saves to: tenants/<CD_TENANT_ID>/email_templates/<slug>.yaml
        Persists path to ClientCD.email_template_s3_path
        Emits Audit + Notifications
        """
        cd = get_object_or_404(ClientCD, pk=pk)
        self._assert_can_manage_this_cd(request, cd)  # LD or same-CD Admin/Staff

        ser = CDEmailTemplateYamlUploadSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        f = ser.validated_data["file"]

        filename = f.name or "email_template.yaml"
        base = slugify(filename.rsplit(".", 1)[0]) or "email_template"
        s3_key = f"tenants/{cd.tenant_id}/email_templates/{base}.yaml"

        saved_key = default_storage.save(s3_key, f)

        # Validate schema
        with default_storage.open(saved_key, "rb") as fh:
            try:
                cfg = yaml.safe_load(fh.read()) or {}
                EmailTemplateSchemaValidator.validate(cfg)
            except Exception as e:
                default_storage.delete(saved_key)
                return Response({"detail": f"Invalid template: {e}"}, status=status.HTTP_400_BAD_REQUEST)

        cd.email_template_s3_path = saved_key
        cd.save(update_fields=["email_template_s3_path"])

        add_audit(actor=request.user, cd=cd, event="CD_EMAIL_TEMPLATE_UPLOADED", meta={"s3_key": saved_key})
        for poc in request.user.__class__.objects.filter(cd=cd, role__in=("CD_ADMIN",)):
            add_notification(poc, cd, f"Email template updated for {cd.name}", "EMAIL_TEMPLATE_UPDATED", actor=request.user)

        return Response({"detail": "Email template uploaded.", "s3_path": saved_key}, status=status.HTTP_200_OK)


    @action(
        detail=True,
        methods=["get"],
        url_path="email-template",
        permission_classes=[permissions.IsAuthenticated],
    )
    def read_email_template(self, request, pk=None):
        """
        Read YAML email template for this CD.
        - ?raw=1 => returns raw YAML (text/yaml)
        - default => returns parsed YAML as JSON
        Permissions: LD or members of this CD (Admin/Staff) can read.
        """
        cd = get_object_or_404(ClientCD, pk=pk)

        u = request.user
        if not u.is_authenticated or not (u.role == "LD" or getattr(u, "cd_id", None) == cd.id):
            from rest_framework.exceptions import PermissionDenied
            raise PermissionDenied("You cannot read this CD's email template.")

        if not cd.email_template_s3_path:
            return Response({"detail": "No email template uploaded."}, status=status.HTTP_404_NOT_FOUND)

        if request.query_params.get("raw") in ("1", "true", "yes"):
            fh = default_storage.open(cd.email_template_s3_path, "rb")
            # Let FileResponse stream the content; consumer will get text/yaml
            from django.http import FileResponse
            return FileResponse(fh, content_type="text/yaml")

        with default_storage.open(cd.email_template_s3_path, "rb") as fh:
            try:
                cfg = yaml.safe_load(fh.read()) or {}
            except yaml.YAMLError as e:
                return Response({"detail": f"Invalid YAML: {e}"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

        return Response(cfg, status=status.HTTP_200_OK)

class CCDViewSet(viewsets.ModelViewSet):
    queryset = ClientCCD.objects.select_related("cd").all()
    permission_classes = [permissions.IsAuthenticated, CanCreateCCD]
    def get_serializer_class(self):
        return ClientCCDCreateSerializer if self.action == "create" else ClientCCDSerializer
    def get_queryset(self):
        qs = super().get_queryset()
        u = self.request.user
        if u.role == "LD":
            cd = self.request.query_params.get("cd")
            if cd:
                qs = qs.filter(cd_id=cd)
            return qs
        return qs.filter(cd_id=u.cd_id or -1)

class CDSMTPConfigView(generics.GenericAPIView):
    permission_classes = [permissions.IsAuthenticated]
    serializer_class = ClientCDSMTPConfigSerializer

    def get_cd(self):
        from .models import ClientCD
        cd_id = self.kwargs["cd_id"]
        cd = get_object_or_404(ClientCD, pk=cd_id)
        # Only LD or the same CD can access/modify its SMTP config
        u = self.request.user
        if u.role != "LD" and u.cd_id != cd.id:
            from rest_framework.exceptions import PermissionDenied
            raise PermissionDenied("You cannot access SMTP config for this CD.")
        return cd

    def get(self, request, cd_id):
        cd = self.get_cd()
        cfg = getattr(cd, "smtp_config", None)
        if not cfg:
            return Response({}, status=status.HTTP_200_OK)
        s = self.get_serializer(cfg)
        return Response(s.data)

    def post(self, request, cd_id):
        cd = self.get_cd()
        s = self.get_serializer(data=request.data, context={"cd": cd})
        s.is_valid(raise_exception=True)
        obj = s.save()
        return Response(self.get_serializer(obj).data, status=status.HTTP_200_OK)

    def put(self, request, cd_id):
        cd = self.get_cd()
        cfg = getattr(cd, "smtp_config", None)
        if not cfg:
            s = self.get_serializer(data=request.data, context={"cd": cd})
            s.is_valid(raise_exception=True)
            obj = s.save()
            return Response(self.get_serializer(obj).data, status=status.HTTP_200_OK)
        s = self.get_serializer(cfg, data=request.data)
        s.is_valid(raise_exception=True)
        obj = s.save()
        return Response(self.get_serializer(obj).data, status=status.HTTP_200_OK)

    patch = put  # allow partial