from django.urls import path
from . import views

app_name = 'platforms'

urlpatterns = [
    # Public endpoints (require API key)
    path('config/', views.get_platform_config, name='config'),
    
    # Admin endpoints
    path('', views.list_platforms, name='list'),
    path('create/', views.create_platform, name='create'),
    path('<int:pk>/', views.get_platform_detail, name='detail'),
    path('<int:pk>/update/', views.update_platform, name='update'),
    path('<int:pk>/delete/', views.delete_platform, name='delete'),
    path('<int:pk>/regenerate-key/', views.regenerate_api_key, name='regenerate-key'),
    path('<int:pk>/stats/', views.get_platform_stats, name='stats'),
    path('<int:pk>/logs/', views.get_platform_api_logs, name='logs'),
    path('<int:pk>/maintenance/', views.toggle_platform_maintenance, name='toggle-maintenance'),
    path('<int:pk>/toggle-status/', views.toggle_platform_status, name='toggle-status'),
    path('<int:pk>/set-default/', views.set_default_platform, name='set-default'),
    path('stats/recalculate/', views.recalculate_all_stats, name='recalculate-stats'),
    
    path('settings/current/', views.get_current_platform_settings, name='current-settings'),
    path('settings/update/', views.update_platform_settings, name='update-settings'),
    path('settings/test-email/', views.test_email_connection_view, name='test-email'),
    path('settings/upload-logo/', views.upload_logo, name='upload-logo'),
    path('settings/upload-favicon/', views.upload_favicon, name='upload-favicon'),
]