from django.urls import path
from . import views

app_name = 'analytics'

urlpatterns = [
    # Dashboard endpoints
    path('dashboard/', views.admin_dashboard_stats, name='admin-dashboard-stats'),
    path('dashboard/revenue-trends/', views.revenue_trends, name='revenue-trends'),
    path('dashboard/user-growth/', views.user_growth, name='user-growth'),
    path('dashboard/category-distribution/', views.category_distribution, name='category-distribution'),
    
    # Existing analytics endpoints
    path('webinars/', views.WebinarAnalyticsListView.as_view(), name='webinar-analytics-list'),
    path('webinars/<int:pk>/', views.WebinarAnalyticsDetailView.as_view(), name='webinar-analytics-detail'),
    path('platform/', views.PlatformMetricsListView.as_view(), name='platform-metrics'),
    path('activities/', views.UserActivityListView.as_view(), name='user-activities'),
    path('revenue/', views.RevenueAnalyticsListView.as_view(), name='revenue-analytics'),
    path('revenue/chart/', views.revenue_chart_data, name='revenue-chart'),
    
    # Activity tracking
    path('track-activity/', views.track_user_activity, name='track-activity'),
    
    # Legacy dashboard stats (for backward compatibility)
    path('dashboard-stats/', views.dashboard_stats, name='dashboard-stats'),
]
