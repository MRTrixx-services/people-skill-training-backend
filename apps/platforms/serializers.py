from rest_framework import serializers
from .models import Platform, PlatformStats, PlatformAPILog


class PlatformStatsSerializer(serializers.ModelSerializer):
    """Platform statistics serializer"""
    
    class Meta:
        model = PlatformStats
        fields = [
            'total_users', 'active_users', 'total_instructors', 'total_attendees',
            'total_webinars', 'live_webinars', 'recorded_webinars',
            'total_enrollments', 'active_enrollments',
            'total_revenue', 'this_month_revenue', 'last_calculated'
        ]


class PlatformCreateSerializer(serializers.ModelSerializer):
    """Platform creation serializer"""
    
    class Meta:
        model = Platform
        fields = [
            'platform_id', 'name', 'description',
            'domain', 'allowed_origins',
            'logo', 'favicon',
            'primary_color', 'secondary_color', 'accent_color',
            'support_email', 'contact_phone', 'address',
            'social_links', 'settings', 'features',
            'payment_settings', 'email_settings', 'analytics',
            'allowed_ip_addresses'
        ]
    
    def validate_platform_id(self, value):
        """Validate platform_id is unique"""
        if Platform.objects.filter(platform_id=value).exists():
            raise serializers.ValidationError("Platform ID already exists")
        return value.lower()


class PlatformListSerializer(serializers.ModelSerializer):
    """Platform list serializer (without sensitive data)"""
    
    user_count = serializers.ReadOnlyField()
    active_user_count = serializers.ReadOnlyField()
    
    class Meta:
        model = Platform
        fields = [
            'id', 'platform_id', 'name', 'description',
            'domain', 'is_active', 'maintenance_mode',
            'user_count', 'active_user_count',
            'created_at', 'last_used_at'
        ]


class PlatformDetailSerializer(serializers.ModelSerializer):
    """Platform detail serializer"""
    
    logo_url = serializers.ReadOnlyField()
    user_count = serializers.ReadOnlyField()
    active_user_count = serializers.ReadOnlyField()
    stats = PlatformStatsSerializer(read_only=True)
    
    class Meta:
        model = Platform
        fields = [
            'id', 'platform_id', 'name', 'description',
            'domain', 'allowed_origins',
            'logo', 'logo_url', 'favicon',
            'primary_color', 'secondary_color', 'accent_color',
            'support_email', 'contact_phone', 'address',
            'social_links', 'settings', 'features',
            'payment_settings', 'email_settings', 'analytics',
            'is_active', 'is_default', 'maintenance_mode',  'requires_email_verification',
            'user_count', 'active_user_count', 'stats',
            'created_at', 'updated_at', 'last_used_at'
        ]


class PlatformConfigSerializer(serializers.ModelSerializer):
    """Public platform configuration for frontend"""
    
    logo_url = serializers.ReadOnlyField()
    
    class Meta:
        model = Platform
        fields = [
            'platform_id', 'name', 'description',
            'logo_url', 'primary_color', 'secondary_color', 'accent_color',
            'support_email', 'contact_phone',
            'social_links', 'features', 'analytics'
        ]


class PlatformAPILogSerializer(serializers.ModelSerializer):
    """API log serializer"""
    
    class Meta:
        model = PlatformAPILog
        fields = [
            'id', 'endpoint', 'method', 'ip_address',
            'status_code', 'response_time_ms',
            'authenticated_user', 
            'error_message', 'created_at'
        ]
