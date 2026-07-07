# apps/webinars/admin.py - Updated for Zoom integration and Platform Pricing
from django.contrib import admin
from django.utils.html import format_html
from django.urls import reverse
from django.utils.safestring import mark_safe
from .models import (
    Category, Webinar, WebinarResource, WebinarSession, 
    WebinarReview, WebinarAnalytics, WebinarPlatformPrice
)


@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    """Category admin"""
    
    list_display = ('name', 'color_display', 'is_active', 'webinar_count', 'created_at')
    list_filter = ('is_active', 'created_at')
    search_fields = ('name', 'description')
    
    def color_display(self, obj):
        return format_html(
            '<span style="background-color: {}; padding: 5px 10px; color: white; border-radius: 3px;">{}</span>',
            obj.color,
            obj.color
        )
    color_display.short_description = 'Color'
    
    def webinar_count(self, obj):
        return obj.webinar_set.count()
    webinar_count.short_description = 'Webinars'


class WebinarResourceInline(admin.TabularInline):
    """Inline for webinar resources"""
    model = WebinarResource
    extra = 0
    fields = ('title', 'resource_type', 'file', 'url', 'is_public', 'is_downloadable')


class WebinarSessionInline(admin.TabularInline):
    """Inline for webinar sessions"""
    model = WebinarSession
    extra = 0
    fields = ('session_number', 'title', 'scheduled_date', 'duration', 'is_completed')
    ordering = ['session_number']


class WebinarPlatformPriceInline(admin.TabularInline):
    """Inline for platform-specific pricing"""
    model = WebinarPlatformPrice
    extra = 0
    fields = ['platform', 'pricing_data', 'discount_percentage', 'is_active']
    raw_id_fields = ('platform',)
    
    def get_formset(self, request, obj=None, **kwargs):
        formset = super().get_formset(request, obj, **kwargs)
        formset.form.base_fields['pricing_data'].help_text = """
        Platform-specific pricing override. Example:
        {
          "live_single_price": 129.00,
          "live_multi_price": 449.00,
          "recorded_single_price": 69.00,
          "recorded_multi_price": 219.00,
          "combo_single_price": 179.00,
          "combo_multi_price": 579.00
        }
        """
        return formset


@admin.register(Webinar)
class WebinarAdmin(admin.ModelAdmin):
    """Enhanced Webinar admin with Zoom and Platform Pricing"""
    list_display = (
        'webinar_id', 'title', 'speaker', 'category', 'webinar_type', 
        'status', 'scheduled_date_display', 'enrolled_count', 
        'platform_pricing_count', 'zoom_status_display'
    )
    list_filter = (
        'webinar_type', 'status', 'category', 'skill_level',
        'has_enrollment_limit', 'created_at'
    )
    search_fields = ('webinar_id', 'title', 'description', 'speaker__first_name', 'speaker__last_name')
   
    raw_id_fields = ('speaker',)
    readonly_fields = ('webinar_id', 'zoom_info_display', 'created_at', 'updated_at') 
    
    date_hierarchy = 'scheduled_date'
    
    fieldsets = (
        ('Basic Information', {
            'fields': ('webinar_id', 'title', 'description', 'speaker', 'category', 'skill_level')
        }),
        ('Webinar Type', {
            'fields': ('webinar_type',),
            'description': 'Choose between live session or recorded content'
        }),
        ('Scheduling (Live Webinars Only)', {
            'fields': ('scheduled_date', 'duration', 'timezone'),
            'classes': ('collapse',),
            'description': 'Required only for live webinars'
        }),
        ('Recorded Content (Recorded Webinars Only)', {
            'fields': ('zoom_url',),
            'classes': ('collapse',),
            'description': 'Zoom recording URL for recorded webinars'
        }),
        ('Default Pricing', {
            'fields': ('pricing_data',),
            'description': 'Default pricing for all platforms (can be overridden per platform below)'
        }),
        ('Capacity', {
            'fields': ('has_enrollment_limit', 'max_attendees')
        }),
        ('Media', {
            'fields': ('cover_image',)
        }),
        ('Settings', {
            'fields': ('status', 'zoom_preferences'),
            'description': 'Zoom preferences only apply to live webinars'
        }),
        ('Zoom Integration', {
            'fields': ('zoom_info_display',),
            'classes': ('collapse',),
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )
    
    # ✅ Add platform pricing inline
    inlines = [WebinarPlatformPriceInline, WebinarResourceInline, WebinarSessionInline]
    
    actions = ['sync_zoom_meetings', 'update_webinar_status']
    
    # ✅ Display platform pricing count
    def platform_pricing_count(self, obj):
        count = obj.platform_prices.filter(is_active=True).count()
        if count > 0:
            return format_html(
                '<span style="background-color: #10b981; color: white; padding: 3px 8px; border-radius: 3px; font-weight: bold;">'
                '{} platform{}</span>',
                count,
                's' if count > 1 else ''
            )
        return format_html('<span style="color: #6b7280;">Default only</span>')
    platform_pricing_count.short_description = 'Platform Pricing'
    
    def enrolled_count(self, obj):
        return obj.enrolled_count
    enrolled_count.short_description = 'Enrolled'
    enrolled_count.admin_order_field = 'enrolled_count'
    
    def zoom_status_display(self, obj):
        """Enhanced Zoom status display for both types"""
        if obj.webinar_type == 'recorded':
            if obj.zoom_url:
                return format_html(
                    '<span style="color: blue; font-weight: bold;">✓ URL Provided</span><br>'
                    '<small>Recorded Content</small>'
                )
            else:
                return format_html('<span style="color: orange;">⚠ URL Missing</span>')
        
        # Live webinar Zoom status
        zoom_meeting = getattr(obj, 'zoom_meeting_rel', None)
        zoom_webinar = getattr(obj, 'zoom_webinar_rel', None)
        
        if zoom_meeting:
            return format_html(
                '<span style="color: green; font-weight: bold;">✓ Meeting</span><br>'
                '<small>ID: {}</small>',
                zoom_meeting.zoom_meeting_id
            )
        elif zoom_webinar:
            return format_html(
                '<span style="color: blue; font-weight: bold;">✓ Webinar</span><br>'
                '<small>ID: {}</small>',
                zoom_webinar.zoom_webinar_id
            )
        else:
            return format_html('<span style="color: red;">✗ No Zoom</span>')
    
    zoom_status_display.short_description = 'Zoom Status'

    def scheduled_date_display(self, obj):
        """Display scheduled date with type context"""
        if obj.webinar_type == 'recorded':
            return format_html('<em style="color: #666;">On-Demand</em>')
        elif obj.scheduled_date:
            return obj.scheduled_date.strftime('%Y-%m-%d %H:%M')
        return '-'
    scheduled_date_display.short_description = 'Schedule'
    
    def zoom_info_display(self, obj):
        """Display detailed Zoom information"""
        zoom_meeting = getattr(obj, 'zoom_meeting_rel', None)
        zoom_webinar = getattr(obj, 'zoom_webinar_rel', None)
        
        if zoom_meeting:
            return format_html(
                '<div style="background: #f0f8ff; padding: 10px; border-radius: 5px;">'
                '<h4 style="margin: 0 0 10px 0; color: #1e40af;">🎯 Zoom Meeting</h4>'
                '<p><strong>Meeting ID:</strong> {}</p>'
                '<p><strong>Join URL:</strong> <a href="{}" target="_blank">{}</a></p>'
                '<p><strong>Start URL:</strong> <a href="{}" target="_blank">Host Link</a></p>'
                '<p><strong>Status:</strong> <span style="color: green;">{}</span></p>'
                '<p><strong>Created:</strong> {}</p>'
                '</div>',
                zoom_meeting.zoom_meeting_id,
                zoom_meeting.join_url,
                zoom_meeting.join_url[:50] + '...' if len(zoom_meeting.join_url) > 50 else zoom_meeting.join_url,
                zoom_meeting.start_url,
                zoom_meeting.status.title(),
                zoom_meeting.created_at.strftime('%Y-%m-%d %H:%M')
            )
        elif zoom_webinar:
            return format_html(
                '<div style="background: #f0f8ff; padding: 10px; border-radius: 5px;">'
                '<h4 style="margin: 0 0 10px 0; color: #1e40af;">📺 Zoom Webinar</h4>'
                '<p><strong>Webinar ID:</strong> {}</p>'
                '<p><strong>Join URL:</strong> <a href="{}" target="_blank">{}</a></p>'
                '<p><strong>Status:</strong> <span style="color: green;">{}</span></p>'
                '<p><strong>Created:</strong> {}</p>'
                '</div>',
                zoom_webinar.zoom_webinar_id,
                zoom_webinar.join_url,
                zoom_webinar.join_url[:50] + '...' if len(zoom_webinar.join_url) > 50 else zoom_webinar.join_url,
                zoom_webinar.status.title(),
                zoom_webinar.created_at.strftime('%Y-%m-%d %H:%M')
            )
        else:
            return format_html(
                '<div style="background: #fef2f2; padding: 10px; border-radius: 5px;">'
                '<h4 style="margin: 0 0 10px 0; color: #dc2626;">❌ No Zoom Integration</h4>'
                '<p>This webinar does not have an associated Zoom meeting.</p>'
                '<p><em>Zoom meetings are created automatically when webinars are saved with "scheduled" status.</em></p>'
                '</div>'
            )
    
    zoom_info_display.short_description = 'Zoom Integration Details'
    
    def sync_zoom_meetings(self, request, queryset):
        """Admin action to sync Zoom meetings"""
        success_count = 0
        error_count = 0
        
        for webinar in queryset:
            try:
                if webinar.status == 'scheduled':
                    webinar._handle_zoom_integration(is_new=False, old_status='scheduled')
                    success_count += 1
                else:
                    error_count += 1
            except Exception as e:
                error_count += 1
        
        if success_count > 0:
            self.message_user(request, f"Successfully synced {success_count} webinar(s) with Zoom.", level='SUCCESS')
        if error_count > 0:
            self.message_user(request, f"Failed to sync {error_count} webinar(s). Check logs for details.", level='WARNING')
    
    sync_zoom_meetings.short_description = "Sync selected webinars with Zoom"
    
    def update_webinar_status(self, request, queryset):
        """Admin action to update webinar status based on time"""
        updated_count = 0
        
        for webinar in queryset:
            old_status = webinar.status
            webinar.update_status_based_on_time()
            if old_status != webinar.status:
                webinar.save(update_fields=['status', 'updated_at'])
                updated_count += 1
        
        self.message_user(request, f"Updated status for {updated_count} webinar(s).", level='SUCCESS')
    
    update_webinar_status.short_description = "Update webinar status based on time"
    
    def save_model(self, request, obj, form, change):
        super().save_model(request, obj, form, change)
        
        try:
            from .models import WebinarAnalytics
            WebinarAnalytics.objects.get_or_create(webinar=obj)
        except:
            pass


@admin.register(WebinarPlatformPrice)
class WebinarPlatformPriceAdmin(admin.ModelAdmin):
    """Admin for platform-specific pricing"""
    list_display = [
        'webinar', 'platform', 'get_live_price',
        'get_recorded_price', 'discount_percentage',
        'is_active', 'updated_at'
    ]
    
    list_filter = ['platform', 'is_active', 'discount_percentage']
    search_fields = ['webinar__title', 'platform__name']
    list_editable = ['is_active']
    
    readonly_fields = ['created_at', 'updated_at']
    
    fieldsets = (
        ('Basic', {
            'fields': ('webinar', 'platform', 'is_active')
        }),
        ('Platform Pricing', {
            'fields': ('pricing_data', 'discount_percentage'),
            'description': 'Override default pricing for this platform'
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )
    
    def get_live_price(self, obj):
        price = obj.pricing_data.get('live_single_price')
        return f"${price}" if price else "-"
    get_live_price.short_description = 'Live Price'
    
    def get_recorded_price(self, obj):
        price = obj.pricing_data.get('recorded_single_price')
        return f"${price}" if price else "-"
    get_recorded_price.short_description = 'Recorded Price'


@admin.register(WebinarResource)
class WebinarResourceAdmin(admin.ModelAdmin):
    """Webinar Resource admin"""
    
    list_display = ('title', 'webinar', 'resource_type', 'is_public', 'is_downloadable', 'uploaded_at')
    list_filter = ('resource_type', 'is_public', 'is_downloadable', 'uploaded_at')
    search_fields = ('title', 'description', 'webinar__title', 'webinar__webinar_id')
    raw_id_fields = ('webinar',)


@admin.register(WebinarSession)
class WebinarSessionAdmin(admin.ModelAdmin):
    """Webinar Session admin"""
    
    list_display = ('webinar', 'session_number', 'title', 'scheduled_date', 'duration', 'is_completed')
    list_filter = ('is_completed', 'scheduled_date')
    search_fields = ('title', 'webinar__title', 'webinar__webinar_id')
    raw_id_fields = ('webinar',)
    ordering = ['webinar', 'session_number']


@admin.register(WebinarReview)
class WebinarReviewAdmin(admin.ModelAdmin):
    """Webinar Review admin"""
    
    list_display = (
        'webinar', 'user', 'rating', 'would_recommend', 
        'is_verified_purchase', 'created_at'
    )
    list_filter = (
        'rating', 'would_recommend', 'is_verified_purchase', 
        'created_at', 'webinar__category'
    )
    search_fields = ('webinar__title', 'webinar__webinar_id', 'user__first_name', 'user__last_name', 'review_text')
    raw_id_fields = ('webinar', 'user')
    readonly_fields = ('created_at', 'updated_at')
    
    fieldsets = (
        ('Review Information', {
            'fields': ('webinar', 'user', 'rating', 'review_text')
        }),
        ('Detailed Ratings', {
            'fields': ('content_quality', 'instructor_performance', 'technical_quality')
        }),
        ('Additional Info', {
            'fields': ('would_recommend', 'is_verified_purchase')
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )


@admin.register(WebinarAnalytics)
class WebinarAnalyticsAdmin(admin.ModelAdmin):
    """Webinar Analytics admin"""
    
    list_display = (
        'webinar', 'total_enrollments', 'total_attendees', 
        'completion_rate', 'average_rating', 'total_revenue'
    )
    list_filter = ('last_updated', 'webinar__category', 'webinar__status')
    search_fields = ('webinar__title', 'webinar__webinar_id')
    raw_id_fields = ('webinar',)
    readonly_fields = ('last_updated',)
    
    fieldsets = (
        ('Webinar', {
            'fields': ('webinar',)
        }),
        ('Enrollment Metrics', {
            'fields': ('total_enrollments', 'total_attendees', 'peak_concurrent_attendees')
        }),
        ('Engagement Metrics', {
            'fields': ('average_attendance_duration', 'total_questions_asked', 'total_chat_messages')
        }),
        ('Quality Metrics', {
            'fields': ('average_rating', 'total_reviews')
        }),
        ('Financial Metrics', {
            'fields': ('total_revenue',)
        }),
        ('Completion Metrics', {
            'fields': ('completion_rate',)
        }),
        ('Timestamps', {
            'fields': ('last_updated',)
        }),
    )
    
    def has_add_permission(self, request):
        return False
    
    actions = ['update_analytics']
    
    def update_analytics(self, request, queryset):
        for analytics in queryset:
            analytics.update_metrics()
        self.message_user(request, f"Updated analytics for {queryset.count()} webinars.")
    update_analytics.short_description = "Update selected analytics"
