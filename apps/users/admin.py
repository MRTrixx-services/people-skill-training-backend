from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from django.contrib.auth.forms import UserCreationForm, UserChangeForm
from django import forms
from .models import User, UserProfile
import pytz
from django.utils import timezone

class UserProfileInline(admin.StackedInline):
    """Inline admin for UserProfile"""
    model = UserProfile
    can_delete = False
    verbose_name_plural = 'Profile'
    fields = [
        'bio', 'location', 'timezone', 'website',
        'linkedin', 'twitter', 'github',
        'show_email_publicly', 'show_phone_publicly',
        'allow_direct_messages'
    ]


class CustomUserCreationForm(UserCreationForm):
    """Custom form for creating users in admin"""
    
    class Meta:
        model = User
        fields = ('email', 'first_name', 'last_name', 'role', 'platform')
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Add helpful text
        self.fields['email'].help_text = 'Email address (used for login)'
        self.fields['platform'].help_text = 'Leave empty for admin/instructor. Required for attendees.'
        self.fields['platform'].required = False


class CustomUserChangeForm(UserChangeForm):
    """Custom form for editing users in admin"""
    
    class Meta:
        model = User
        fields = '__all__'


@admin.register(User)
class UserAdmin(BaseUserAdmin):
    """Custom User Admin"""
    
    form = CustomUserChangeForm
    add_form = CustomUserCreationForm
    inlines = (UserProfileInline,)
  
    # List display
    list_display = [
        'email', 'first_name', 'last_name', 'role', 
        'platform_display', 'is_verified', 'is_active', 
        'is_staff', 'created_at_ist', 'updated_at_ist', 'last_login_ist', 'email_verified_at_ist'
    ]
    
    # Filters
    list_filter = [
        'role', 'is_active', 'is_verified', 'is_staff', 
        'is_superuser', 'platform', 'created_at'
    ]
    
    # Search
    search_fields = ['email', 'first_name', 'last_name', 'username_key', 'phone']
    
    # Ordering
    ordering = ['-created_at']
    
    # Fieldsets for editing existing users
    fieldsets = (
        ('Authentication', {
            'fields': ('email', 'username_key', 'password'),
            'description': 'Login with EMAIL (not username_key). username_key is auto-generated.'
        }),
        ('Personal Information', {
            'fields': ('first_name', 'last_name', 'avatar', 'phone')
        }),
        ('Platform & Role', {
            'fields': ('platform', 'role'),
            'description': 'Platform should be NULL for admins/instructors (shared users). Required for attendees.'
        }),
        ('Permissions', {
            'fields': ('is_active', 'is_verified', 'is_staff', 'is_superuser', 'groups', 'user_permissions'),
            'classes': ('collapse',)
        }),
        ('Important Dates', {
        'fields': (
            'last_login_ist',
            'email_verified_at_ist',
            'created_at_ist',
            'updated_at_ist'
        ),
        'classes': ('collapse',)
    }),
    )
    
    # Fieldsets for creating new users
    add_fieldsets = (
        ('Create New User', {
            'classes': ('wide',),
            'fields': (
                'email', 'first_name', 'last_name', 'role', 
                'platform', 'password1', 'password2',
                'is_staff', 'is_superuser'
            ),
            'description': '''
                <strong>Important:</strong><br>
                - Use EMAIL to login to admin (not username_key)<br>
                - Leave platform EMPTY for admins/instructors<br>
                - Select platform for attendees<br>
                - username_key will be auto-generated on save
            '''
        }),
    )
    
    # Read-only fields
    # readonly_fields = ['username_key', 'created_at', 'updated_at', 'last_login', 'email_verified_at', 'created_at_ist', 'updated_at_ist', 'last_login_ist', 'email_verified_at_ist']
    readonly_fields = [
        'username_key',
        'created_at_ist',
        'updated_at_ist',
        'last_login_ist',
        'email_verified_at_ist'
    ]
    def created_at_ist(self, obj):
        ist = pytz.timezone("Asia/Kolkata")
        return timezone.localtime(obj.created_at, ist).strftime("%Y-%m-%d %H:%M:%S IST")
    

    created_at_ist.short_description = "Created At (IST)"
    def updated_at_ist(self, obj):
        ist = pytz.timezone("Asia/Kolkata")
        return timezone.localtime(obj.updated_at, ist).strftime("%Y-%m-%d %H:%M:%S IST")
    updated_at_ist.short_description = "Updated At (IST)"

    def last_login_ist(self, obj):
        if obj.last_login:
            ist = pytz.timezone("Asia/Kolkata")
            return timezone.localtime(obj.last_login, ist).strftime("%Y-%m-%d %H:%M:%S IST")

        return "-"
    last_login_ist.short_description = "Last Login (IST)"

    def email_verified_at_ist(self, obj):
        if obj.email_verified_at:
            ist = pytz.timezone("Asia/Kolkata")
            return timezone.localtime(obj.email_verified_at, ist).strftime("%Y-%m-%d %H:%M:%S IST")
        return "-"
    email_verified_at_ist.short_description = "Email Verified At (IST)"
    # Custom display methods
    def platform_display(self, obj):
        """Display platform or 'Shared' for admins/instructors"""
        if obj.platform:
            return f"🏢 {obj.platform.name}"
        return "🌐 Shared (All Platforms)" if obj.is_shared_user() else "⚠️ No Platform"
    platform_display.short_description = 'Platform'
    platform_display.admin_order_field = 'platform__name'
    
    def get_queryset(self, request):
        """Optimize queryset with select_related"""
        qs = super().get_queryset(request)
        return qs.select_related('platform', 'profile')
    
    def save_model(self, request, obj, form, change):
        """Custom save logic"""
        # If this is a new user and password is set
        if not change and 'password1' in form.cleaned_data:
            obj.set_password(form.cleaned_data['password1'])
        
        super().save_model(request, obj, form, change)
        
        # Show success message with login info
        if not change:
            from django.contrib import messages
            messages.success(
                request, 
                f'User created successfully! Login to admin using EMAIL: {obj.email}'
            )


@admin.register(UserProfile)
class UserProfileAdmin(admin.ModelAdmin):
    """User Profile Admin"""
    
    list_display = ['user', 'user_role', 'location', 'timezone', 'created_at']
    list_filter = ['timezone', 'show_email_publicly', 'show_phone_publicly', 'created_at']
    search_fields = [
        'user__first_name', 'user__last_name', 'user__email', 
        'location', 'bio'
    ]
    readonly_fields = ['created_at', 'updated_at']
    
    fieldsets = (
        ('User', {
            'fields': ('user',)
        }),
        ('Personal Information', {
            'fields': ('bio', 'location', 'timezone')
        }),
        ('Social Links', {
            'fields': ('website', 'linkedin', 'twitter', 'github'),
            'classes': ('collapse',)
        }),
        ('Privacy Settings', {
            'fields': (
                'show_email_publicly', 
                'show_phone_publicly', 
                'allow_direct_messages'
            )
        }),
        ('Advanced', {
            'fields': ('preferences', 'notification_settings'),
            'classes': ('collapse',)
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )
    
    def user_role(self, obj):
        """Display user role"""
        return obj.user.role.upper()
    user_role.short_description = 'Role'
    user_role.admin_order_field = 'user__role'
    
    def get_queryset(self, request):
        """Optimize queryset"""
        qs = super().get_queryset(request)
        return qs.select_related('user', 'user__platform')


# Customize admin site
admin.site.site_header = "Webinar Platform Administration"
admin.site.site_title = "Webinar Admin"
admin.site.index_title = "Welcome to Webinar Platform Admin"
