from rest_framework import serializers
from .models import WebinarAnalytics, PlatformMetrics, UserActivity, RevenueAnalytics

class WebinarAnalyticsSerializer(serializers.ModelSerializer):
    webinar_title = serializers.CharField(source='webinar.title', read_only=True)
    webinar_type = serializers.CharField(source='webinar.webinar_type', read_only=True)
    instructor_name = serializers.CharField(source='webinar.instructor.get_full_name', read_only=True)
    
    class Meta:
        model = WebinarAnalytics
        fields = [
            'id', 'webinar_title', 'webinar_type', 'instructor_name',
            'total_enrollments', 'total_attendees', 'peak_attendance', 
            'average_attendance_duration', 'total_watch_time', 'average_rating', 
            'total_reviews', 'total_revenue', 'completion_rate', 'engagement_score', 
            'last_updated'
        ]

class PlatformMetricsSerializer(serializers.ModelSerializer):
    growth_rate = serializers.SerializerMethodField()
    
    class Meta:
        model = PlatformMetrics
        fields = [
            'date', 'total_users', 'new_users', 'active_users',
            'total_instructors', 'active_instructors', 'total_webinars',
            'live_webinars', 'completed_webinars', 'total_enrollments',
            'new_enrollments', 'daily_revenue', 'total_revenue', 'growth_rate'
        ]
    
    def get_growth_rate(self, obj):
        # Calculate growth rate compared to previous day
        try:
            previous_day = PlatformMetrics.objects.filter(
                date=obj.date - timedelta(days=1)
            ).first()
            if previous_day and previous_day.total_users > 0:
                growth = ((obj.total_users - previous_day.total_users) / previous_day.total_users) * 100
                return round(growth, 2)
        except:
            pass
        return 0.0

class UserActivitySerializer(serializers.ModelSerializer):
    user_email = serializers.CharField(source='user.email', read_only=True)
    user_name = serializers.CharField(source='user.get_full_name', read_only=True)
    webinar_title = serializers.CharField(source='webinar.title', read_only=True)
    
    class Meta:
        model = UserActivity
        fields = [
            'id', 'user_email', 'user_name', 'activity_type', 'webinar_title',
            'metadata', 'ip_address', 'timestamp'
        ]

class RevenueAnalyticsSerializer(serializers.ModelSerializer):
    instructor_name = serializers.CharField(source='instructor.get_full_name', read_only=True)
    instructor_email = serializers.CharField(source='instructor.email', read_only=True)
    webinar_title = serializers.CharField(source='webinar.title', read_only=True)
    profit_margin = serializers.SerializerMethodField()
    
    class Meta:
        model = RevenueAnalytics
        fields = [
            'date', 'instructor_name', 'instructor_email', 'webinar_title', 
            'gross_revenue', 'platform_fee', 'net_revenue', 'enrollments_count',
            'refunds_count', 'refund_amount', 'profit_margin'
        ]
    
    def get_profit_margin(self, obj):
        if obj.gross_revenue > 0:
            return round(((obj.net_revenue / obj.gross_revenue) * 100), 2)
        return 0.0

class DashboardStatsSerializer(serializers.Serializer):
    total_webinars = serializers.IntegerField()
    total_enrollments = serializers.IntegerField()
    total_revenue = serializers.DecimalField(max_digits=10, decimal_places=2)
    average_rating = serializers.DecimalField(max_digits=3, decimal_places=2)
    active_users = serializers.IntegerField()
    growth_rate = serializers.DecimalField(max_digits=5, decimal_places=2)

class AdminDashboardSerializer(serializers.Serializer):
    """Serializer for comprehensive admin dashboard data"""
    
    # Metrics section
    metrics = serializers.DictField()
    
    # Charts data
    revenue_trends = serializers.ListField(child=serializers.DictField())
    user_growth = serializers.ListField(child=serializers.DictField())
    category_distribution = serializers.ListField(child=serializers.DictField())
    
    # Recent activities
    recent_activities = serializers.ListField(child=serializers.DictField())
    
    # Metadata
    time_range = serializers.CharField()
    generated_at = serializers.DateTimeField()

# Additional specialized serializers
class TopInstructorSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    full_name = serializers.CharField()
    email = serializers.CharField()
    profile_picture = serializers.URLField(allow_null=True)
    total_revenue = serializers.DecimalField(max_digits=10, decimal_places=2)
    webinar_count = serializers.IntegerField()
    student_count = serializers.IntegerField()
    average_rating = serializers.DecimalField(max_digits=3, decimal_places=2)

class CategoryDistributionSerializer(serializers.Serializer):
    category_name = serializers.CharField()
    percentage = serializers.DecimalField(max_digits=5, decimal_places=2)
    count = serializers.IntegerField()

class RevenueChartSerializer(serializers.Serializer):
    month = serializers.CharField()
    revenue = serializers.DecimalField(max_digits=10, decimal_places=2)
    webinar_count = serializers.IntegerField()

class UserGrowthSerializer(serializers.Serializer):
    month = serializers.CharField()
    attendees = serializers.IntegerField()
    instructors = serializers.IntegerField()
