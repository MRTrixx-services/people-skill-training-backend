from django.urls import path
from rest_framework_simplejwt.views import TokenRefreshView

from .views import (
    CustomTokenObtainPairView,
    UserRegistrationView,
    logout_view,
    UserProfileView,
    PasswordChangeView,
    PasswordResetRequestView,
    PasswordResetConfirmView,
    verify_token,
    verify_email,
    resend_verification_email,
    check_verification_status,
    create_profile,  # NEW
)

app_name = 'authentication'

urlpatterns = [
    # Authentication endpoints
    path('login/', CustomTokenObtainPairView.as_view(), name='login'),
    path('register/', UserRegistrationView.as_view(), name='register'),
    path('logout/', logout_view, name='logout'),
    path('refresh/', TokenRefreshView.as_view(), name='token_refresh'),
    path('verify/', verify_token, name='verify_token'),
    
    path('verify-email/', verify_email, name='verify_email'),
    path('resend-verification/', resend_verification_email, name='resend_verification'),
    path('check-verification/', check_verification_status, name='check_verification'),
    
    # Profile endpoints
    path('profile/', UserProfileView.as_view(), name='profile'),
    path('create-profile/', create_profile, name='create_profile'),  # NEW
    
    # Password management endpoints
    path('change-password/', PasswordChangeView.as_view(), name='change_password'),
    path('reset-password/', PasswordResetRequestView.as_view(), name='reset_password'),
    path('reset-password/confirm/', PasswordResetConfirmView.as_view(), name='reset_password_confirm'),
]
