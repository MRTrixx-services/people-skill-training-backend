from django.db import models
from django.contrib.auth.tokens import default_token_generator
from django.utils import timezone
from datetime import timedelta
import secrets


class EmailVerificationToken(models.Model):
    """Email verification tokens - Platform-aware through user"""
    
    user = models.ForeignKey(
        'users.User', 
        on_delete=models.CASCADE, 
        related_name='verification_tokens'
    )
    token = models.CharField(max_length=255, unique=True, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField(db_index=True)
    is_used = models.BooleanField(default=False, db_index=True)
    
    # Optional: Track which platform the verification was initiated from
    platform = models.ForeignKey(
        'platforms.Platform',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='verification_tokens',
        help_text="Platform where verification was initiated (optional)"
    )
    
    class Meta:
        db_table = 'email_verification_tokens'
        verbose_name = 'Email Verification Token'
        verbose_name_plural = 'Email Verification Tokens'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['token', 'is_used']),
            models.Index(fields=['user', 'is_used', 'expires_at']),
        ]
    
    def save(self, *args, **kwargs):
        if not self.token:
            self.token = secrets.token_urlsafe(32)
        if not self.expires_at:
            self.expires_at = timezone.now() + timedelta(hours=24)
        
        # Auto-assign platform from user if not set
        if not self.platform_id and self.user and hasattr(self.user, 'platform'):
            self.platform = self.user.platform
        
        super().save(*args, **kwargs)
    
    def is_expired(self):
        """Check if token is expired"""
        return timezone.now() > self.expires_at
    
    def is_valid(self):
        """Check if token is valid (not used and not expired)"""
        return not self.is_used and not self.is_expired()
    
    def mark_as_used(self):
        """Mark token as used"""
        self.is_used = True
        self.save(update_fields=['is_used'])
    
    def __str__(self):
        platform_name = self.platform.name if self.platform else 'System'
        return f"[{platform_name}] Verification token for {self.user.email}"


class PasswordResetToken(models.Model):
    """Password reset tokens - Platform-aware through user"""
    
    user = models.ForeignKey(
        'users.User', 
        on_delete=models.CASCADE, 
        related_name='reset_tokens'
    )
    token = models.CharField(max_length=255, unique=True, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField(db_index=True)
    is_used = models.BooleanField(default=False, db_index=True)
    
    # Optional: Track which platform the reset was initiated from
    platform = models.ForeignKey(
        'platforms.Platform',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='reset_tokens',
        help_text="Platform where reset was initiated (optional)"
    )
    
    # Track IP for security
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    user_agent = models.TextField(blank=True)
    
    class Meta:
        db_table = 'password_reset_tokens'
        verbose_name = 'Password Reset Token'
        verbose_name_plural = 'Password Reset Tokens'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['token', 'is_used']),
            models.Index(fields=['user', 'is_used', 'expires_at']),
        ]
    
    def save(self, *args, **kwargs):
        if not self.token:
            self.token = secrets.token_urlsafe(32)
        if not self.expires_at:
            self.expires_at = timezone.now() + timedelta(hours=1)  # 1 hour expiry
        
        # Auto-assign platform from user if not set
        if not self.platform_id and self.user and hasattr(self.user, 'platform'):
            self.platform = self.user.platform
        
        super().save(*args, **kwargs)
    
    def is_expired(self):
        """Check if token is expired"""
        return timezone.now() > self.expires_at
    
    def is_valid(self):
        """Check if token is valid (not used and not expired)"""
        return not self.is_used and not self.is_expired()
    
    def mark_as_used(self):
        """Mark token as used"""
        self.is_used = True
        self.save(update_fields=['is_used'])
    
    def __str__(self):
        platform_name = self.platform.name if self.platform else 'System'
        return f"[{platform_name}] Reset token for {self.user.email}"
    
    @classmethod
    def invalidate_all_for_user(cls, user):
        """Invalidate all tokens for a user (e.g., after successful password reset)"""
        return cls.objects.filter(user=user, is_used=False).update(is_used=True)
