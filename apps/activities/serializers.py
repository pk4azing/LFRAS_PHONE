from django.contrib.auth import get_user_model
from rest_framework import serializers
from .models import Activity, ActivityFile

User = get_user_model()

# ---- presenters ----
class UserMiniSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ['id', 'email', 'username', 'name', 'role']

class ActivityFileSerializer(serializers.ModelSerializer):
    class Meta:
        model = ActivityFile
        fields = [
            'id','activity','original_name','document_type','s3_key',
            'size_bytes','uploaded_at','validation_status','validation_message',
            'expiry_at','reminder_due'
        ]
        extra_kwargs = {'activity': {'write_only': True}}

class ActivitySerializer(serializers.ModelSerializer):
    ccd = UserMiniSerializer(read_only=True)
    files = ActivityFileSerializer(many=True, read_only=True)

    class Meta:
        model = Activity
        fields = [
            'id','cd','ccd','period','status','created_at','completed_at','s3_prefix','files'
        ]

# ---- create/update ----
class ActivityWriteSerializer(serializers.ModelSerializer):
    ccd = serializers.PrimaryKeyRelatedField(
        queryset=User.objects.filter(role='CCD'),
        required=False, allow_null=True
    )

    class Meta:
        model = Activity
        fields = ['cd','ccd','period','status','s3_prefix']
        extra_kwargs = {'status': {'required': False}}

    def validate(self, attrs):
        u = self.context['request'].user
        if u.role != 'LD':
            # non-LD must stick to their tenant
            attrs['cd'] = u.cd
        else:
            if not attrs.get('cd'):
                raise serializers.ValidationError({'cd': 'CD is required for LD.'})
        # default status on create
        if self.instance is None and not attrs.get('status'):
            attrs['status'] = 'in_progress'
        return attrs

class ActivityFileWriteSerializer(serializers.ModelSerializer):
    class Meta:
        model = ActivityFile
        fields = [
            'activity','original_name','document_type','s3_key',
            'size_bytes','validation_status','validation_message','expiry_at','reminder_due'
        ]