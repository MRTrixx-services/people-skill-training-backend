from django.db import models
from django.utils import timezone
from apps.users.models import User


class OAuthProvider(models.Model):
    """OAuth provider configuration"""
    
    PROVIDER_CHOICES = [
        ('google', 'Google'),
        ('facebook', 'Facebook'),
        ('linkedin', 'LinkedIn'),
        ('github', 'GitHub'),
        ('microsoft', 'Microsoft'),
        ('zoom', 'Zoom'),
    ]
    
    name = models.CharField(max_length=50, choices=PROVIDER_CHOICES, unique=True)
    display_name = models.CharField(max_length=100)
    client_id = models.CharField(max_length=255)
    client_secret = models.CharField(max_length=255)
    
    # OAuth URLs
    authorization_url = models.URLField()
    token_url = models.URLField()
    user_info_url = models.URLField()
    
    # Configuration
    scope = models.TextField(help_text="Space-separated scopes")
    is_active = models.BooleanField(default=True)
    
    # UI Configuration
    button_color = models.CharField(max_length=7, default='#4285f4')  # Hex color
    icon_class = models.CharField(max_length=50, blank=True)
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        db_table = 'oauth_providers'
        verbose_name = 'OAuth Provider'
        verbose_name_plural = 'OAuth Providers'
    
    def __str__(self):
        return self.display_name


class SocialAccount(models.Model):
    """User's social account connections"""
    
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='social_accounts')
    provider = models.ForeignKey(OAuthProvider, on_delete=models.CASCADE)
    
    # Provider-specific user info
    provider_user_id = models.CharField(max_length=255)
    email = models.EmailField(blank=True)
    first_name = models.CharField(max_length=150, blank=True)
    last_name = models.CharField(max_length=150, blank=True)
    avatar_url = models.URLField(blank=True)
    profile_url = models.URLField(blank=True)
    
    # OAuth tokens
    access_token = models.TextField()
    refresh_token = models.TextField(blank=True)
    token_expires_at = models.DateTimeField(null=True, blank=True)
    
    # Additional provider data
    extra_data = models.JSONField(default=dict, blank=True)
    
    # Metadata
    is_primary = models.BooleanField(default=False)  # Primary login method
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    last_login = models.DateTimeField(null=True, blank=True)
    
    class Meta:
        db_table = 'social_accounts'
        verbose_name = 'Social Account'
        verbose_name_plural = 'Social Accounts'
        unique_together = ['provider', 'provider_user_id']
    
    def __str__(self):
        return f"{self.user.email} - {self.provider.display_name}"
    
    def is_token_expired(self):
        if not self.token_expires_at:
            return False
        return timezone.now() >= self.token_expires_at


class OAuthState(models.Model):
    """OAuth state tracking for security"""
    
    state = models.CharField(max_length=255, unique=True)
    provider = models.ForeignKey(OAuthProvider, on_delete=models.CASCADE)
    redirect_uri = models.URLField()
    
    # Optional user context
    user = models.ForeignKey(User, on_delete=models.CASCADE, null=True, blank=True)
    
    # Additional context data
    context_data = models.JSONField(default=dict, blank=True)
    
    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField()
    is_used = models.BooleanField(default=False)
    
    class Meta:
        db_table = 'oauth_states'
        verbose_name = 'OAuth State'
        verbose_name_plural = 'OAuth States'
    
    def __str__(self):
        return f"OAuth State - {self.provider.display_name}"
    
    def is_expired(self):
        return timezone.now() >= self.expires_at
    
    def is_valid(self):
        return not self.is_used and not self.is_expired()


class LoginAttempt(models.Model):
    """Track login attempts for security"""
    
    ATTEMPT_TYPES = [
        ('password', 'Password Login'),
        ('oauth', 'OAuth Login'),
        ('token', 'Token Refresh'),
    ]
    
    STATUS_CHOICES = [
        ('success', 'Success'),
        ('failed', 'Failed'),
        ('blocked', 'Blocked'),
    ]
    
    email = models.EmailField()
    attempt_type = models.CharField(max_length=20, choices=ATTEMPT_TYPES)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES)
    
    # OAuth specific
    provider = models.ForeignKey(OAuthProvider, on_delete=models.CASCADE, null=True, blank=True)
    
    # Request details
    ip_address = models.GenericIPAddressField()
    user_agent = models.TextField(blank=True)
    
    # Failure details
    failure_reason = models.CharField(max_length=255, blank=True)
    
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        db_table = 'login_attempts'
        verbose_name = 'Login Attempt'
        verbose_name_plural = 'Login Attempts'
        ordering = ['-created_at']
    
    def __str__(self):
        return f"{self.email} - {self.get_status_display()} ({self.created_at})"
