from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import CDViewSet, CCDViewSet, CDSMTPConfigView

router = DefaultRouter()
router.register(r"cd", CDViewSet, basename="cd")
router.register(r"ccd", CCDViewSet, basename="ccd")

urlpatterns = [
    *router.urls,
    path("cd/<int:cd_id>/smtp-config/", CDSMTPConfigView.as_view(), name="cd-smtp-config"),
]