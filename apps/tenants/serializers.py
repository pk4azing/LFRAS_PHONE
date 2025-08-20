from django.contrib.auth import get_user_model
from rest_framework import serializers
from rest_framework.exceptions import ValidationError, PermissionDenied
from .models import ClientCD, ClientCCD, ClientCDSMTPConfig
from .utils import gen_password, gen_tenant_id, email_with_tenant, s3_ensure_paths
from apps.notifications.utils import add_notification
from apps.audit.utils import add_audit
import yaml

User = get_user_model()

class ClientCDSerializer(serializers.ModelSerializer):
    class Meta:
        model = ClientCD
        fields = ["id", "tenant_id", "name", "poc_name", "poc_email", "poc_phone", "created_at"]
        read_only_fields = ["id", "tenant_id", "created_at"]


class ClientCDCreateSerializer(serializers.ModelSerializer):
    """
    Creates a CD tenant and **automatically** creates a CD Admin user for the POC.
    Emails credentials via per-CD SMTP (if configured after), Audit + Notification, S3 bootstrap.
    """
    class Meta:
        model = ClientCD
        fields = ["name", "poc_name", "poc_email", "poc_phone"]

    def create(self, validated_data):
        # Create CD tenant with generated tenant_id
        next_seq = (ClientCD.objects.order_by("-id").first().id + 1) if ClientCD.objects.exists() else 1
        cd = ClientCD.objects.create(tenant_id=gen_tenant_id("CD", next_seq), **validated_data)

        # Create POC admin user
        username = f"cd_{cd.id:05d}"
        password = gen_password()
        user = User.objects.create(
            email=cd.poc_email,
            username=username,
            name=cd.poc_name,
            role="CD_ADMIN",
            cd=cd,
        )
        user.set_password(password)
        user.save()

        # Email credentials
        subject = f"LFRAS: CD Tenant created ({cd.name})"
        text = (f"Hello {cd.poc_name},\n\nYour CD tenant has been created.\n"
                f"Tenant ID: {cd.tenant_id}\n"
                f"Login Email: {user.email}\nUsername: {user.username}\nPassword: {password}\n\n"
                f"Please change your password on first login.")
        html = (f"<p>Hello {cd.poc_name},</p>"
                f"<p>Your CD tenant has been created.</p>"
                f"<p><b>Tenant ID:</b> {cd.tenant_id}<br>"
                f"<b>Login Email:</b> {user.email}<br>"
                f"<b>Username:</b> {user.username}<br>"
                f"<b>Password:</b> {password}</p>"
                f"<p>Please change your password on first login.</p>")
        email_with_tenant(cd, user.email, subject, text, html)

        # S3 bootstrap
        s3_ensure_paths(cd)

        # Notify + Audit
        add_notification(user, cd, f"CD tenant {cd.name} created.", "CD_CREATED", actor=self.context["request"].user)
        add_audit(actor=self.context["request"].user, cd=cd, event="CD_CREATED", target_user=user, meta={"cd_id": cd.id, "tenant_id": cd.tenant_id})

        return cd


class ClientCCDSerializer(serializers.ModelSerializer):
    class Meta:
        model = ClientCCD
        fields = ["id", "tenant_id", "cd", "org_name", "email", "created_at"]
        read_only_fields = ["id", "tenant_id", "created_at"]


class ClientCCDCreateSerializer(serializers.ModelSerializer):
    """
    Creates a CCD tenant and **exactly one CCD user** for login.
    LD may pass `cd`. CD_ADMIN is auto-scoped to their own `cd`.
    """
    class Meta:
        model = ClientCCD
        fields = ["cd", "org_name", "email"]

    def validate(self, attrs):
        u = self.context["request"].user
        if u.role == "LD":
            if not attrs.get("cd"):
                raise ValidationError({"cd": "This field is required for LD."})
        elif u.role in ("CD_ADMIN",):
            if not u.cd_id:
                raise PermissionDenied("Your account is not linked to a CD.")
            attrs["cd"] = u.cd
        else:
            raise PermissionDenied("Only LD or CD Admins can create CCD tenants.")

        # Ensure no duplicate CCD user under same CD
        cd = attrs["cd"]
        email = attrs.get("email")
        if email and User.objects.filter(cd=cd, role="CCD", email__iexact=email).exists():
            raise ValidationError({"email": "A CCD user with this email already exists for this CD."})
        return attrs

    def create(self, validated_data):
        cd = validated_data["cd"]

        # Create CCD tenant with generated tenant_id
        next_seq = (ClientCCD.objects.order_by("-id").first().id + 1) if ClientCCD.objects.exists() else 1
        ccd = ClientCCD.objects.create(tenant_id=gen_tenant_id("CCD", next_seq), **validated_data)

        # Create exclusive CCD user
        username = f"ccd_{cd.id:05d}_{ccd.id:05d}"
        password = gen_password()
        ccd_user = User.objects.create(
            email=ccd.email,
            username=username,
            name=ccd.org_name,
            role="CCD",
            cd=cd,
        )
        ccd_user.set_password(password)
        ccd_user.save()

        # Email credentials via CD SMTP
        subject = f"LFRAS: CCD tenant created ({ccd.org_name})"
        text = (f"Hello,\n\nYour CCD access has been created under {cd.name}.\n"
                f"CCD Tenant ID: {ccd.tenant_id}\n"
                f"Login Email: {ccd_user.email}\nUsername: {ccd_user.username}\nPassword: {password}\n\n"
                f"Please change your password on first login.")
        html = (f"<p>Hello,</p><p>Your CCD access has been created under <b>{cd.name}</b>.</p>"
                f"<p><b>CCD Tenant ID:</b> {ccd.tenant_id}<br>"
                f"<b>Login Email:</b> {ccd_user.email}<br>"
                f"<b>Username:</b> {ccd_user.username}<br>"
                f"<b>Password:</b> {password}</p>"
                f"<p>Please change your password on first login.</p>")
        email_with_tenant(cd, ccd_user.email, subject, text, html)

        # S3 bootstrap for CCD
        s3_ensure_paths(cd, ccd)

        # Notify POCs + Audit
        add_notification(ccd_user, cd, f"CCD tenant {ccd.org_name} created.", "CCD_CREATED", actor=self.context["request"].user)
        for poc in User.objects.filter(cd=cd, role="CD_ADMIN"):
            add_notification(poc, cd, f"CCD {ccd.org_name} created.", "CCD_CREATED", actor=self.context["request"].user)

        add_audit(actor=self.context["request"].user, cd=cd, event="CCD_CREATED", target_user=ccd_user, meta={"ccd_id": ccd.id, "tenant_id": ccd.tenant_id})

        return ccd


class ClientCDSMTPConfigSerializer(serializers.ModelSerializer):
    class Meta:
        model = ClientCDSMTPConfig
        fields = ["host", "port", "username", "password", "use_tls", "use_ssl", "from_email"]

    def create(self, validated_data):
        cd = self.context["cd"]
        obj, _ = ClientCDSMTPConfig.objects.update_or_create(cd=cd, defaults=validated_data)
        return obj

    def update(self, instance, validated_data):
        for k, v in validated_data.items():
            setattr(instance, k, v)
        instance.save()
        return instance
    

class CDYamlUploadSerializer(serializers.Serializer):
    file = serializers.FileField()

    def validate_file(self, f):
        # 5MB cap (adjust if needed)
        if f.size > 5 * 1024 * 1024:
            raise serializers.ValidationError("File too large (max 5MB).")

        name = f.name or "config.yaml"
        ext = (name.rsplit(".", 1)[-1] or "").lower()
        if ext not in ("yaml", "yml"):
            raise serializers.ValidationError("Only .yaml or .yml files are allowed.")

        # Parse once to catch syntax errors (also protects from upload of non-yaml)
        try:
            # IMPORTANT: read then reset cursor for storage to re-read stream
            data = f.read()
            yaml.safe_load(data)
            f.seek(0)
        except yaml.YAMLError as e:
            raise serializers.ValidationError(f"Invalid YAML: {e}")

        return f
    

class CDConfigSchemaValidator:
    REQUIRED_TOP_LEVEL_KEYS = {"files"}  # e.g., files: [ {name, type, validations: [...]}, ... ]

    @classmethod
    def validate(cls, cfg: dict):
        if not isinstance(cfg, dict):
            raise serializers.ValidationError("Config root must be a mapping/object.")
        missing = cls.REQUIRED_TOP_LEVEL_KEYS - set(cfg.keys())
        if missing:
            raise serializers.ValidationError(f"Missing required keys: {', '.join(sorted(missing))}")

        files = cfg.get("files", [])
        if not isinstance(files, list) or not files:
            raise serializers.ValidationError("`files` must be a non-empty list.")
        for i, item in enumerate(files, start=1):
            if not isinstance(item, dict):
                raise serializers.ValidationError(f"`files[{i}]` must be an object.")
            if "name" not in item or "type" not in item:
                raise serializers.ValidationError(f"`files[{i}]` must include `name` and `type`.")
            # Optionally validate validations array
            vals = item.get("validations", [])
            if vals and not isinstance(vals, list):
                raise serializers.ValidationError(f"`files[{i}].validations` must be a list.")
            

class CDEmailTemplateYamlUploadSerializer(serializers.Serializer):
    file = serializers.FileField()

    def validate_file(self, f):
        if f.size > 5 * 1024 * 1024:
            raise serializers.ValidationError("File too large (max 5MB).")
        name = f.name or "email_template.yaml"
        ext = (name.rsplit(".", 1)[-1] or "").lower()
        if ext not in ("yaml", "yml"):
            raise serializers.ValidationError("Only .yaml or .yml files are allowed.")
        try:
            data = f.read()
            yaml.safe_load(data)
            f.seek(0)
        except yaml.YAMLError as e:
            raise serializers.ValidationError(f"Invalid YAML: {e}")
        return f


class EmailTemplateSchemaValidator:
    """
    Minimal schema:
    - subject: str (required)
    - body_text: str (optional if body_html provided)
    - body_html: str (optional if body_text provided)
    - placeholders: list[str] (optional, for documentation of variables like {{tenant}}, {{period}}, etc.)
    """
    @classmethod
    def validate(cls, cfg: dict):
        if not isinstance(cfg, dict):
            raise serializers.ValidationError("Template root must be a mapping/object.")
        subject = cfg.get("subject")
        body_text = cfg.get("body_text")
        body_html = cfg.get("body_html")
        if not subject or not isinstance(subject, str):
            raise serializers.ValidationError("`subject` is required and must be a string.")
        if not (isinstance(body_text, str) or isinstance(body_html, str)):
            raise serializers.ValidationError("Provide at least one of `body_text` or `body_html`.")
        ph = cfg.get("placeholders")
        if ph is not None and not (isinstance(ph, list) and all(isinstance(x, str) for x in ph)):
            raise serializers.ValidationError("`placeholders` must be a list of strings if provided.")
        return cfg