# apps/integrations/urls.py - ENHANCED with all conditional webinar endpoints
from django.urls import path
from .views import (
    ZoomCredentialsView,
    ZoomCredentialsDetailView,
    ZoomMeetingListView,
    ZoomWebinarListView,
    ZoomRecordingListView,
    ZoomWebhookEventListView,
    ZoomIntegrationLogListView,
    zoom_connection_status,
    create_zoom_meeting,
    update_zoom_meeting,
    delete_zoom_meeting,
    sync_zoom_recordings,
    force_recording_check,
    bulk_sync_recordings,
    get_webinar_zoom_status,
    zoom_webhook,
     # NEW: Search-related views
    search_zoom_meetings,
    link_existing_zoom_meeting,
    get_webinar_meeting_suggestions,
    test_list_all_zoom_meetings,
    replace_zoom_meeting,
    list_zoom_cloud_recordings,
    link_recording_to_webinar
)

app_name = 'integrations'

urlpatterns = [
    # Zoom credentials management (admin only)
    path('credentials/', ZoomCredentialsView.as_view(), name='zoom_credentials'),
    path('credentials/<int:pk>/', ZoomCredentialsDetailView.as_view(), name='zoom_credentials_detail'),
    
    # Connection and status
    path('connection/status/', zoom_connection_status, name='zoom_connection_status'),
    path('webinar/<str:webinar_id>/zoom-status/', get_webinar_zoom_status, name='webinar_zoom_status'),
     # NEW: Meeting search and linking endpoints
    path('meetings/search/', search_zoom_meetings, name='search_zoom_meetings'),
    path('meetings/link/', link_existing_zoom_meeting, name='link_existing_meeting'),
    path('webinars/<int:webinar_id>/meeting-suggestions/', get_webinar_meeting_suggestions, name='meeting_suggestions'),
    path('meetings/test-list-all/', test_list_all_zoom_meetings, name='test_list_all'),

    # Zoom meetings management (for live webinars)
    path('meetings/', ZoomMeetingListView.as_view(), name='zoom_meetings'),
    path('meetings/create/', create_zoom_meeting, name='create_zoom_meeting'),
    path('meetings/<str:meeting_id>/update/', update_zoom_meeting, name='update_zoom_meeting'),
    path('meetings/<str:meeting_id>/delete/', delete_zoom_meeting, name='delete_zoom_meeting'),
    path('meetings/replace/', replace_zoom_meeting, name='replace_zoom_meeting'),
   
    # Zoom webinars management (for large live events)
    path('webinars/', ZoomWebinarListView.as_view(), name='zoom_webinars'),
    
    # Recordings management and auto-conversion
    path('recordings/', ZoomRecordingListView.as_view(), name='zoom_recordings'),
    path('recordings/sync/<int:webinar_id>/', sync_zoom_recordings, name='sync_zoom_recordings'),
    path('recordings/force-check/<str:webinar_id>/', force_recording_check, name='force_recording_check'),
    path('recordings/bulk-sync/', bulk_sync_recordings, name='bulk_sync_recordings'),
    
    # Admin monitoring endpoints
    path('webhook/events/', ZoomWebhookEventListView.as_view(), name='zoom_webhook_events'),
    path('logs/', ZoomIntegrationLogListView.as_view(), name='zoom_integration_logs'),
    path('recordings/list/', list_zoom_cloud_recordings, name='list_zoom_cloud_recordings'),
    path('recordings/link/', link_recording_to_webinar, name='link_recording_to_webinar'),

    # Webhook endpoint (for external Zoom service)
    path('webhook/', zoom_webhook, name='zoom_webhook'),
]
