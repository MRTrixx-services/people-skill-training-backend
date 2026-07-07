from django.db import models
from django.contrib.auth import get_user_model
from apps.webinars.models import Webinar

User = get_user_model()


class NotificationTemplate(models.Model):
    """Notification templates - Can be platform-specific or global"""
    
    TEMPLATE_TYPES = [
        ('email', 'Email'),
        ('sms', 'SMS'),
        ('push', 'Push Notification'),
        ('in_app', 'In-App Notification'),
    ]
    
    EVENT_TYPES = [
        ('webinar_reminder', 'Webinar Reminder'),
        ('webinar_started', 'Webinar Started'),
        ('webinar_cancelled', 'Webinar Cancelled'),
        ('enrollment_confirmed', 'Enrollment Confirmed'),
        ('payment_successful', 'Payment Successful'),
        ('payment_failed', 'Payment Failed'),
        ('instructor_approved', 'Instructor Approved'),
        ('webinar_feedback', 'Webinar Feedback Request'),
        ('certificate_ready', 'Certificate Ready'),
    ]
    
    name = models.CharField(max_length=100)
    template_type = models.CharField(max_length=20, choices=TEMPLATE_TYPES)
    event_type = models.CharField(max_length=50, choices=EVENT_TYPES)
    subject = models.CharField(max_length=200, blank=True)
    content = models.TextField()
    is_active = models.BooleanField(default=True, db_index=True)
    
    # ✅ PLATFORM SUPPORT - Platform-specific or global templates
    platform = models.ForeignKey(
        'platforms.Platform',
        on_delete=models.CASCADE,
        related_name='notification_templates',
        null=True,
        blank=True,
        help_text="Platform-specific template (leave empty for global template)"
    )
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'notification_templates'
        verbose_name = 'Notification Template'
        verbose_name_plural = 'Notification Templates'
        # Updated unique constraint
        constraints = [
            models.UniqueConstraint(
                fields=['template_type', 'event_type', 'platform'],
                name='unique_template_per_platform'
            ),
            models.UniqueConstraint(
                fields=['template_type', 'event_type'],
                condition=models.Q(platform__isnull=True),
                name='unique_global_template'
            ),
        ]
        indexes = [
            models.Index(fields=['platform', 'event_type', 'is_active']),
        ]

    def __str__(self):
        platform_name = self.platform.name if self.platform else 'Global'
        return f"{self.name} - {self.template_type} ({platform_name})"


class Notification(models.Model):
    """Notifications sent to users - Platform-specific"""
    
    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('sent', 'Sent'),
        ('failed', 'Failed'),
        ('read', 'Read'),
    ]
    
    PRIORITY_CHOICES = [
        ('low', 'Low'),
        ('medium', 'Medium'),
        ('high', 'High'),
        ('urgent', 'Urgent'),
    ]
    
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='notifications')
    template = models.ForeignKey(NotificationTemplate, on_delete=models.CASCADE)
    webinar = models.ForeignKey(Webinar, on_delete=models.CASCADE, null=True, blank=True)
    
    # ✅ PLATFORM SUPPORT (from user.platform)
    platform = models.ForeignKey(
        'platforms.Platform',
        on_delete=models.CASCADE,
        related_name='notifications',
        help_text="Platform where notification was sent (from user.platform)"
    )
    
    title = models.CharField(max_length=200)
    message = models.TextField()
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending', db_index=True)
    priority = models.CharField(max_length=20, choices=PRIORITY_CHOICES, default='medium')
    scheduled_at = models.DateTimeField(null=True, blank=True, db_index=True)
    sent_at = models.DateTimeField(null=True, blank=True)
    read_at = models.DateTimeField(null=True, blank=True)
    metadata = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'notifications'
        verbose_name = 'Notification'
        verbose_name_plural = 'Notifications'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['platform', 'user', 'status']),
            models.Index(fields=['platform', 'scheduled_at']),
            models.Index(fields=['user', 'status', 'created_at']),
            models.Index(fields=['template', 'status']),
        ]
    
    def save(self, *args, **kwargs):
        # Auto-assign platform from user
        if not self.platform_id and self.user and self.user.platform:
            self.platform = self.user.platform
        super().save(*args, **kwargs)

    def __str__(self):
        platform_name = self.platform.name if self.platform else 'No Platform'
        return f"{self.title} - {self.user.email} ({platform_name})"


class EmailLog(models.Model):
    """Email delivery logs"""
    
    notification = models.OneToOneField(Notification, on_delete=models.CASCADE, related_name='email_log')
    to_email = models.EmailField(db_index=True)
    from_email = models.EmailField()
    subject = models.CharField(max_length=200)
    body = models.TextField()
    sent_at = models.DateTimeField(null=True, blank=True, db_index=True)
    delivery_status = models.CharField(max_length=50, blank=True)
    error_message = models.TextField(blank=True)
    opened_at = models.DateTimeField(null=True, blank=True)
    clicked_at = models.DateTimeField(null=True, blank=True)
    
    class Meta:
        db_table = 'email_logs'
        verbose_name = 'Email Log'
        verbose_name_plural = 'Email Logs'
        indexes = [
            models.Index(fields=['to_email', 'sent_at']),
        ]

    def __str__(self):
        return f"Email to {self.to_email} - {self.subject}"


class SMSLog(models.Model):
    """SMS delivery logs"""
    
    notification = models.OneToOneField(Notification, on_delete=models.CASCADE, related_name='sms_log')
    to_phone = models.CharField(max_length=20, db_index=True)
    message = models.TextField()
    sent_at = models.DateTimeField(null=True, blank=True, db_index=True)
    delivery_status = models.CharField(max_length=50, blank=True)
    error_message = models.TextField(blank=True)
    provider_message_id = models.CharField(max_length=100, blank=True)
    
    class Meta:
        db_table = 'sms_logs'
        verbose_name = 'SMS Log'
        verbose_name_plural = 'SMS Logs'
        indexes = [
            models.Index(fields=['to_phone', 'sent_at']),
        ]

    def __str__(self):
        return f"SMS to {self.to_phone}"


class NotificationPreference(models.Model):
    """User notification preferences"""
    
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='notification_preferences')
    email_notifications = models.BooleanField(default=True)
    sms_notifications = models.BooleanField(default=False)
    push_notifications = models.BooleanField(default=True)
    webinar_reminders = models.BooleanField(default=True)
    marketing_emails = models.BooleanField(default=False)
    payment_notifications = models.BooleanField(default=True)
    instructor_updates = models.BooleanField(default=True)
    reminder_time = models.IntegerField(default=60)  # minutes before webinar
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        db_table = 'notification_preferences'
        verbose_name = 'Notification Preference'
        verbose_name_plural = 'Notification Preferences'

    def __str__(self):
        return f"Preferences for {self.user.email}"
