from django.shortcuts import get_object_or_404
from rest_framework import viewsets, permissions, status, generics
from rest_framework.response import Response
from rest_framework.decorators import action

from django.contrib.auth import get_user_model
from .models import ClientCD, ClientCCD, ClientCDSMTPConfig
from .serializers import (
    ClientCDSerializer, ClientCDCreateSerializer,
    ClientCCDSerializer, ClientCCDCreateSerializer,
    ClientCDSMTPConfigSerializer,
)
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