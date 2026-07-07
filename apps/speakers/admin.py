from django.contrib import admin
from django.utils.html import format_html
from django.urls import reverse
from django.utils.safestring import mark_safe
from django.db.models import Count, Avg
from django.contrib import messages
from django.utils import timezone

from .models import Speaker


@admin.register(Speaker)
class SpeakerAdmin(admin.ModelAdmin):
    """Enhanced Speaker admin - Only model fields"""
    
    list_display = [
        'speaker_name', 'title', 'company', 'verification_status', 
        'is_active', 'total_sessions', 'created_at'
    ]
    
    list_filter = [
        'is_verified', 'is_active', 'user__is_active', 
        'created_at', 'updated_at'
    ]
    
    search_fields = [
        'user__first_name', 'user__last_name', 'user__email',
        'title', 'bio', 'company'
    ]
    
    readonly_fields = [
        'total_sessions', 'created_at', 'updated_at'
    ]
    
    fieldsets = (
        ('User Information', {
            'fields': ('user',)
        }),
        ('Basic Profile', {
            'fields': ('title', 'bio', 'company')
        }),
        ('Status', {
            'fields': ('is_verified', 'is_active')
        }),
        ('Statistics', {
            'fields': ('total_sessions',),
            'classes': ('collapse',)
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )
    
    actions = [
        'mark_as_verified', 'mark_as_unverified', 
        'mark_as_active', 'mark_as_inactive', 'export_speaker_data'
    ]
    
    def speaker_name(self, obj):
        """Display speaker name with link to user"""
        user_url = reverse('admin:users_user_change', args=[obj.user.id])
        return format_html(
            '<a href="{}" title="View User Details">{}</a>',
            user_url,
            obj.user.full_name
        )
    speaker_name.short_description = 'Name'
    speaker_name.admin_order_field = 'user__first_name'
    
    def verification_status(self, obj):
        """Display verification status with color coding"""
        if obj.is_verified:
            return format_html(
                '<span style="color: green; font-weight: bold;">✓ Verified</span>'
            )
        else:
            return format_html(
                '<span style="color: red;">❌ Not Verified</span>'
            )
    verification_status.short_description = 'Verification'
    
    def get_queryset(self, request):
        """Optimize queryset with related data"""
        return super().get_queryset(request).select_related('user')
    
    # Admin Actions
    def mark_as_verified(self, request, queryset):
        """Mark selected speakers as verified"""
        updated = 0
        for speaker in queryset:
            speaker.is_verified = True
            speaker.user.is_verified = True
            speaker.user.save()
            speaker.save()
            updated += 1
        
        self.message_user(
            request, 
            f'{updated} speaker(s) marked as verified.',
            messages.SUCCESS
        )
    mark_as_verified.short_description = "Mark selected speakers as verified"
    
    def mark_as_unverified(self, request, queryset):
        """Mark selected speakers as unverified"""
        updated = queryset.update(is_verified=False)
        # Also update user verification status
        for speaker in queryset:
            speaker.user.is_verified = False
            speaker.user.save()
        
        self.message_user(
            request,
            f'{updated} speaker(s) marked as unverified.',
            messages.SUCCESS
        )
    mark_as_unverified.short_description = "Mark selected speakers as unverified"
    
    def mark_as_active(self, request, queryset):
        """Mark selected speakers as active"""
        updated = queryset.update(is_active=True)
        self.message_user(
            request,
            f'{updated} speaker(s) marked as active.',
            messages.SUCCESS
        )
    mark_as_active.short_description = "Mark selected speakers as active"
    
    def mark_as_inactive(self, request, queryset):
        """Mark selected speakers as inactive"""
        updated = queryset.update(is_active=False)
        self.message_user(
            request,
            f'{updated} speaker(s) marked as inactive.',
            messages.SUCCESS
        )
    mark_as_inactive.short_description = "Mark selected speakers as inactive"
    
    def export_speaker_data(self, request, queryset):
        """Export speaker data (simplified)"""
        import csv
        from django.http import HttpResponse
        
        response = HttpResponse(content_type='text/csv')
        response['Content-Disposition'] = 'attachment; filename="speakers_export.csv"'
        
        writer = csv.writer(response)
        writer.writerow([
            'Name', 'Email', 'Title', 'Bio', 'Company',
            'Total Sessions', 'Is Verified', 'Is Active', 'Created At'
        ])
        
        for speaker in queryset:
            writer.writerow([
                speaker.user.full_name,
                speaker.user.email,
                speaker.title,
                speaker.bio[:100] + '...' if len(speaker.bio) > 100 else speaker.bio,
                speaker.company,
                speaker.total_sessions,
                'Yes' if speaker.is_verified else 'No',
                'Yes' if speaker.is_active else 'No',
                speaker.created_at.strftime('%Y-%m-%d')
            ])
        
        return response
    export_speaker_data.short_description = "Export selected speakers to CSV"


# Admin site customization
admin.site.site_header = "Webinar Platform Administration"
admin.site.site_title = "Speaker Management"
admin.site.index_title = "Welcome to Speaker Management Portal"
