from rest_framework import serializers
from django.utils import timezone
from apps.users.serializers import UserSerializer
from apps.webinars.serializers import WebinarListSerializer
from .models import (
    Enrollment, EnrollmentFeedback, AttendanceLog, 
    Certificate, EnrollmentReminder, WaitlistEntry
)


class EnrollmentSerializer(serializers.ModelSerializer):
    """Basic enrollment serializer with platform info"""
    
    user = UserSerializer(read_only=True)
    webinar = WebinarListSerializer(read_only=True)
    status_display = serializers.CharField(source='get_status_display', read_only=True)
    is_active = serializers.ReadOnlyField()
    attended_webinar = serializers.ReadOnlyField()
    platform_info = serializers.SerializerMethodField()
    
    class Meta:
        model = Enrollment
        fields = '__all__'
        read_only_fields = (
            'user', 'platform', 'enrolled_at', 'updated_at', 'attendance_duration',
            'completion_percentage', 'certificate_issued'
        )
    
    def get_platform_info(self, obj):
        """Get platform information"""
        if obj.platform:
            return {
                'id': obj.platform.id,
                'platform_id': obj.platform.platform_id,
                'name': obj.platform.name
            }
        return None


class EnrollmentCreateSerializer(serializers.ModelSerializer):
    """Enrollment creation serializer - Platform-aware"""
    
    class Meta:
        model = Enrollment
        fields = ('webinar', 'access_type', 'payment_method', 'transaction_id')
    
    def validate_webinar(self, value):
        user = self.context['request'].user
        platform = getattr(self.context['request'], 'platform', None) or user.platform
        
        # Check if already enrolled
        if Enrollment.objects.filter(user=user, webinar=value).exists():
            raise serializers.ValidationError("You are already enrolled in this webinar")
        
        # Check if webinar is available on this platform
        if platform and not value.platforms.filter(id=platform.id).exists():
            raise serializers.ValidationError("This webinar is not available on your platform")
        
        # Check if webinar is full
        if value.is_full:
            raise serializers.ValidationError("This webinar is full")
        
        # Check if webinar is still available for enrollment
        if value.webinar_type == 'live' and value.scheduled_date and value.scheduled_date <= timezone.now():
            raise serializers.ValidationError("Cannot enroll in past webinars")
        
        if value.status not in ['scheduled', 'draft', 'available']:
            raise serializers.ValidationError("This webinar is not available for enrollment")
        
        return value
    
    def create(self, validated_data):
        user = self.context['request'].user
        webinar = validated_data['webinar']
        platform = getattr(self.context['request'], 'platform', None) or user.platform
        
        if not platform:
            raise serializers.ValidationError({'platform': 'No platform associated with user'})
        
        # Set payment amount based on webinar price and access type
        access_type = validated_data.get('access_type', 'liveOne')
        payment_amount = 0  # Will be set by payment processing
        
        enrollment = Enrollment.objects.create(
            user=user,
            webinar=webinar,
            platform=platform,
            payment_amount=payment_amount,
            **validated_data
        )
        
        return enrollment


class EnrollmentFeedbackSerializer(serializers.ModelSerializer):
    """Enrollment feedback serializer"""
    
    enrollment = EnrollmentSerializer(read_only=True)
    
    class Meta:
        model = EnrollmentFeedback
        fields = '__all__'
        read_only_fields = ('enrollment', 'submitted_at')


class AttendanceLogSerializer(serializers.ModelSerializer):
    """Attendance log serializer"""
    
    enrollment = EnrollmentSerializer(read_only=True)
    action_display = serializers.CharField(source='get_action_display', read_only=True)
    
    class Meta:
        model = AttendanceLog
        fields = '__all__'
        read_only_fields = ('enrollment', 'timestamp')


class CertificateSerializer(serializers.ModelSerializer):
    """Certificate serializer"""
    
    enrollment = EnrollmentSerializer(read_only=True)
    certificate_file_url = serializers.SerializerMethodField()
    
    class Meta:
        model = Certificate
        fields = '__all__'
        read_only_fields = (
            'enrollment', 'certificate_id', 'issued_at', 
            'verification_code'
        )
    
    def get_certificate_file_url(self, obj):
        if obj.certificate_file:
            request = self.context.get('request')
            if request:
                return request.build_absolute_uri(obj.certificate_file.url)
        return None


class EnrollmentReminderSerializer(serializers.ModelSerializer):
    """Enrollment reminder serializer"""
    
    enrollment = EnrollmentSerializer(read_only=True)
    reminder_type_display = serializers.CharField(
        source='get_reminder_type_display', 
        read_only=True
    )
    
    class Meta:
        model = EnrollmentReminder
        fields = '__all__'
        read_only_fields = (
            'enrollment', 'sent_at', 'is_sent', 'created_at'
        )


class WaitlistEntrySerializer(serializers.ModelSerializer):
    """Waitlist entry serializer with platform"""
    
    user = UserSerializer(read_only=True)
    webinar = WebinarListSerializer(read_only=True)
    platform_info = serializers.SerializerMethodField()
    
    class Meta:
        model = WaitlistEntry
        fields = '__all__'
        read_only_fields = (
            'user', 'platform', 'joined_at', 'position', 'converted_to_enrollment',
            'converted_at', 'notification_sent', 'notification_sent_at'
        )
    
    def get_platform_info(self, obj):
        """Get platform information"""
        if obj.platform:
            return {
                'id': obj.platform.id,
                'platform_id': obj.platform.platform_id,
                'name': obj.platform.name
            }
        return None


class WaitlistCreateSerializer(serializers.ModelSerializer):
    """Waitlist creation serializer - Platform-aware"""
    
    class Meta:
        model = WaitlistEntry
        fields = ('webinar', 'notify_on_availability')
    
    def validate_webinar(self, value):
        user = self.context['request'].user
        platform = getattr(self.context['request'], 'platform', None) or user.platform
        
        # Check if already on waitlist
        if WaitlistEntry.objects.filter(
            user=user, 
            webinar=value, 
            is_active=True
        ).exists():
            raise serializers.ValidationError("You are already on the waitlist for this webinar")
        
        # Check if already enrolled
        if Enrollment.objects.filter(user=user, webinar=value).exists():
            raise serializers.ValidationError("You are already enrolled in this webinar")
        
        # Check if webinar is available on this platform
        if platform and not value.platforms.filter(id=platform.id).exists():
            raise serializers.ValidationError("This webinar is not available on your platform")
        
        # Check if webinar is actually full
        if not value.is_full:
            raise serializers.ValidationError("This webinar is not full. You can enroll directly.")
        
        return value
    
    def create(self, validated_data):
        user = self.context['request'].user
        platform = getattr(self.context['request'], 'platform', None) or user.platform
        
        if not platform:
            raise serializers.ValidationError({'platform': 'No platform associated with user'})
        
        return WaitlistEntry.objects.create(
            user=user,
            platform=platform,
            **validated_data
        )


class EnrollmentStatsSerializer(serializers.Serializer):
    """Enrollment statistics serializer"""
    
    total_enrollments = serializers.IntegerField()
    active_enrollments = serializers.IntegerField()
    completed_enrollments = serializers.IntegerField()
    cancelled_enrollments = serializers.IntegerField()
    total_revenue = serializers.DecimalField(max_digits=10, decimal_places=2)
    average_completion_rate = serializers.DecimalField(max_digits=5, decimal_places=2)
    certificates_issued = serializers.IntegerField()
    feedback_submitted = serializers.IntegerField()
    platform = serializers.DictField(required=False)


class UserEnrollmentStatsSerializer(serializers.Serializer):
    """User enrollment statistics serializer"""
    
    total_enrollments = serializers.IntegerField()
    attended_webinars = serializers.IntegerField()
    missed_webinars = serializers.IntegerField()
    certificates_earned = serializers.IntegerField()
    total_learning_hours = serializers.IntegerField()
    favorite_categories = serializers.ListField()
    average_completion_rate = serializers.DecimalField(max_digits=5, decimal_places=2)


class AttendanceTrackingSerializer(serializers.Serializer):
    """Attendance tracking serializer for real-time updates"""
    
    enrollment_id = serializers.IntegerField()
    action = serializers.ChoiceField(choices=AttendanceLog.ACTION_CHOICES)
    session_id = serializers.CharField(required=False, allow_blank=True)
    connection_quality = serializers.CharField(required=False, allow_blank=True)
    device_info = serializers.JSONField(required=False)
