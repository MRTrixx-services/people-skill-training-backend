from django.urls import path
from . import views

app_name = 'notifications'

urlpatterns = [
    # User notification endpoints
    path('', views.NotificationListView.as_view(), name='notification-list'),
    path('<int:pk>/', views.NotificationDetailView.as_view(), name='notification-detail'),
    path('mark-all-read/', views.mark_all_read, name='mark-all-read'),
    path('unread-count/', views.unread_count, name='unread-count'),
    path('preferences/', views.NotificationPreferenceView.as_view(), name='notification-preferences'),
    
    # Admin notification endpoints
    path('admin/', views.AdminNotificationListView.as_view(), name='admin-notification-list'),
    path('admin/bulk-send/', views.send_bulk_notification, name='bulk-notification'),
    path('templates/', views.NotificationTemplateListView.as_view(), name='template-list'),
    path('templates/<int:pk>/', views.NotificationTemplateDetailView.as_view(), name='template-detail'),
]
