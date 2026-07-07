from rest_framework import serializers
from .models import (
    AttendeeProfile, 
    AttendeeNotificationSettings, 
    AttendeeSecuritySettings,
    AttendeeActivity,
    AttendeeLearningPath
)
from apps.users.serializers import UserSerializer


class AttendeeNotificationSettingsSerializer(serializers.ModelSerializer):
    """Serializer for attendee notification settings"""
    
    class Meta:
        model = AttendeeNotificationSettings
        exclude = ['attendee', 'created_at', 'updated_at']


class AttendeeSecuritySettingsSerializer(serializers.ModelSerializer):
    """Serializer for attendee security settings"""
    
    class Meta:
        model = AttendeeSecuritySettings
        fields = [
            'two_factor_enabled', 'login_alerts_enabled', 
            'password_changed_at', 'created_at', 'updated_at'
        ]
        read_only_fields = ['password_changed_at', 'created_at', 'updated_at']


class AttendeeProfileSerializer(serializers.ModelSerializer):
    """Main attendee profile serializer"""
    
    user = UserSerializer(read_only=True)
    full_name = serializers.CharField(source='user.full_name', read_only=True)
    email = serializers.EmailField(source='user.email', read_only=True)
    avatar = serializers.ImageField(source='user.avatar', read_only=True)
    phone = serializers.CharField(source='user.phone', read_only=True)
    
    # Related settings
    notification_settings = AttendeeNotificationSettingsSerializer(read_only=True)
    security_settings = AttendeeSecuritySettingsSerializer(read_only=True)
    
    # Computed fields
    completion_rate = serializers.ReadOnlyField()
    
    class Meta:
        model = AttendeeProfile
        fields = [
            'id', 'user', 'full_name', 'email', 'avatar', 'phone',
            'interests', 'learning_goals', 'skill_level',
            'total_enrollments', 'completed_webinars', 'total_hours_learned',
            'certificates_earned', 'company', 'average_rating_given', 'completion_rate',
            'show_email_publicly', 'show_phone_publicly', 'allow_direct_messages',
            'allow_newsletters', 'language', 'timezone', 'email_frequency',
            'auto_join_webinars', 'show_profile_publicly', 'member_since',
            'notification_settings', 'security_settings',
            'created_at', 'updated_at'
        ]
        read_only_fields = [
            'id', 'user', 'total_enrollments', 'completed_webinars', 
            'total_hours_learned', 'certificates_earned', 'average_rating_given',
            'member_since', 'created_at', 'updated_at'
        ]


class AttendeeProfileUpdateSerializer(serializers.ModelSerializer):
    """Serializer for updating attendee profile"""
    
    notification_settings = AttendeeNotificationSettingsSerializer(required=False)
    security_settings = AttendeeSecuritySettingsSerializer(required=False)
    
    # User fields that can be updated
    first_name = serializers.CharField(source='user.first_name', required=False)
    last_name = serializers.CharField(source='user.last_name', required=False)
    avatar = serializers.ImageField(source='user.avatar', required=False)
    phone = serializers.CharField(source='user.phone', required=False)
    
    class Meta:
        model = AttendeeProfile
        fields = [
            'first_name', 'company', 'last_name', 'avatar', 'phone',
            'interests', 'learning_goals', 'skill_level',
            'show_email_publicly', 'show_phone_publicly', 'allow_direct_messages',
            'allow_newsletters', 'language', 'timezone', 'email_frequency',
            'auto_join_webinars', 'show_profile_publicly',
            'notification_settings', 'security_settings'
        ]
    
    def update(self, instance, validated_data):
        # Handle user fields
        user_data = {}
        for field in ['first_name', 'last_name', 'avatar', 'phone']:
            if f'user.{field}' in validated_data:
                user_data[field] = validated_data.pop(f'user.{field}')
        
        if user_data:
            user = instance.user
            for attr, value in user_data.items():
                setattr(user, attr, value)
            user.save()
        
        # Handle notification settings
        notification_data = validated_data.pop('notification_settings', None)
        if notification_data and hasattr(instance, 'notification_settings'):
            notification_settings = instance.notification_settings
            for attr, value in notification_data.items():
                setattr(notification_settings, attr, value)
            notification_settings.save()
        
        # Handle security settings
        security_data = validated_data.pop('security_settings', None)
        if security_data and hasattr(instance, 'security_settings'):
            security_settings = instance.security_settings
            for attr, value in security_data.items():
                setattr(security_settings, attr, value)
            security_settings.save()
        
        # Update attendee profile
        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        instance.save()
        
        return instance


class AttendeeListSerializer(serializers.ModelSerializer):
    """Serializer for listing attendees"""
    
    full_name = serializers.CharField(source='user.full_name', read_only=True)
    email = serializers.EmailField(source='user.email', read_only=True)
    avatar = serializers.ImageField(source='user.avatar', read_only=True)
    completion_rate = serializers.ReadOnlyField()
    
    class Meta:
        model = AttendeeProfile
        fields = [
            'id', 'full_name', 'email', 'avatar', 'skill_level',
            'total_enrollments', 'company', 'completed_webinars', 'total_hours_learned',
            'certificates_earned', 'completion_rate', 'member_since'
        ]


class AttendeeActivitySerializer(serializers.ModelSerializer):
    """Serializer for attendee activities"""
    
    attendee_name = serializers.CharField(source='attendee.user.full_name', read_only=True)
    
    class Meta:
        model = AttendeeActivity
        fields = [
            'id', 'attendee', 'attendee_name', 'activity_type', 
            'description', 'metadata', 'created_at'
        ]
        read_only_fields = ['id', 'attendee', 'created_at']


class AttendeeLearningPathSerializer(serializers.ModelSerializer):
    """Serializer for learning paths"""
    
    attendee_name = serializers.CharField(source='attendee.user.full_name', read_only=True)
    
    class Meta:
        model = AttendeeLearningPath
        fields = [
            'id', 'attendee', 'attendee_name', 'path_name', 'description',
            'status', 'total_webinars', 'completed_webinars', 'progress_percentage',
            'started_at', 'completed_at', 'target_completion_date',
            'created_at', 'updated_at'
        ]
        read_only_fields = [
            'id', 'attendee', 'progress_percentage', 'started_at', 
            'completed_at', 'created_at', 'updated_at'
        ]


class AttendeeStatsSerializer(serializers.Serializer):
    """Serializer for attendee statistics"""
    
    total_attendees = serializers.IntegerField()
    active_attendees = serializers.IntegerField()
    new_this_month = serializers.IntegerField()
    average_completion_rate = serializers.DecimalField(max_digits=5, decimal_places=2)
    total_hours_learned = serializers.IntegerField()
    certificates_issued = serializers.IntegerField()
    top_interests = serializers.ListField()
