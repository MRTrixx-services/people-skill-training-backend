# apps/integrations/admin.py - Fixed admin with proper actions
from django.contrib import admin
from django.utils.html import format_html
from django.urls import reverse
from django.utils.safestring import mark_safe
from django.db.models import Count, Q
from django.core.exceptions import PermissionDenied
from django.contrib import messages
from django.http import HttpResponseRedirect
from .models import (
    ZoomCredentials,
    ZoomMeeting,
    ZoomWebinar,
    ZoomRecording,
    ZoomWebhookEvent,
    ZoomIntegrationLog
)

@admin.register(ZoomCredentials)
class ZoomCredentialsAdmin(admin.ModelAdmin):
    """Enhanced admin interface for Zoom credentials with security"""
    
    list_display = ['name', 'client_id_masked', 'account_id_masked', 'is_active_badge', 'connection_test_status', 'created_at']
    list_filter = ['is_active', 'created_at']
    search_fields = ['name', 'description']
    readonly_fields = ['created_at', 'updated_at']
    
    def get_queryset(self, request):
        return super().get_queryset(request).select_related()
    
    fieldsets = (
        ('Application Details', {
            'fields': ('name', 'description', 'is_active')
        }),
        ('Zoom API Credentials', {
            'fields': ('client_id', 'client_secret', 'account_id'),
            'classes': ('collapse',),
            'description': 'Server-to-Server OAuth credentials from Zoom Marketplace'
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )
    
    # FIXED: Proper actions list
    actions = ['test_connection_action', 'activate_credentials', 'deactivate_credentials']
    
    def client_id_masked(self, obj):
        """Display masked client ID for security"""
        if obj.client_id:
            return f"{obj.client_id[:10]}***"
        return "N/A"
    client_id_masked.short_description = 'Client ID'
    client_id_masked.admin_order_field = 'client_id'
    
    def account_id_masked(self, obj):
        """Display masked account ID for security"""
        if obj.account_id:
            return f"{obj.account_id[:8]}***"
        return "N/A"
    account_id_masked.short_description = 'Account ID'
    account_id_masked.admin_order_field = 'account_id'
    
    def is_active_badge(self, obj):
        """Display active status as a badge"""
        if obj.is_active:
            return format_html(
                '<span style="background-color: #28a745; color: white; padding: 3px 8px; '
                'border-radius: 4px; font-size: 11px; font-weight: bold;">ACTIVE</span>'
            )
        return format_html(
            '<span style="background-color: #6c757d; color: white; padding: 3px 8px; '
            'border-radius: 4px; font-size: 11px; font-weight: bold;">INACTIVE</span>'
        )
    is_active_badge.short_description = 'Status'
    is_active_badge.admin_order_field = 'is_active'
    
    def connection_test_status(self, obj):
        """Display connection test status"""
        if not obj.is_active:
            return format_html('<span style="color: #6c757d;">Inactive</span>')
        
        try:
            from .services import ZoomAPIService
            # Only test if this is the active credential
            if obj.is_active:
                api = ZoomAPIService()
                result = api.test_connection()
                if result['success']:
                    return format_html(
                        '<span style="color: #28a745; font-weight: bold;">✓ OK</span>'
                    )
                else:
                    return format_html(
                        '<span style="color: #dc3545; font-weight: bold;">✗ Failed</span>'
                    )
        except Exception:
            return format_html(
                '<span style="color: #ffc107;">Unknown</span>'
            )
        
        return format_html('<span style="color: #6c757d;">N/A</span>')
    connection_test_status.short_description = 'Connection'
    
    # FIXED: Renamed to avoid conflicts
    def test_connection_action(self, request, queryset):
        """Admin action to test Zoom connection"""
        if queryset.count() != 1:
            self.message_user(request, "Please select exactly one credential to test.", level=messages.WARNING)
            return
        
        credential = queryset.first()
        if not credential.is_active:
            self.message_user(request, "Cannot test inactive credentials.", level=messages.WARNING)
            return
        
        try:
            from .services import ZoomAPIService
            api = ZoomAPIService()
            result = api.test_connection()
            
            if result['success']:
                self.message_user(
                    request, 
                    f"✅ Connection successful! Connected as: {result.get('user_email', 'Unknown user')}", 
                    level=messages.SUCCESS
                )
            else:
                self.message_user(
                    request, 
                    f"❌ Connection failed: {result.get('error', 'Unknown error')}", 
                    level=messages.ERROR
                )
        except Exception as e:
            self.message_user(request, f"❌ Test failed: {str(e)}", level=messages.ERROR)
    
    test_connection_action.short_description = "Test Zoom API connection"
    
    def activate_credentials(self, request, queryset):
        """Activate selected credentials (only one can be active)"""
        if queryset.count() != 1:
            self.message_user(request, "Please select exactly one credential to activate.", level=messages.WARNING)
            return
        
        # Deactivate all others first
        ZoomCredentials.objects.all().update(is_active=False)
        
        # Activate selected
        credential = queryset.first()
        credential.is_active = True
        credential.save()
        
        self.message_user(request, f"✅ Activated '{credential.name}' credentials.", level=messages.SUCCESS)
    
    activate_credentials.short_description = "Activate selected credentials"
    
    def deactivate_credentials(self, request, queryset):
        """Deactivate selected credentials"""
        count = queryset.update(is_active=False)
        self.message_user(request, f"Deactivated {count} credential(s).", level=messages.SUCCESS)
    
    deactivate_credentials.short_description = "Deactivate selected credentials"

@admin.register(ZoomMeeting)
class ZoomMeetingAdmin(admin.ModelAdmin):
    """Enhanced admin interface for Zoom meetings"""
    
    list_display = [
        'topic_truncated', 
        'zoom_meeting_id', 
        'status_colored', 
        'start_time_formatted',
        'duration_formatted',
        'recordings_count',
        'webinar_link',
        'join_action'
    ]
    list_filter = [
        'status', 
        'meeting_type', 
        'auto_recording',
        'waiting_room',
        ('start_time', admin.DateFieldListFilter),
        ('created_at', admin.DateFieldListFilter)
    ]
    search_fields = ['topic', 'zoom_meeting_id', 'webinar__title', 'webinar__webinar_id']
    readonly_fields = [
        'zoom_meeting_id', 
        'uuid', 
        'host_id', 
        'join_url_clickable', 
        'start_url_clickable', 
        'created_at', 
        'updated_at',
        'is_active'
    ]
    
    list_per_page = 25
    list_max_show_all = 100
    
    # FIXED: Proper actions list
    actions = ['sync_with_zoom', 'update_meeting_status']
    
    def get_queryset(self, request):
        return super().get_queryset(request).select_related(
            'webinar__speaker', 'webinar__category', 'created_by'
        ).prefetch_related('recordings')
    
    def topic_truncated(self, obj):
        """Display truncated topic for better layout"""
        if obj.topic:
            return obj.topic[:50] + "..." if len(obj.topic) > 50 else obj.topic
        return "N/A"
    topic_truncated.short_description = 'Topic'
    topic_truncated.admin_order_field = 'topic'
    
    def status_colored(self, obj):
        """Display status with color coding"""
        colors = {
            'waiting': '#ffa500',  # orange
            'started': '#32cd32',  # green
            'ended': '#dc143c'     # red
        }
        color = colors.get(obj.status, '#000000')
        return format_html(
            '<span style="color: {}; font-weight: bold;">{}</span>',
            color, obj.get_status_display()
        )
    status_colored.short_description = 'Status'
    status_colored.admin_order_field = 'status'
    
    def start_time_formatted(self, obj):
        """Format start time for display"""
        if obj.start_time:
            return obj.start_time.strftime('%Y-%m-%d %H:%M')
        return "N/A"
    start_time_formatted.short_description = 'Start Time'
    start_time_formatted.admin_order_field = 'start_time'
    
    def duration_formatted(self, obj):
        """Format duration in hours and minutes"""
        if obj.duration:
            hours = obj.duration // 60
            minutes = obj.duration % 60
            if hours > 0:
                return f"{hours}h {minutes}m"
            return f"{minutes}m"
        return "N/A"
    duration_formatted.short_description = 'Duration'
    duration_formatted.admin_order_field = 'duration'
    
    def recordings_count(self, obj):
        """Show number of recordings with badge"""
        count = obj.recordings.count()
        if count > 0:
            return format_html(
                '<span style="background-color: #17a2b8; color: white; padding: 2px 6px; '
                'border-radius: 3px; font-size: 10px; font-weight: bold;">{}</span>', count
            )
        return "0"
    recordings_count.short_description = 'Recordings'
    
    def webinar_link(self, obj):
        """Enhanced webinar link with more info"""
        if obj.webinar:
            url = reverse('admin:webinars_webinar_change', args=[obj.webinar.pk])
            return format_html(
                '<a href="{}" title="{}">{}</a>',
                url, 
                obj.webinar.title,
                obj.webinar.webinar_id
            )
        return "No webinar"
    webinar_link.short_description = 'Webinar'
    
    def join_action(self, obj):
        """Quick join action button"""
        if obj.join_url:
            return format_html(
                '<a href="{}" target="_blank" rel="noopener" '
                'style="background: #007bff; color: white; padding: 4px 8px; '
                'text-decoration: none; border-radius: 3px; font-size: 11px;">JOIN</a>',
                obj.join_url
            )
        return "N/A"
    join_action.short_description = 'Quick Join'
    
    def join_url_clickable(self, obj):
        """Make join URL clickable"""
        if obj.join_url:
            return format_html(
                '<a href="{}" target="_blank" rel="noopener">Join Meeting</a>',
                obj.join_url
            )
        return "N/A"
    join_url_clickable.short_description = 'Join URL'
    
    def start_url_clickable(self, obj):
        """Make start URL clickable"""
        if obj.start_url:
            return format_html(
                '<a href="{}" target="_blank" rel="noopener">Start Meeting</a>',
                obj.start_url
            )
        return "N/A"
    start_url_clickable.short_description = 'Start URL'
    
    def sync_with_zoom(self, request, queryset):
        """Admin action to sync meetings with Zoom"""
        success_count = 0
        error_count = 0
        
        for meeting in queryset:
            try:
                from .services import ZoomAPIService
                api = ZoomAPIService()
                zoom_data = api.get_meeting(meeting.zoom_meeting_id)
                
                # Update local data with Zoom data
                meeting.status = zoom_data.get('status', meeting.status)
                meeting.topic = zoom_data.get('topic', meeting.topic)
                meeting.save()
                
                success_count += 1
            except Exception as e:
                error_count += 1
        
        if success_count > 0:
            self.message_user(request, f"✅ Synced {success_count} meeting(s) with Zoom.", level=messages.SUCCESS)
        if error_count > 0:
            self.message_user(request, f"❌ Failed to sync {error_count} meeting(s).", level=messages.WARNING)
    
    sync_with_zoom.short_description = "Sync with Zoom"
    
    def update_meeting_status(self, request, queryset):
        """Update meeting status based on current time"""
        from django.utils import timezone
        
        now = timezone.now()
        updated_count = 0
        
        for meeting in queryset:
            old_status = meeting.status
            
            if now < meeting.start_time:
                new_status = 'waiting'
            elif now >= meeting.start_time and now <= meeting.start_time + timezone.timedelta(minutes=meeting.duration):
                new_status = 'started'
            else:
                new_status = 'ended'
            
            if old_status != new_status:
                meeting.status = new_status
                meeting.save()
                updated_count += 1
        
        self.message_user(request, f"Updated status for {updated_count} meeting(s).", level=messages.SUCCESS)
    
    update_meeting_status.short_description = "Update status based on time"

@admin.register(ZoomWebinar)
class ZoomWebinarAdmin(admin.ModelAdmin):
    """Enhanced admin interface for Zoom webinars"""
    
    list_display = [
        'topic_truncated', 
        'zoom_webinar_id', 
        'status_colored', 
        'start_time_formatted',
        'duration_formatted',
        'approval_type_badge',
        'recordings_count',
        'webinar_link'
    ]
    list_filter = [
        'status', 
        'webinar_type', 
        'approval_type',
        'registration_type',
        'auto_recording',
        ('start_time', admin.DateFieldListFilter),
        ('created_at', admin.DateFieldListFilter)
    ]
    search_fields = ['topic', 'zoom_webinar_id', 'webinar__title', 'webinar__webinar_id']
    readonly_fields = [
        'zoom_webinar_id', 
        'uuid', 
        'host_id', 
        'join_url_clickable', 
        'registration_url_clickable', 
        'created_at', 
        'updated_at',
        'is_active'
    ]
    
    list_per_page = 25
    
    def get_queryset(self, request):
        return super().get_queryset(request).select_related(
            'webinar__speaker', 'webinar__category', 'created_by'
        ).prefetch_related('recordings')
    
    def topic_truncated(self, obj):
        if obj.topic:
            return obj.topic[:50] + "..." if len(obj.topic) > 50 else obj.topic
        return "N/A"
    topic_truncated.short_description = 'Topic'
    topic_truncated.admin_order_field = 'topic'
    
    def status_colored(self, obj):
        colors = {
            'waiting': '#ffa500',
            'started': '#32cd32',
            'ended': '#dc143c'
        }
        color = colors.get(obj.status, '#000000')
        return format_html(
            '<span style="color: {}; font-weight: bold;">{}</span>',
            color, obj.get_status_display()
        )
    status_colored.short_description = 'Status'
    status_colored.admin_order_field = 'status'
    
    def start_time_formatted(self, obj):
        if obj.start_time:
            return obj.start_time.strftime('%Y-%m-%d %H:%M')
        return "N/A"
    start_time_formatted.short_description = 'Start Time'
    start_time_formatted.admin_order_field = 'start_time'
    
    def duration_formatted(self, obj):
        if obj.duration:
            hours = obj.duration // 60
            minutes = obj.duration % 60
            if hours > 0:
                return f"{hours}h {minutes}m"
            return f"{minutes}m"
        return "N/A"
    duration_formatted.short_description = 'Duration'
    
    def approval_type_badge(self, obj):
        """Display approval type as badge"""
        colors = {0: '#28a745', 1: '#ffc107', 2: '#17a2b8'}
        labels = {0: 'AUTO', 1: 'MANUAL', 2: 'NONE'}
        color = colors.get(obj.approval_type, '#6c757d')
        label = labels.get(obj.approval_type, 'UNK')
        return format_html(
            '<span style="background-color: {}; color: white; padding: 2px 6px; '
            'border-radius: 3px; font-size: 10px; font-weight: bold;">{}</span>', color, label
        )
    approval_type_badge.short_description = 'Approval'
    
    def recordings_count(self, obj):
        count = obj.recordings.count()
        if count > 0:
            return format_html(
                '<span style="background-color: #17a2b8; color: white; padding: 2px 6px; '
                'border-radius: 3px; font-size: 10px; font-weight: bold;">{}</span>', count
            )
        return "0"
    recordings_count.short_description = 'Recordings'
    
    def webinar_link(self, obj):
        """Enhanced webinar link"""
        if obj.webinar:
            url = reverse('admin:webinars_webinar_change', args=[obj.webinar.pk])
            return format_html(
                '<a href="{}" title="{}">{}</a>',
                url, 
                obj.webinar.title,
                obj.webinar.webinar_id
            )
        return "No webinar"
    webinar_link.short_description = 'Webinar'
    
    def join_url_clickable(self, obj):
        if obj.join_url:
            return format_html(
                '<a href="{}" target="_blank" rel="noopener">Join Webinar</a>',
                obj.join_url
            )
        return "N/A"
    join_url_clickable.short_description = 'Join URL'
    
    def registration_url_clickable(self, obj):
        if obj.registration_url:
            return format_html(
                '<a href="{}" target="_blank" rel="noopener">Register</a>',
                obj.registration_url
            )
        return "N/A"
    registration_url_clickable.short_description = 'Registration'

@admin.register(ZoomRecording)
class ZoomRecordingAdmin(admin.ModelAdmin):
    """Enhanced admin interface for Zoom recordings"""
    
    list_display = [
        'recording_id_short',
        'topic_short',
        'recording_type_badge',
        'file_type_badge',
        'status_colored',
        'file_size_formatted',
        'recording_start_formatted',
        'duration_calculated',
        'quick_actions'
    ]
    list_filter = [
        'recording_type', 
        'file_type', 
        'status', 
        ('recording_start', admin.DateFieldListFilter),
        ('created_at', admin.DateFieldListFilter)
    ]
    search_fields = ['recording_id', 'meeting_id', 'topic']
    readonly_fields = [
        'recording_id', 
        'meeting_id', 
        'file_size', 
        'file_extension',
        'download_url_clickable', 
        'play_url_clickable',
        'duration_minutes',
        'file_size_mb',
        'created_at', 
        'updated_at'
    ]
    
    list_per_page = 50
    
    def get_queryset(self, request):
        return super().get_queryset(request).select_related(
            'zoom_meeting__webinar',
            'zoom_webinar__webinar'
        )
    
    def recording_id_short(self, obj):
        if obj.recording_id:
            return f"{obj.recording_id[:15]}..."
        return "N/A"
    recording_id_short.short_description = 'Recording ID'
    
    def topic_short(self, obj):
        if obj.topic:
            return obj.topic[:30] + "..." if len(obj.topic) > 30 else obj.topic
        return "N/A"
    topic_short.short_description = 'Topic'
    
    def recording_type_badge(self, obj):
        """Display recording type as badge"""
        type_colors = {
            'shared_screen_with_speaker_view': '#007bff',
            'shared_screen_with_gallery_view': '#6f42c1',
            'speaker_view': '#28a745',
            'gallery_view': '#fd7e14',
            'shared_screen': '#20c997',
            'audio_only': '#6c757d',
            'chat_file': '#ffc107'
        }
        color = type_colors.get(obj.recording_type, '#6c757d')
        display_name = obj.recording_type.replace('_', ' ').title()[:15]
        return format_html(
            '<span style="background-color: {}; color: white; padding: 2px 4px; '
            'border-radius: 3px; font-size: 9px; font-weight: bold;">{}</span>',
            color, display_name
        )
    recording_type_badge.short_description = 'Type'
    
    def file_type_badge(self, obj):
        colors = {
            'MP4': '#28a745',
            'M4A': '#17a2b8',
            'TXT': '#6c757d',
            'VTT': '#ffc107',
            'CSV': '#fd7e14',
            'JSON': '#6f42c1'
        }
        color = colors.get(obj.file_type.upper(), '#6c757d')
        return format_html(
            '<span style="background-color: {}; color: white; padding: 2px 6px; '
            'border-radius: 3px; font-size: 10px; font-weight: bold;">{}</span>',
            color, obj.file_type.upper()
        )
    file_type_badge.short_description = 'Format'
    
    def status_colored(self, obj):
        colors = {
            'processing': '#ffa500',
            'completed': '#32cd32',
            'failed': '#dc143c'
        }
        color = colors.get(obj.status, '#000000')
        return format_html(
            '<span style="color: {}; font-weight: bold;">{}</span>',
            color, obj.get_status_display()
        )
    status_colored.short_description = 'Status'
    
    def file_size_formatted(self, obj):
        if obj.file_size:
            return f"{obj.file_size_mb:.1f} MB"
        return "N/A"
    file_size_formatted.short_description = 'Size'
    
    def recording_start_formatted(self, obj):
        if obj.recording_start:
            return obj.recording_start.strftime('%m/%d %H:%M')
        return "N/A"
    recording_start_formatted.short_description = 'Started'
    recording_start_formatted.admin_order_field = 'recording_start'
    
    def duration_calculated(self, obj):
        return f"{obj.duration_minutes}m" if obj.duration_minutes else "N/A"
    duration_calculated.short_description = 'Duration'
    
    def quick_actions(self, obj):
        """Quick action buttons"""
        buttons = []
        if obj.play_url:
            buttons.append(f'<a href="{obj.play_url}" target="_blank" style="margin-right:5px; background:#007bff; color:white; padding:2px 6px; text-decoration:none; border-radius:3px; font-size:10px;">Play</a>')
        if obj.download_url:
            buttons.append(f'<a href="{obj.download_url}" target="_blank" style="background:#28a745; color:white; padding:2px 6px; text-decoration:none; border-radius:3px; font-size:10px;">Download</a>')
        
        return format_html(''.join(buttons)) if buttons else "N/A"
    quick_actions.short_description = 'Actions'
    
    def download_url_clickable(self, obj):
        if obj.download_url:
            return format_html(
                '<a href="{}" target="_blank" rel="noopener">Download</a>',
                obj.download_url
            )
        return "N/A"
    download_url_clickable.short_description = 'Download'
    
    def play_url_clickable(self, obj):
        if obj.play_url:
            return format_html(
                '<a href="{}" target="_blank" rel="noopener">Play</a>',
                obj.play_url
            )
        return "N/A"
    play_url_clickable.short_description = 'Play'

@admin.register(ZoomWebhookEvent)
class ZoomWebhookEventAdmin(admin.ModelAdmin):
    """Enhanced admin interface for Zoom webhook events"""
    
    list_display = [
        'event_type_badge',
        'processed_status', 
        'processing_attempts_badge',
        'source_ip',
        'created_at_short',
        'processing_time'
    ]
    list_filter = [
        'event_type', 
        'processed', 
        'processing_attempts',
        ('created_at', admin.DateFieldListFilter)
    ]
    search_fields = ['event_type', 'source_ip']
    readonly_fields = [
        'event_type', 
        'event_ts',
        'event_data', 
        'source_ip',
        'user_agent',
        'created_at',
        'processed_at'
    ]
    
    list_per_page = 50
    
    # FIXED: Proper actions list
    actions = ['mark_as_processed', 'retry_processing', 'delete_old_events']
    
    def event_type_badge(self, obj):
        """Display event type as colored badge"""
        type_colors = {
            'meeting.started': '#28a745',
            'meeting.ended': '#dc3545',
            'meeting.participant_joined': '#17a2b8',
            'meeting.participant_left': '#6c757d',
            'recording.completed': '#ffc107',
            'webinar.started': '#28a745',
            'webinar.ended': '#dc3545'
        }
        color = type_colors.get(obj.event_type, '#6c757d')
        return format_html(
            '<span style="background-color: {}; color: white; padding: 2px 6px; '
            'border-radius: 3px; font-size: 10px; font-weight: bold;">{}</span>',
            color, obj.event_type
        )
    event_type_badge.short_description = 'Event Type'
    
    def created_at_short(self, obj):
        return obj.created_at.strftime('%m/%d %H:%M')
    created_at_short.short_description = 'Created'
    created_at_short.admin_order_field = 'created_at'
    
    def processed_status(self, obj):
        if obj.processed:
            return format_html(
                '<span style="color: #28a745; font-weight: bold;">✓ Done</span>'
            )
        elif obj.processing_error:
            return format_html(
                '<span style="color: #dc3545; font-weight: bold;">✗ Error</span>'
            )
        else:
            return format_html(
                '<span style="color: #ffc107; font-weight: bold;">⏳ Pending</span>'
            )
    processed_status.short_description = 'Status'
    
    def processing_attempts_badge(self, obj):
        if obj.processing_attempts > 0:
            color = '#dc3545' if obj.processing_attempts >= 3 else '#ffc107'
            return format_html(
                '<span style="background-color: {}; color: white; padding: 2px 6px; '
                'border-radius: 3px; font-size: 10px; font-weight: bold;">{}</span>',
                color, obj.processing_attempts
            )
        return "0"
    processing_attempts_badge.short_description = 'Attempts'
    
    def processing_time(self, obj):
        if obj.processed_at and obj.created_at:
            delta = obj.processed_at - obj.created_at
            return f"{delta.total_seconds():.1f}s"
        return "N/A"
    processing_time.short_description = 'Time'
    
    def has_add_permission(self, request):
        return False
    
    def mark_as_processed(self, request, queryset):
        """Mark events as processed"""
        updated = queryset.update(processed=True, processing_error=None)
        self.message_user(request, f'✅ Marked {updated} events as processed.', level=messages.SUCCESS)
    mark_as_processed.short_description = "Mark as processed"
    
    def retry_processing(self, request, queryset):
        """Retry failed events"""
        updated = queryset.update(processed=False, processing_error=None, processing_attempts=0)
        self.message_user(request, f'🔄 Queued {updated} events for retry.', level=messages.SUCCESS)
    retry_processing.short_description = "Retry processing"
    
    def delete_old_events(self, request, queryset):
        """Delete events older than 30 days"""
        from django.utils import timezone
        cutoff_date = timezone.now() - timezone.timedelta(days=30)
        old_events = queryset.filter(created_at__lt=cutoff_date)
        count = old_events.count()
        old_events.delete()
        self.message_user(request, f'🗑️ Deleted {count} old events.', level=messages.SUCCESS)
    delete_old_events.short_description = "Delete old events (30+ days)"

@admin.register(ZoomIntegrationLog)
class ZoomIntegrationLogAdmin(admin.ModelAdmin):
    """Enhanced admin interface for Zoom integration logs"""
    
    list_display = [
        'level_badge',
        'action_type_short',
        'user_link',
        'status_code_colored',
        'execution_time_formatted',
        'created_at_short'
    ]
    list_filter = [
        'level',
        'action_type',
        ('status_code', admin.AllValuesFieldListFilter),
        ('created_at', admin.DateFieldListFilter)
    ]
    search_fields = [
        'user__email',
        'user__first_name',
        'user__last_name',
        'message',
        'action_type'
    ]
    readonly_fields = ['created_at']
    
    list_per_page = 100
    list_max_show_all = 500
    
    # FIXED: Proper actions list
    actions = ['delete_old_logs']
    
    def get_queryset(self, request):
        return super().get_queryset(request).select_related('user')
    
    def level_badge(self, obj):
        colors = {
            'DEBUG': '#6c757d',
            'INFO': '#17a2b8', 
            'WARNING': '#ffc107',
            'ERROR': '#dc3545',
            'CRITICAL': '#6f42c1'
        }
        color = colors.get(obj.level, '#000000')
        return format_html(
            '<span style="background-color: {}; color: white; padding: 2px 6px; '
            'border-radius: 3px; font-size: 10px; font-weight: bold;">{}</span>',
            color, obj.level
        )
    level_badge.short_description = 'Level'
    level_badge.admin_order_field = 'level'
    
    def action_type_short(self, obj):
        """Truncate long action types"""
        return obj.action_type.replace('_', ' ').title()[:20]
    action_type_short.short_description = 'Action'
    action_type_short.admin_order_field = 'action_type'
    
    def user_link(self, obj):
        if obj.user:
            return obj.user.get_full_name() or obj.user.email
        return "System"
    user_link.short_description = 'User'
    
    def status_code_colored(self, obj):
        if obj.status_code:
            if 200 <= obj.status_code < 300:
                color = '#28a745'
            elif 300 <= obj.status_code < 400:
                color = '#17a2b8'
            elif 400 <= obj.status_code < 500:
                color = '#ffc107'
            else:
                color = '#dc3545'
            
            return format_html(
                '<span style="color: {}; font-weight: bold;">{}</span>',
                color, obj.status_code
            )
        return "N/A"
    status_code_colored.short_description = 'Status'
    status_code_colored.admin_order_field = 'status_code'
    
    def execution_time_formatted(self, obj):
        if obj.execution_time is not None:
            if obj.execution_time >= 1:
                return f"{obj.execution_time:.2f}s"
            else:
                return f"{obj.execution_time * 1000:.0f}ms"
        return "N/A"
    execution_time_formatted.short_description = 'Duration'
    execution_time_formatted.admin_order_field = 'execution_time'
    
    def created_at_short(self, obj):
        return obj.created_at.strftime('%m/%d %H:%M')
    created_at_short.short_description = 'Time'
    created_at_short.admin_order_field = 'created_at'
    
    def has_add_permission(self, request):
        return False
    
    def has_change_permission(self, request, obj=None):
        return False
    
    def delete_old_logs(self, request, queryset):
        """Delete logs older than 7 days"""
        from django.utils import timezone
        cutoff_date = timezone.now() - timezone.timedelta(days=7)
        old_logs = queryset.filter(created_at__lt=cutoff_date)
        count = old_logs.count()
        old_logs.delete()
        self.message_user(request, f'🗑️ Deleted {count} old logs.', level=messages.SUCCESS)
    delete_old_logs.short_description = "Delete old logs (7+ days)"

# Enhanced admin site configuration
admin.site.site_header = "🎯 Zoom Integration Admin"
admin.site.site_title = "Zoom Integration"
admin.site.index_title = "Zoom Integration Dashboard"
