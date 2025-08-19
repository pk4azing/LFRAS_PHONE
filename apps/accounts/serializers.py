# apps/accounts/serializers.py
from django.contrib.auth import authenticate, get_user_model
from rest_framework import serializers

User = get_user_model()


class UserSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        exclude = ["password"]  # Don’t leak password hashes


class LoginSerializer(serializers.Serializer):
    email = serializers.EmailField()
    password = serializers.CharField(write_only=True)
    user = serializers.HiddenField(default=None)

    def validate(self, data):
        email = data.get("email")
        password = data.get("password")
        user = authenticate(request=self.context.get("request"),
                            email=email, password=password)
        if not user:
            raise serializers.ValidationError("Invalid credentials")
        if not user.is_active:
            raise serializers.ValidationError("User account is disabled")
        data["user"] = user
        return data


class MeUpdateSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ["first_name", "last_name", "username", "email",
                  "address", "city", "phone"]


class CDEmployeeCreateSerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True)

    class Meta:
        model = User
        fields = ["id", "email", "password", "first_name", "last_name",
                  "role", "cd"]

    def create(self, validated_data):
        password = validated_data.pop("password")
        user = User.objects.create(**validated_data)
        user.set_password(password)
        user.save()
        return user


class CDEmployeeUpdateSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ["first_name", "last_name", "email", "username", "role"]


# ---------------------------
# CCD Serializer (one login per CCD)
# ---------------------------
class CCDCreateSerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True)

    class Meta:
        model = User
        fields = ["id", "email", "password", "first_name", "last_name", "cd"]

    def validate(self, attrs):
        cd = attrs.get("cd")
        if cd and User.objects.filter(cd=cd, role="CCD").exists():
            raise serializers.ValidationError("A CCD user already exists for this CD.")
        return attrs

    def create(self, validated_data):
        password = validated_data.pop("password")
        user = User.objects.create(**validated_data, role="CCD")
        user.set_password(password)
        user.save()
        return user