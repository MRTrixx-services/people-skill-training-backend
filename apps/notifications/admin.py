from django.contrib import admin
from django.utils.html import format_html
from .models import NotificationTemplate, Notification, EmailLog, SMSLog, NotificationPreference


@admin.register(NotificationTemplate)
class NotificationTemplateAdmin(admin.ModelAdmin):
    """Notification template admin with platform support"""
    
    list_display = [
        'name', 'template_type', 'event_type', 
        'platform_display', 'is_active', 'created_at'
    ]
    list_filter = ['platform', 'template_type', 'event_type', 'is_active', 'created_at']
    search_fields = ['name', 'subject', 'content']
    readonly_fields = ['created_at', 'updated_at']
    
    fieldsets = (
        ('Template Information', {
            'fields': ('name', 'template_type', 'event_type', 'platform')
        }),
        ('Content', {
            'fields': ('subject', 'content')
        }),
        ('Status', {
            'fields': ('is_active',)
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )
    
    def platform_display(self, obj):
        """Display platform name or Global"""
        if obj.platform:
            return format_html(
                '<span style="color: #059669; font-weight: bold;">{}</span>',
                obj.platform.name
            )
        return format_html(
            '<span style="color: #6b7280;">Global Template</span>'
        )
    platform_display.short_description = 'Platform'
    platform_display.admin_order_field = 'platform__name'
    
    def get_queryset(self, request):
        """Optimize queryset"""
        qs = super().get_queryset(request)
        return qs.select_related('platform')


@admin.register(Notification)
class NotificationAdmin(admin.ModelAdmin):
    """Notification admin with platform support"""
    
    list_display = [
        'title', 'user_email', 'platform_display', 
        'template_name', 'status_display', 'priority', 'created_at'
    ]
    list_filter = [
        'platform', 'status', 'priority', 
        'template__event_type', 'created_at'
    ]
    search_fields = ['title', 'user__email', 'message']
    readonly_fields = ['platform', 'sent_at', 'read_at', 'created_at']
    date_hierarchy = 'created_at'
    
    fieldsets = (
        ('Notification Details', {
            'fields': ('user', 'template', 'platform', 'webinar')
        }),
        ('Content', {
            'fields': ('title', 'message', 'metadata')
        }),
        ('Status & Priority', {
            'fields': ('status', 'priority', 'scheduled_at')
        }),
        ('Timestamps', {
            'fields': ('sent_at', 'read_at', 'created_at'),
            'classes': ('collapse',)
        }),
    )
    
    def user_email(self, obj):
        """Display user email"""
        return obj.user.email
    user_email.short_description = 'User'
    user_email.admin_order_field = 'user__email'
    
    def template_name(self, obj):
        """Display template name"""
        return obj.template.name
    template_name.short_description = 'Template'
    template_name.admin_order_field = 'template__name'
    
    def platform_display(self, obj):
        """Display platform name"""
        if obj.platform:
            return format_html(
                '<span style="color: #059669; font-weight: bold;">{}</span>',
                obj.platform.name
            )
        return format_html('<span style="color: #6b7280;">No Platform</span>')
    platform_display.short_description = 'Platform'
    platform_display.admin_order_field = 'platform__name'
    
    def status_display(self, obj):
        """Display colored status"""
        colors = {
            'pending': 'orange',
            'sent': 'green',
            'failed': 'red',
            'read': 'blue',
        }
        color = colors.get(obj.status, 'gray')
        return format_html(
            '<span style="color: {}; font-weight: bold;">{}</span>',
            color,
            obj.get_status_display()
        )
    status_display.short_description = 'Status'
    status_display.admin_order_field = 'status'
    
    def get_queryset(self, request):
        """Optimize queryset"""
        qs = super().get_queryset(request)
        return qs.select_related('user', 'template', 'platform', 'webinar')
    
    actions = ['mark_as_sent', 'mark_as_read']
    
    def mark_as_sent(self, request, queryset):
        """Mark notifications as sent"""
        from django.utils import timezone
        updated = queryset.update(status='sent', sent_at=timezone.now())
        self.message_user(request, f'{updated} notifications marked as sent.')
    mark_as_sent.short_description = "Mark as sent"
    
    def mark_as_read(self, request, queryset):
        """Mark notifications as read"""
        from django.utils import timezone
        updated = queryset.update(status='read', read_at=timezone.now())
        self.message_user(request, f'{updated} notifications marked as read.')
    mark_as_read.short_description = "Mark as read"


@admin.register(EmailLog)
class EmailLogAdmin(admin.ModelAdmin):
    """Email log admin"""
    
    list_display = [
        'to_email', 'subject', 'delivery_status_display', 
        'sent_at', 'opened_at'
    ]
    list_filter = ['delivery_status', 'sent_at']
    search_fields = ['to_email', 'subject', 'from_email']
    readonly_fields = ['sent_at', 'opened_at', 'clicked_at']
    date_hierarchy = 'sent_at'
    
    fieldsets = (
        ('Email Details', {
            'fields': ('notification', 'to_email', 'from_email', 'subject')
        }),
        ('Content', {
            'fields': ('body',),
            'classes': ('collapse',)
        }),
        ('Delivery Info', {
            'fields': ('delivery_status', 'error_message')
        }),
        ('Tracking', {
            'fields': ('sent_at', 'opened_at', 'clicked_at')
        }),
    )
    
    def delivery_status_display(self, obj):
        """Display colored delivery status"""
        colors = {
            'sent': 'green',
            'failed': 'red',
            'bounced': 'orange',
        }
        color = colors.get(obj.delivery_status, 'gray')
        return format_html(
            '<span style="color: {}; font-weight: bold;">{}</span>',
            color,
            obj.delivery_status or 'Pending'
        )
    delivery_status_display.short_description = 'Status'
    
    def get_queryset(self, request):
        """Optimize queryset"""
        qs = super().get_queryset(request)
        return qs.select_related('notification', 'notification__user')


@admin.register(SMSLog)
class SMSLogAdmin(admin.ModelAdmin):
    """SMS log admin"""
    
    list_display = [
        'to_phone', 'delivery_status_display', 
        'sent_at', 'provider_message_id'
    ]
    list_filter = ['delivery_status', 'sent_at']
    search_fields = ['to_phone', 'provider_message_id']
    readonly_fields = ['sent_at']
    date_hierarchy = 'sent_at'
    
    fieldsets = (
        ('SMS Details', {
            'fields': ('notification', 'to_phone', 'message')
        }),
        ('Delivery Info', {
            'fields': ('delivery_status', 'error_message', 'provider_message_id')
        }),
        ('Timestamp', {
            'fields': ('sent_at',)
        }),
    )
    
    def delivery_status_display(self, obj):
        """Display colored delivery status"""
        colors = {
            'sent': 'green',
            'failed': 'red',
            'delivered': 'blue',
        }
        color = colors.get(obj.delivery_status, 'gray')
        return format_html(
            '<span style="color: {}; font-weight: bold;">{}</span>',
            color,
            obj.delivery_status or 'Pending'
        )
    delivery_status_display.short_description = 'Status'
    
    def get_queryset(self, request):
        """Optimize queryset"""
        qs = super().get_queryset(request)
        return qs.select_related('notification', 'notification__user')


@admin.register(NotificationPreference)
class NotificationPreferenceAdmin(admin.ModelAdmin):
    """Notification preference admin"""
    
    list_display = [
        'user_email', 'email_notifications', 'sms_notifications', 
        'push_notifications', 'webinar_reminders'
    ]
    list_filter = [
        'email_notifications', 'sms_notifications', 
        'push_notifications', 'webinar_reminders'
    ]
    search_fields = ['user__email']
    
    fieldsets = (
        ('User', {
            'fields': ('user',)
        }),
        ('Notification Channels', {
            'fields': (
                'email_notifications', 
                'sms_notifications', 
                'push_notifications'
            )
        }),
        ('Preferences', {
            'fields': (
                'webinar_reminders', 
                'marketing_emails', 
                'payment_notifications', 
                'instructor_updates', 
                'reminder_time'
            )
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )
    
    readonly_fields = ['created_at', 'updated_at']
    
    def user_email(self, obj):
        """Display user email"""
        return obj.user.email
    user_email.short_description = 'User'
    user_email.admin_order_field = 'user__email'
    
    def get_queryset(self, request):
        """Optimize queryset"""
        qs = super().get_queryset(request)
        return qs.select_related('user')
