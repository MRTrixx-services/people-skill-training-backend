# apps/webinars/urls.py - ENHANCED with conditional webinar types and auto-conversion
from django.urls import path
from .views import (
    CategoryListView,
    CategoryDetailView,
    WebinarListView,
    WebinarDetailView,
    WebinarCreateView,
    WebinarUpdateView,
    WebinarDeleteView,
    MyWebinarsView,
    UpcomingWebinarsView,
    AvailableWebinarsView,  # ADDED: New view for recorded webinars
    WebinarResourceListView,
    WebinarReviewListView,
    webinar_stats,
    instructor_webinar_stats,
    update_webinar_analytics,
    sync_webinar_recordings,
    bulk_sync_recordings,  # ADDED: Bulk operations
)

app_name = 'webinars'

urlpatterns = [
    # Categories
    path('categories/', CategoryListView.as_view(), name='category_list'),
    path('categories/<int:pk>/', CategoryDetailView.as_view(), name='category_detail'),
    
    # Webinar Management - UPDATED: Enhanced with conditional types
    path('create/', WebinarCreateView.as_view(), name='webinar_create'),
    path('my/', MyWebinarsView.as_view(), name='my_webinars'),
    path('upcoming/', UpcomingWebinarsView.as_view(), name='upcoming_webinars'),
    path('available/', AvailableWebinarsView.as_view(), name='available_webinars'),  # ADDED: For recorded content
    
    # Statistics and analytics
    path('stats/', webinar_stats, name='webinar_stats'),
    path('instructor-stats/', instructor_webinar_stats, name='instructor_stats'),
    
    # Webinar CRUD operations - UPDATED: Proper order for no conflicts
    path('<int:pk>/update/', WebinarUpdateView.as_view(), name='webinar_update'),
    path('<int:pk>/delete/', WebinarDeleteView.as_view(), name='webinar_delete'),
    path('<int:pk>/analytics/update/', update_webinar_analytics, name='update_analytics'),
    
    # Recording operations - ENHANCED: Auto-conversion support
    path('<str:webinar_id>/sync-recordings/', sync_webinar_recordings, name='sync_recordings'),
    path('bulk-sync-recordings/', bulk_sync_recordings, name='bulk_sync_recordings'),  # ADDED: Admin bulk operations
    
    # Webinar Resources and Reviews
    path('<int:webinar_id>/resources/', WebinarResourceListView.as_view(), name='webinar_resources'),
    path('<int:webinar_id>/reviews/', WebinarReviewListView.as_view(), name='webinar_reviews'),
    
    # Webinar List and Detail - UPDATED: These come last to avoid conflicts
    path('', WebinarListView.as_view(), name='webinar_list'),
    path('<str:webinar_id>/', WebinarDetailView.as_view(), name='webinar_detail'),
]
