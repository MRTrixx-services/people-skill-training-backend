from django.contrib import admin
from .models import WebinarAnalytics, PlatformMetrics, UserActivity, RevenueAnalytics

@admin.register(WebinarAnalytics)
class WebinarAnalyticsAdmin(admin.ModelAdmin):
    list_display = ['webinar', 'total_enrollments', 'total_attendees', 'average_rating', 'total_revenue', 'last_updated']
    list_filter = ['webinar__category', 'last_updated']
    search_fields = ['webinar__title', 'webinar__instructor__email']
    readonly_fields = ['last_updated']
    raw_id_fields = ['webinar']

@admin.register(PlatformMetrics)
class PlatformMetricsAdmin(admin.ModelAdmin):
    list_display = ['date', 'total_users', 'active_users', 'total_webinars', 'daily_revenue']
    list_filter = ['date']
    date_hierarchy = 'date'
    readonly_fields = ['created_at']

@admin.register(UserActivity)
class UserActivityAdmin(admin.ModelAdmin):
    list_display = ['user', 'activity_type', 'webinar', 'timestamp']
    list_filter = ['activity_type', 'timestamp']
    search_fields = ['user__email', 'webinar__title']
    readonly_fields = ['timestamp']
    date_hierarchy = 'timestamp'
    raw_id_fields = ['user', 'webinar']

@admin.register(RevenueAnalytics)
class RevenueAnalyticsAdmin(admin.ModelAdmin):
    list_display = ['date', 'instructor', 'webinar', 'gross_revenue', 'net_revenue']
    list_filter = ['date', 'instructor']
    search_fields = ['instructor__email', 'webinar__title']
    date_hierarchy = 'date'
    raw_id_fields = ['instructor', 'webinar']
