from django.contrib import admin
from .models import OAuthProvider, SocialAccount, OAuthState, LoginAttempt


@admin.register(OAuthProvider)
class OAuthProviderAdmin(admin.ModelAdmin):
    list_display = ['display_name', 'name', 'is_active', 'created_at']
    list_filter = ['is_active', 'name', 'created_at']
    search_fields = ['name', 'display_name']
    readonly_fields = ['created_at', 'updated_at']
    
    fieldsets = (
        ('Basic Information', {
            'fields': ('name', 'display_name', 'is_active')
        }),
        ('OAuth Configuration', {
            'fields': ('client_id', 'client_secret', 'authorization_url', 'token_url', 'user_info_url', 'scope')
        }),
        ('UI Configuration', {
            'fields': ('button_color', 'icon_class')
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )
    
    def get_readonly_fields(self, request, obj=None):
        if obj:  # editing an existing object
            return self.readonly_fields + ['name']
        return self.readonly_fields


@admin.register(SocialAccount)
class SocialAccountAdmin(admin.ModelAdmin):
    list_display = ['user', 'provider', 'email', 'is_primary', 'last_login', 'created_at']
    list_filter = ['provider', 'is_primary', 'created_at', 'last_login']
    search_fields = ['user__email', 'user__first_name', 'user__last_name', 'email']
    readonly_fields = ['provider_user_id', 'created_at', 'updated_at', 'last_login']
    
    fieldsets = (
        ('Account Information', {
            'fields': ('user', 'provider', 'provider_user_id', 'email', 'is_primary')
        }),
        ('Profile Data', {
            'fields': ('first_name', 'last_name', 'avatar_url', 'profile_url')
        }),
        ('Token Information', {
            'fields': ('token_expires_at',),
            'classes': ('collapse',)
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at', 'last_login'),
            'classes': ('collapse',)
        }),
    )
    
    def get_readonly_fields(self, request, obj=None):
        readonly = list(self.readonly_fields)
        if obj:  # editing an existing object
            readonly.extend(['user', 'provider'])
        return readonly


@admin.register(OAuthState)
class OAuthStateAdmin(admin.ModelAdmin):
    list_display = ['provider', 'user', 'is_used', 'is_expired', 'created_at']
    list_filter = ['provider', 'is_used', 'created_at']
    search_fields = ['state', 'user__email']
    readonly_fields = ['state', 'created_at', 'expires_at']
    
    def is_expired(self, obj):
        return obj.is_expired()
    is_expired.boolean = True
    is_expired.short_description = 'Expired'


@admin.register(LoginAttempt)
class LoginAttemptAdmin(admin.ModelAdmin):
    list_display = ['email', 'attempt_type', 'status', 'provider', 'ip_address', 'created_at']
    list_filter = ['attempt_type', 'status', 'provider', 'created_at']
    search_fields = ['email', 'ip_address']
    readonly_fields = ['created_at']
    
    def has_add_permission(self, request):
        return False  # Login attempts are created automatically
    
    def has_change_permission(self, request, obj=None):
        return False  # Login attempts should not be modified
