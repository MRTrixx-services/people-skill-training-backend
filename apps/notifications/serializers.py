from rest_framework import serializers
from .models import Notification, NotificationTemplate, NotificationPreference


class NotificationTemplateSerializer(serializers.ModelSerializer):
    """Notification template serializer with platform info"""
    
    platform_info = serializers.SerializerMethodField()
    
    class Meta:
        model = NotificationTemplate
        fields = [
            'id', 'name', 'template_type', 'event_type', 'subject',
            'content', 'is_active', 'platform_info', 
            'created_at', 'updated_at'
        ]
        read_only_fields = ['created_at', 'updated_at']
    
    def get_platform_info(self, obj):
        """Get platform information"""
        if obj.platform:
            return {
                'id': obj.platform.id,
                'platform_id': obj.platform.platform_id,
                'name': obj.platform.name
            }
        return {'name': 'Global Template'}


class NotificationSerializer(serializers.ModelSerializer):
    """Notification serializer with platform info"""
    
    template_name = serializers.CharField(source='template.name', read_only=True)
    webinar_title = serializers.CharField(source='webinar.title', read_only=True)
    platform_info = serializers.SerializerMethodField()
    status_display = serializers.CharField(source='get_status_display', read_only=True)
    priority_display = serializers.CharField(source='get_priority_display', read_only=True)
    
    class Meta:
        model = Notification
        fields = [
            'id', 'template_name', 'webinar_title', 'title', 'message',
            'status', 'status_display', 'priority', 'priority_display',
            'platform_info', 'scheduled_at', 'sent_at', 'read_at',
            'created_at', 'metadata'
        ]
        read_only_fields = ['platform', 'sent_at', 'created_at']
    
    def get_platform_info(self, obj):
        """Get platform information"""
        if obj.platform:
            return {
                'id': obj.platform.id,
                'platform_id': obj.platform.platform_id,
                'name': obj.platform.name
            }
        return None


class NotificationPreferenceSerializer(serializers.ModelSerializer):
    """User notification preferences serializer"""
    
    class Meta:
        model = NotificationPreference
        fields = [
            'email_notifications', 'sms_notifications', 'push_notifications',
            'webinar_reminders', 'marketing_emails', 'payment_notifications',
            'instructor_updates', 'reminder_time'
        ]


class NotificationCreateSerializer(serializers.ModelSerializer):
    """Create notification serializer"""
    
    class Meta:
        model = Notification
        fields = [
            'user', 'template', 'webinar', 'title', 'message', 
            'priority', 'scheduled_at', 'metadata'
        ]
    
    def validate_template(self, value):
        """Validate template is active"""
        if not value.is_active:
            raise serializers.ValidationError("Cannot use inactive template")
        return value
    
    def create(self, validated_data):
        """Create notification with auto-platform assignment"""
        # Platform will be auto-assigned from user.platform in model save()
        return super().create(validated_data)


class NotificationListSerializer(serializers.ModelSerializer):
    """Simplified notification list serializer"""
    
    class Meta:
        model = Notification
        fields = [
            'id', 'title', 'message', 'status', 'priority',
            'sent_at', 'read_at', 'created_at'
        ]


class NotificationStatsSerializer(serializers.Serializer):
    """Notification statistics serializer"""
    
    total_notifications = serializers.IntegerField()
    pending_notifications = serializers.IntegerField()
    sent_notifications = serializers.IntegerField()
    failed_notifications = serializers.IntegerField()
    unread_notifications = serializers.IntegerField()
    platform = serializers.DictField(required=False)
