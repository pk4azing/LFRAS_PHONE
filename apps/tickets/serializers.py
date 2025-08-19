from django.contrib.auth import get_user_model
from rest_framework import serializers
from .models import Ticket, TicketComment

User = get_user_model()

# -------- Light nested presenters --------
class _UserMiniSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ['id', 'email', 'username', 'name', 'role']

# -------- Read serializer --------
class TicketSerializer(serializers.ModelSerializer):
    created_by = _UserMiniSerializer(read_only=True)
    assigned_to = _UserMiniSerializer(read_only=True)

    class Meta:
        model = Ticket
        fields = [
            'id','cd','title','description','status','priority',
            'created_by','assigned_to','created_at','updated_at','closed_at'
        ]

# -------- Create/Update --------
class TicketWriteSerializer(serializers.ModelSerializer):
    assigned_to = serializers.PrimaryKeyRelatedField(
        queryset=User.objects.filter(role='LD'), required=False, allow_null=True
    )

    class Meta:
        model = Ticket
        fields = ['cd','title','description','priority','assigned_to','status']
        extra_kwargs = {
            # status optionally updateable; on create we’ll force OPEN
            'status': {'required': False},
        }

    def validate(self, attrs):
        req = self.context['request']
        u = req.user

        # Scope cd: CD/CCD must use their own cd; LD can choose
        if u.role in ('CD_ADMIN', 'CD_STAFF', 'CCD'):
            attrs['cd'] = u.cd
        else:
            # LD must provide cd
            if not attrs.get('cd'):
                raise serializers.ValidationError({'cd': 'This field is required for LD.'})

        # Enforce LD assignment when present
        assigned_to = attrs.get('assigned_to')
        if assigned_to and assigned_to.role != 'LD':
            raise serializers.ValidationError({'assigned_to': 'Tickets can only be assigned to LD users.'})

        # On create: force OPEN
        if self.instance is None:
            attrs['status'] = 'OPEN'

        return attrs

    def create(self, validated):
        req = self.context['request']
        ticket = Ticket.objects.create(
            created_by=req.user,
            **validated
        )
        return ticket

    def update(self, instance, validated):
        # Allow normal partial/full updates; closed_at handled in view or signals
        for k, v in validated.items():
            setattr(instance, k, v)
        instance.save()
        return instance

# -------- Comments --------
class TicketCommentSerializer(serializers.ModelSerializer):
    author = _UserMiniSerializer(read_only=True)

    class Meta:
        model = TicketComment
        fields = ['id','ticket','author','message','created_at']
        extra_kwargs = {'ticket': {'write_only': True}}

    def create(self, validated):
        req = self.context['request']
        return TicketComment.objects.create(author=req.user, **validated)