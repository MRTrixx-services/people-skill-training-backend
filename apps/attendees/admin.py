from django.contrib import admin
from .models import (
    AttendeeProfile, 
    AttendeeNotificationSettings, 
    AttendeeSecuritySettings,
    AttendeeActivity,
    AttendeeLearningPath
)


class AttendeeNotificationSettingsInline(admin.StackedInline):
    model = AttendeeNotificationSettings
    can_delete = False


class AttendeeSecuritySettingsInline(admin.StackedInline):
    model = AttendeeSecuritySettings
    can_delete = False


@admin.register(AttendeeProfile)
class AttendeeProfileAdmin(admin.ModelAdmin):
    inlines = [AttendeeNotificationSettingsInline, AttendeeSecuritySettingsInline]
    
    list_display = [
        'user', 'platform_display', 'skill_level', 'total_enrollments', 
        'completed_webinars', 'total_hours_learned', 'certificates_earned', 
        'completion_rate', 'show_profile_publicly', 'member_since'
    ]
    list_filter = [
        'platform', 'skill_level', 'language', 'show_profile_publicly', 
        'allow_newsletters', 'auto_join_webinars', 'member_since'
    ]
    search_fields = [
        'user__first_name', 'user__last_name', 'user__email', 
        'interests', 'learning_goals', 'company'
    ]
    readonly_fields = [
        'platform', 'total_enrollments', 'completed_webinars', 'total_hours_learned',
        'certificates_earned', 'average_rating_given', 'completion_rate',
        'member_since', 'created_at', 'updated_at'
    ]
    
    fieldsets = (
        ('User Information', {
            'fields': ('user', 'platform')
        }),
        ('Learning Preferences', {
            'fields': ('interests', 'learning_goals', 'skill_level', 'company')
        }),
        ('Statistics', {
            'fields': (
                'total_enrollments', 'completed_webinars', 'total_hours_learned',
                'certificates_earned', 'average_rating_given', 'completion_rate'
            ),
            'classes': ('collapse',)
        }),
        ('Privacy & Contact', {
            'fields': (
                'show_email_publicly', 'show_phone_publicly', 
                'allow_direct_messages', 'allow_newsletters', 'show_profile_publicly'
            )
        }),
        ('App Preferences', {
            'fields': ('language', 'timezone', 'email_frequency', 'auto_join_webinars')
        }),
        ('Timestamps', {
            'fields': ('member_since', 'created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )
    
    def platform_display(self, obj):
        """Display platform name"""
        return obj.platform.name if obj.platform else "No Platform"
    platform_display.short_description = 'Platform'
    
    def get_queryset(self, request):
        """Optimize queryset"""
        qs = super().get_queryset(request)
        return qs.select_related('user', 'platform')


@admin.register(AttendeeActivity)
class AttendeeActivityAdmin(admin.ModelAdmin):
    list_display = [
        'attendee', 'activity_type', 'description', 'created_at'
    ]
    list_filter = ['activity_type', 'created_at']
    search_fields = [
        'attendee__user__first_name', 'attendee__user__last_name', 
        'description'
    ]
    readonly_fields = ['created_at']
    
    def get_queryset(self, request):
        """Optimize queryset"""
        qs = super().get_queryset(request)
        return qs.select_related('attendee__user', 'attendee__platform')


@admin.register(AttendeeLearningPath)
class AttendeeLearningPathAdmin(admin.ModelAdmin):
    list_display = [
        'attendee', 'path_name', 'status', 'progress_percentage',
        'started_at', 'target_completion_date'
    ]
    list_filter = ['status', 'started_at', 'completed_at']
    search_fields = [
        'attendee__user__first_name', 'attendee__user__last_name', 
        'path_name', 'description'
    ]
    readonly_fields = ['progress_percentage', 'completed_at', 'created_at', 'updated_at']
    
    def get_queryset(self, request):
        """Optimize queryset"""
        qs = super().get_queryset(request)
        return qs.select_related('attendee__user', 'attendee__platform')
