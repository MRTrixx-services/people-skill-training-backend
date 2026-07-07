from django.db import models
from django.core.validators import MinValueValidator, MaxValueValidator
from apps.users.models import User


class SpeakerManager(models.Manager):
    """Custom manager for Speaker model"""
    
    def active_speakers(self):
        """Get only active speakers available for webinars"""
        return self.filter(is_active=True, user__is_active=True, user__role='instructor')
    
    def verified_speakers(self):
        """Get verified speakers"""
        return self.active_speakers().filter(is_verified=True)
    
    def available_speakers(self):
        """Get available speakers"""
        return self.active_speakers()


class Speaker(models.Model):
    """Speaker/Instructor profile - Minimal version for webinar integration"""
   
    user = models.OneToOneField(
        User, 
        on_delete=models.CASCADE, 
        related_name='speaker_profile',
        limit_choices_to={'role': 'instructor'}
    )
    
    # Basic profile information
    title = models.CharField(
        max_length=200, 
        blank=True, 
        help_text="Professional title or designation"
    )
    bio = models.TextField(
        blank=True, 
        help_text="Professional background and expertise"
    )
    company = models.CharField(
        max_length=200, 
        blank=True, 
        help_text="Current organization or company"
    )
    
    # Status fields
    is_verified = models.BooleanField(
        default=False, 
        help_text="Verified speaker status by admin"
    )
    is_active = models.BooleanField(
        default=True, 
        help_text="Available for new webinars"
    )
    
    # Statistics
    total_sessions = models.PositiveIntegerField(
        default=0,
        help_text="Total completed webinar sessions"
    )
    
    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    # Custom manager
    objects = SpeakerManager()
    
    class Meta:
        db_table = 'speakers'
        verbose_name = 'Speaker'
        verbose_name_plural = 'Speakers'
        ordering = ['-total_sessions']
        indexes = [
            models.Index(fields=['is_active', 'is_verified']),
            models.Index(fields=['total_sessions']),
        ]
    
    def __str__(self):
        """String representation of the speaker"""
        return f"{self.full_name} - {self.title}" if self.title else self.full_name
    
    # Properties for accessing user data
    @property
    def full_name(self):
        """Get full name from linked user - required for webinar serializers"""
        if self.user:
            return self.user.full_name
        return f"Speaker {self.id}"
    
    @property
    def email(self):
        """Get email from linked user - required for webinar serializers"""
        return self.user.email if self.user else ''
    
    @property
    def first_name(self):
        """Get first name from linked user"""
        return self.user.first_name if self.user else ''
    
    @property
    def last_name(self):
        """Get last name from linked user"""
        return self.user.last_name if self.user else ''
    
    @property
    def avatar(self):
        """Get avatar from linked user"""
        return self.user.avatar if self.user else None
    
    @property
    def display_name(self):
        """Display name for frontend"""
        if self.title:
            return f"{self.full_name}, {self.title}"
        return self.full_name
    
    # Business logic methods
    def can_create_webinars(self):
        """Check if speaker can create webinars"""
        return (
            self.is_active and 
            self.user and 
            self.user.is_active and 
            self.user.role == 'instructor'
        )
    
    def get_webinar_count(self):
        """Get total webinars created by this speaker"""
        try:
            return self.webinars.count()
        except AttributeError:
            return 0
    
    def get_completed_webinars_count(self):
        """Get count of completed webinars"""
        try:
            return self.webinars.filter(status='completed').count()
        except AttributeError:
            return 0
    
    def get_upcoming_webinars_count(self):
        """Get count of upcoming webinars for this speaker"""
        from django.utils import timezone
        try:
            return self.webinars.filter(
                scheduled_date__gt=timezone.now(),
                status='scheduled'
            ).count()
        except AttributeError:
            return 0
    
    def update_session_stats(self):
        """Update speaker statistics from completed webinars"""
        try:
            completed_count = self.webinars.filter(status='completed').count()
            if self.total_sessions != completed_count:
                Speaker.objects.filter(id=self.id).update(
                    total_sessions=completed_count
                )
                self.total_sessions = completed_count
        except AttributeError:
            pass
    
    def save(self, *args, **kwargs):
        """Override save method for additional processing"""
        # Update session count on save if record exists
        if self.pk:
            self.update_session_stats()
        
        super().save(*args, **kwargs)
    
