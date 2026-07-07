from django.urls import path
from .views import (
    OAuthProviderListView,
    OAuthProviderAdminView,
    OAuthProviderAdminDetailView,
    UserSocialAccountsView,
    LoginAttemptListView,
    get_authorization_url,
    oauth_callback,
    disconnect_social_account,
    set_primary_social_account,
    user_login_history,
    setup_default_providers,
)

app_name = 'oauth'

urlpatterns = [
    # Public OAuth endpoints
    path('providers/', OAuthProviderListView.as_view(), name='oauth_providers'),
    path('authorize/', get_authorization_url, name='get_authorization_url'),
    path('callback/', oauth_callback, name='oauth_callback'),
    
    # User social accounts
    path('accounts/', UserSocialAccountsView.as_view(), name='user_social_accounts'),
    path('accounts/<int:account_id>/disconnect/', disconnect_social_account, name='disconnect_social_account'),
    path('accounts/<int:account_id>/set-primary/', set_primary_social_account, name='set_primary_social_account'),
    path('login-history/', user_login_history, name='user_login_history'),
    
    # Admin endpoints
    path('admin/providers/', OAuthProviderAdminView.as_view(), name='oauth_providers_admin'),
    path('admin/providers/<int:pk>/', OAuthProviderAdminDetailView.as_view(), name='oauth_provider_admin_detail'),
    path('admin/login-attempts/', LoginAttemptListView.as_view(), name='login_attempts'),
    path('admin/setup-providers/', setup_default_providers, name='setup_default_providers'),
]
