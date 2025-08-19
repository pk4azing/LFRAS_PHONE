from django.urls import path
from rest_framework.routers import DefaultRouter
from .views import ActivityViewSet, ActivityFileViewSet, CalendarFeedView

router = DefaultRouter()
router.register(r'', ActivityViewSet, basename='activities')
router.register(r'files', ActivityFileViewSet, basename='activity-files')

urlpatterns = [
    path('calendar/', CalendarFeedView.as_view(), name='activities-calendar'),
]
urlpatterns += router.urls