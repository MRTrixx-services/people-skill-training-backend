from django.db import models
from django.core.validators import MinValueValidator, MaxValueValidator
from django.contrib.postgres.fields import ArrayField
from apps.users.models import User


class AttendeeProfile(models.Model):
    """Attendee-specific profile data - Platform-specific"""
    
    SKILL_LEVEL_CHOICES = [
        ('beginner', 'Beginner'),
        ('intermediate', 'Intermediate'),
        ('advanced', 'Advanced'),
        ('expert', 'Expert'),
    ]
    
    LANGUAGE_CHOICES = [
        ('en', 'English'),
        ('es', 'Spanish'),
        ('fr', 'French'),
        ('de', 'German'),
        ('zh', 'Chinese'),
        ('ja', 'Japanese'),
    ]
    
    user = models.OneToOneField(
        User, 
        on_delete=models.CASCADE, 
        related_name='attendee_profile',
        limit_choices_to={'role': 'attendee'}
    )
    
    # ✅ PLATFORM ASSIGNMENT (automatically inherited from user)
    platform = models.ForeignKey(
        'platforms.Platform',
        on_delete=models.CASCADE,
        related_name='attendee_profiles',
        help_text="Platform this attendee belongs to (from user.platform)"
    )
    
    # Learning preferences
    interests = ArrayField(
        models.CharField(max_length=100),
        size=20,
        default=list,
        blank=True,
        help_text="Learning interests like Data Science, Web Development, etc."
    )
    learning_goals = models.TextField(
        blank=True,
        help_text="What the attendee wants to achieve through learning"
    )
    skill_level = models.CharField(
        max_length=20,
        choices=SKILL_LEVEL_CHOICES,
        default='beginner'
    )
    company = models.CharField(
        max_length=200, 
        blank=True, 
        help_text="Current organization or company"
    )
    
    # Learning statistics
    total_enrollments = models.IntegerField(default=0)
    completed_webinars = models.IntegerField(default=0)
    total_hours_learned = models.IntegerField(default=0)
    certificates_earned = models.IntegerField(default=0)
    average_rating_given = models.DecimalField(
        max_digits=3,
        decimal_places=2,
        default=0.0,
        validators=[MinValueValidator(0.0), MaxValueValidator(5.0)]
    )
    
    # Contact preferences
    show_email_publicly = models.BooleanField(default=False)
    show_phone_publicly = models.BooleanField(default=False)
    allow_direct_messages = models.BooleanField(default=True)
    allow_newsletters = models.BooleanField(default=True)
    
    # App preferences
    language = models.CharField(
        max_length=5, 
        choices=LANGUAGE_CHOICES, 
        default='en'
    )
    timezone = models.CharField(max_length=50, default='America/New_York')
    email_frequency = models.CharField(
        max_length=20,
        choices=[
            ('immediate', 'Immediate'),
            ('daily', 'Daily Digest'),
            ('weekly', 'Weekly Summary'),
            ('never', 'Never'),
        ],
        default='immediate'
    )
    auto_join_webinars = models.BooleanField(default=False)
    show_profile_publicly = models.BooleanField(default=True)
    
    # Member information
    member_since = models.DateTimeField(auto_now_add=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        db_table = 'attendee_profiles'
        verbose_name = 'Attendee Profile'
        verbose_name_plural = 'Attendee Profiles'
        indexes = [
            models.Index(fields=['platform', 'skill_level']),
            models.Index(fields=['platform', 'created_at']),
        ]
    
    def save(self, *args, **kwargs):
        # Auto-assign platform from user
        if not self.platform_id and self.user.platform:
            self.platform = self.user.platform
        super().save(*args, **kwargs)
    
    def __str__(self):
        return f"{self.user.full_name} - {self.platform.name if self.platform else 'No Platform'}"
    
    @property
    def completion_rate(self):
        """Calculate completion rate percentage"""
        if self.total_enrollments == 0:
            return 0
        return round((self.completed_webinars / self.total_enrollments) * 100, 2)


class AttendeeNotificationSettings(models.Model):
    """Detailed notification settings for attendees"""
    
    attendee = models.OneToOneField(
        AttendeeProfile, 
        on_delete=models.CASCADE, 
        related_name='notification_settings'
    )
    
    # Email notifications
    email_webinar_reminders = models.BooleanField(default=True)
    email_new_webinar_alerts = models.BooleanField(default=True)
    email_payment_confirmations = models.BooleanField(default=True)
    email_weekly_digest = models.BooleanField(default=False)
    email_promotional = models.BooleanField(default=False)
    
    # SMS notifications
    sms_webinar_reminders = models.BooleanField(default=True)
    sms_payment_alerts = models.BooleanField(default=True)
    sms_security_alerts = models.BooleanField(default=True)
    
    # Push notifications
    push_webinar_starting = models.BooleanField(default=True)
    push_new_messages = models.BooleanField(default=True)
    push_system_updates = models.BooleanField(default=False)
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        db_table = 'attendee_notification_settings'
        verbose_name = 'Attendee Notification Settings'
        verbose_name_plural = 'Attendee Notification Settings'
    
    def __str__(self):
        return f"{self.attendee.user.full_name} - Notification Settings"


class AttendeeSecuritySettings(models.Model):
    """Security settings for attendees"""
    
    attendee = models.OneToOneField(
        AttendeeProfile, 
        on_delete=models.CASCADE, 
        related_name='security_settings'
    )
    
    # Two-factor authentication
    two_factor_enabled = models.BooleanField(default=False)
    two_factor_secret = models.CharField(max_length=32, blank=True)
    backup_codes = ArrayField(
        models.CharField(max_length=10),
        size=10,
        default=list,
        blank=True
    )
    
    # Security preferences
    login_alerts_enabled = models.BooleanField(default=True)
    password_changed_at = models.DateTimeField(auto_now_add=True)
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        db_table = 'attendee_security_settings'
        verbose_name = 'Attendee Security Settings'
        verbose_name_plural = 'Attendee Security Settings'
    
    def __str__(self):
        return f"{self.attendee.user.full_name} - Security Settings"


class AttendeeActivity(models.Model):
    """Track attendee learning activity"""
    
    ACTIVITY_TYPES = [
        ('enrollment', 'Enrolled in Webinar'),
        ('completion', 'Completed Webinar'),
        ('certificate_earned', 'Certificate Earned'),
        ('profile_update', 'Profile Updated'),
        ('rating_given', 'Rating Given'),
        ('comment_posted', 'Comment Posted'),
        ('login', 'Login'),
        ('logout', 'Logout'),
    ]
    
    attendee = models.ForeignKey(
        AttendeeProfile, 
        on_delete=models.CASCADE, 
        related_name='activities'
    )
    activity_type = models.CharField(max_length=30, choices=ACTIVITY_TYPES)
    description = models.TextField(blank=True)
    
    # Related objects (stored as JSON for flexibility)
    metadata = models.JSONField(default=dict, blank=True)
    
    # Activity details
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    user_agent = models.TextField(blank=True)
    
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        db_table = 'attendee_activities'
        verbose_name = 'Attendee Activity'
        verbose_name_plural = 'Attendee Activities'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['attendee', 'activity_type']),
            models.Index(fields=['attendee', 'created_at']),
        ]
    
    def __str__(self):
        return f"{self.attendee.user.full_name} - {self.get_activity_type_display()}"


class AttendeeLearningPath(models.Model):
    """Learning paths and progress for attendees"""
    
    STATUS_CHOICES = [
        ('not_started', 'Not Started'),
        ('in_progress', 'In Progress'),
        ('completed', 'Completed'),
        ('paused', 'Paused'),
    ]
    
    attendee = models.ForeignKey(
        AttendeeProfile, 
        on_delete=models.CASCADE, 
        related_name='learning_paths'
    )
    
    path_name = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='not_started')
    
    # Progress tracking
    total_webinars = models.IntegerField(default=0)
    completed_webinars = models.IntegerField(default=0)
    progress_percentage = models.IntegerField(
        default=0,
        validators=[MinValueValidator(0), MaxValueValidator(100)]
    )
    
    # Dates
    started_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    target_completion_date = models.DateTimeField(null=True, blank=True)
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        db_table = 'attendee_learning_paths'
        verbose_name = 'Learning Path'
        verbose_name_plural = 'Learning Paths'
        ordering = ['-created_at']
    
    def __str__(self):
        return f"{self.attendee.user.full_name} - {self.path_name}"
    
    def update_progress(self):
        """Update progress percentage based on completed webinars"""
        if self.total_webinars > 0:
            self.progress_percentage = min(
                100, 
                round((self.completed_webinars / self.total_webinars) * 100)
            )
            if self.progress_percentage == 100 and self.status != 'completed':
                from django.utils import timezone
                self.status = 'completed'
                self.completed_at = timezone.now()
        self.save()


# Signal handlers to create related models
from django.db.models.signals import post_save
from django.dispatch import receiver


@receiver(post_save, sender=AttendeeProfile)
def create_attendee_settings(sender, instance, created, **kwargs):
    """Create related settings when attendee profile is created"""
    if created:
        AttendeeNotificationSettings.objects.create(attendee=instance)
        AttendeeSecuritySettings.objects.create(attendee=instance)


@receiver(post_save, sender=AttendeeProfile)
def save_attendee_settings(sender, instance, **kwargs):
    """Save related settings when attendee profile is saved"""
    if hasattr(instance, 'notification_settings'):
        instance.notification_settings.save()
    if hasattr(instance, 'security_settings'):
        instance.security_settings.save()
