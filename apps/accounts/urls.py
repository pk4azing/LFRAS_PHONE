from django.urls import path
from rest_framework_simplejwt.views import TokenRefreshView, TokenVerifyView
from .views import LoginView, MeView, ChangePasswordView, ForgotPasswordView, ResetPasswordView, CDEmployeeViewSet
from rest_framework.routers import DefaultRouter
from .views import CDEmployeeViewSet


router = DefaultRouter()
router.register(r'employees', CDEmployeeViewSet, basename='employee')
urlpatterns = [
    path('login/', LoginView.as_view(), name='accounts-login'),
    path('me/', MeView.as_view(), name='accounts-me'),
    
    path('change-password/', ChangePasswordView.as_view(), name='accounts-change-password'),
    path('forgot-password/', ForgotPasswordView.as_view(), name='accounts-forgot-password'),
    path('reset-password/', ResetPasswordView.as_view(), name='accounts-reset-password'),

    # JWT helpers
    path('token/refresh/', TokenRefreshView.as_view(), name='token_refresh'),
    path('token/verify/', TokenVerifyView.as_view(), name='token_verify'),
    *router.urls,
]