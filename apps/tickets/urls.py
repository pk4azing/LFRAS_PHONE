from rest_framework.routers import DefaultRouter
from .views import TicketViewSet, TicketCommentViewSet

router = DefaultRouter()
router.register(r'', TicketViewSet, basename='tickets')
router.register(r'comments', TicketCommentViewSet, basename='ticket-comments')

urlpatterns = router.urls