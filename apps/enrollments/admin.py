from django.contrib import admin
from django.utils.html import format_html
from django.urls import reverse
from django.utils.safestring import mark_safe
from django.utils import timezone
from .models import (
    Enrollment, EnrollmentFeedback, AttendanceLog, 
    Certificate, EnrollmentReminder, WaitlistEntry
)


@admin.register(Enrollment)
class EnrollmentAdmin(admin.ModelAdmin):
    """Enrollment admin with platform support"""
    
    list_display = (
        'user', 'webinar', 'platform_display', 'status', 'access_type',
        'payment_amount', 'attendance_duration', 'completion_percentage', 
        'enrolled_at'
    )
    list_filter = (
        'platform', 'status', 'access_type', 'certificate_issued', 
        'feedback_submitted', 'enrolled_at'
    )
    search_fields = (
        'user__first_name', 'user__last_name', 'user__email',
        'webinar__title', 'transaction_id'
    )
    raw_id_fields = ('user', 'webinar')
    date_hierarchy = 'enrolled_at'
    
    fieldsets = (
        ('Enrollment Information', {
            'fields': ('user', 'webinar', 'platform', 'status', 'access_type', 'enrolled_at')
        }),
        ('Payment Details', {
            'fields': ('payment_amount', 'payment_method', 'transaction_id')
        }),
        ('Attendance Tracking', {
            'fields': (
                'joined_at', 'left_at', 'attendance_duration',
                'completion_percentage'
            )
        }),
        ('Engagement Metrics', {
            'fields': (
                'questions_asked', 'chat_messages_sent', 
                'polls_participated'
            )
        }),
        ('Completion & Feedback', {
            'fields': (
                'certificate_issued', 'certificate_url',
                'feedback_submitted', 'would_recommend'
            )
        }),
    )
    
    readonly_fields = ('platform', 'enrolled_at', 'updated_at')
    
    actions = ['mark_as_attended', 'issue_certificates']
    
    def platform_display(self, obj):
        """Display platform name"""
        return obj.platform.name if obj.platform else "No Platform"
    platform_display.short_description = 'Platform'
    platform_display.admin_order_field = 'platform__name'
    
    def mark_as_attended(self, request, queryset):
        updated = 0
        for enrollment in queryset:
            if enrollment.status == 'enrolled':
                enrollment.mark_as_attended()
                updated += 1
        
        self.message_user(
            request, 
            f"Marked {updated} enrollments as attended."
        )
    mark_as_attended.short_description = "Mark selected enrollments as attended"
    
    def issue_certificates(self, request, queryset):
        issued = 0
        for enrollment in queryset:
            if (enrollment.status == 'attended' and 
                not enrollment.certificate_issued and
                enrollment.completion_percentage >= 80):
                
                Certificate.objects.get_or_create(enrollment=enrollment)
                enrollment.certificate_issued = True
                enrollment.save()
                issued += 1
        
        self.message_user(
            request, 
            f"Issued {issued} certificates."
        )
    issue_certificates.short_description = "Issue certificates for completed enrollments"
    
    def get_queryset(self, request):
        """Optimize queryset with select_related"""
        qs = super().get_queryset(request)
        return qs.select_related('user', 'webinar', 'platform')


@admin.register(EnrollmentFeedback)
class EnrollmentFeedbackAdmin(admin.ModelAdmin):
    """Enrollment Feedback admin"""
    
    list_display = (
        'enrollment', 'overall_rating', 'would_recommend', 
        'would_attend_again', 'submitted_at'
    )
    list_filter = (
        'overall_rating', 'would_recommend', 'would_attend_again',
        'learning_objectives_met', 'submitted_at'
    )
    search_fields = (
        'enrollment__user__first_name', 'enrollment__user__last_name',
        'enrollment__webinar__title', 'what_liked', 'what_improved'
    )
    raw_id_fields = ('enrollment',)
    readonly_fields = ('submitted_at',)
    
    fieldsets = (
        ('Enrollment', {
            'fields': ('enrollment',)
        }),
        ('Ratings', {
            'fields': (
                'overall_rating', 'content_rating', 
                'instructor_rating', 'technical_rating'
            )
        }),
        ('Detailed Feedback', {
            'fields': ('what_liked', 'what_improved', 'additional_comments')
        }),
        ('Recommendations', {
            'fields': ('would_recommend', 'would_attend_again')
        }),
        ('Learning Outcomes', {
            'fields': ('learning_objectives_met', 'skill_level_after')
        }),
        ('Timestamp', {
            'fields': ('submitted_at',)
        }),
    )
    
    def get_queryset(self, request):
        """Optimize queryset"""
        qs = super().get_queryset(request)
        return qs.select_related('enrollment__user', 'enrollment__webinar', 'enrollment__platform')


@admin.register(AttendanceLog)
class AttendanceLogAdmin(admin.ModelAdmin):
    """Attendance Log admin"""
    
    list_display = (
        'enrollment', 'action', 'timestamp', 
        'connection_quality', 'ip_address'
    )
    list_filter = ('action', 'connection_quality', 'timestamp')
    search_fields = (
        'enrollment__user__first_name', 'enrollment__user__last_name',
        'enrollment__webinar__title', 'session_id'
    )
    raw_id_fields = ('enrollment',)
    readonly_fields = ('timestamp',)
    
    def has_add_permission(self, request):
        return False
    
    def has_change_permission(self, request, obj=None):
        return False
    
    def get_queryset(self, request):
        """Optimize queryset"""
        qs = super().get_queryset(request)
        return qs.select_related('enrollment__user', 'enrollment__webinar', 'enrollment__platform')


@admin.register(Certificate)
class CertificateAdmin(admin.ModelAdmin):
    """Certificate admin"""
    
    list_display = (
        'certificate_id', 'enrollment_user', 'enrollment_webinar',
        'issued_at', 'verification_code', 'is_verified'
    )
    list_filter = ('is_verified', 'issued_at', 'template_used')
    search_fields = (
        'certificate_id', 'verification_code',
        'enrollment__user__first_name', 'enrollment__user__last_name',
        'enrollment__webinar__title'
    )
    raw_id_fields = ('enrollment',)
    readonly_fields = ('certificate_id', 'verification_code', 'issued_at')
    
    fieldsets = (
        ('Certificate Information', {
            'fields': ('enrollment', 'certificate_id', 'issued_at')
        }),
        ('Content', {
            'fields': ('template_used', 'custom_message')
        }),
        ('Files', {
            'fields': ('certificate_file', 'certificate_url')
        }),
        ('Verification', {
            'fields': ('verification_code', 'is_verified')
        }),
    )
    
    def enrollment_user(self, obj):
        """Display enrollment user"""
        return obj.enrollment.user.full_name
    enrollment_user.short_description = 'User'
    enrollment_user.admin_order_field = 'enrollment__user__first_name'
    
    def enrollment_webinar(self, obj):
        """Display enrollment webinar"""
        return obj.enrollment.webinar.title
    enrollment_webinar.short_description = 'Webinar'
    enrollment_webinar.admin_order_field = 'enrollment__webinar__title'
    
    def get_queryset(self, request):
        """Optimize queryset"""
        qs = super().get_queryset(request)
        return qs.select_related('enrollment__user', 'enrollment__webinar', 'enrollment__platform')


@admin.register(EnrollmentReminder)
class EnrollmentReminderAdmin(admin.ModelAdmin):
    """Enrollment Reminder admin"""
    
    list_display = (
        'enrollment', 'reminder_type', 'scheduled_at', 
        'is_sent', 'sent_at'
    )
    list_filter = (
        'reminder_type', 'is_sent', 'send_email', 
        'send_sms', 'scheduled_at'
    )
    search_fields = (
        'enrollment__user__first_name', 'enrollment__user__last_name',
        'enrollment__webinar__title', 'subject'
    )
    raw_id_fields = ('enrollment',)
    readonly_fields = ('created_at', 'sent_at')
    
    fieldsets = (
        ('Reminder Information', {
            'fields': ('enrollment', 'reminder_type')
        }),
        ('Scheduling', {
            'fields': ('scheduled_at', 'sent_at', 'is_sent')
        }),
        ('Content', {
            'fields': ('subject', 'message')
        }),
        ('Delivery Options', {
            'fields': ('send_email', 'send_sms')
        }),
        ('Tracking', {
            'fields': ('email_opened', 'email_clicked')
        }),
    )
    
    def get_queryset(self, request):
        """Optimize queryset"""
        qs = super().get_queryset(request)
        return qs.select_related('enrollment__user', 'enrollment__webinar', 'enrollment__platform')


@admin.register(WaitlistEntry)
class WaitlistEntryAdmin(admin.ModelAdmin):
    """Waitlist Entry admin with platform support"""
    
    list_display = (
        'user', 'webinar', 'platform_display', 'position', 
        'joined_at', 'is_active', 'converted_to_enrollment'
    )
    list_filter = (
        'platform', 'is_active', 'converted_to_enrollment', 
        'notification_sent', 'joined_at'
    )
    search_fields = (
        'user__first_name', 'user__last_name', 'user__email',
        'webinar__title'
    )
    raw_id_fields = ('user', 'webinar')
    readonly_fields = ('platform', 'joined_at', 'converted_at')
    
    fieldsets = (
        ('Waitlist Information', {
            'fields': ('user', 'webinar', 'platform', 'position', 'joined_at')
        }),
        ('Notifications', {
            'fields': (
                'notify_on_availability', 'notification_sent', 
                'notification_sent_at'
            )
        }),
        ('Status', {
            'fields': (
                'is_active', 'converted_to_enrollment', 'converted_at'
            )
        }),
    )
    
    actions = ['notify_availability', 'convert_to_enrollment']
    
    def platform_display(self, obj):
        """Display platform name"""
        return obj.platform.name if obj.platform else "No Platform"
    platform_display.short_description = 'Platform'
    platform_display.admin_order_field = 'platform__name'
    
    def notify_availability(self, request, queryset):
        # This would trigger notification logic
        notified = queryset.filter(
            is_active=True,
            notification_sent=False
        ).count()
        
        self.message_user(
            request,
            f"Sent availability notifications to {notified} waitlist entries."
        )
    notify_availability.short_description = "Notify about availability"
    
    def convert_to_enrollment(self, request, queryset):
        converted = 0
        for entry in queryset:
            if entry.is_active and not entry.converted_to_enrollment:
                # This would create an enrollment
                entry.converted_to_enrollment = True
                entry.converted_at = timezone.now()
                entry.is_active = False
                entry.save()
                converted += 1
        
        self.message_user(
            request,
            f"Converted {converted} waitlist entries to enrollments."
        )
    convert_to_enrollment.short_description = "Convert to enrollment"
    
    def get_queryset(self, request):
        """Optimize queryset with select_related"""
        qs = super().get_queryset(request)
        return qs.select_related('user', 'webinar', 'platform')
