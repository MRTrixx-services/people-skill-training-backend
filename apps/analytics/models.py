from django.db import models
from django.contrib.auth import get_user_model
from apps.webinars.models import Webinar

User = get_user_model()


class WebinarAnalytics(models.Model):
    webinar = models.OneToOneField(
        Webinar,
        on_delete=models.CASCADE,
        related_name='analytics_data'  # 👈 renamed to avoid clash
    )
    total_enrollments = models.IntegerField(default=0)
    total_attendees = models.IntegerField(default=0)
    peak_attendance = models.IntegerField(default=0)
    average_attendance_duration = models.IntegerField(default=0)  # in minutes
    total_watch_time = models.IntegerField(default=0)  # in minutes
    average_rating = models.DecimalField(max_digits=3, decimal_places=2, default=0.0)
    total_reviews = models.IntegerField(default=0)
    total_revenue = models.DecimalField(max_digits=10, decimal_places=2, default=0.00)
    completion_rate = models.DecimalField(max_digits=5, decimal_places=2, default=0.0)
    engagement_score = models.DecimalField(max_digits=5, decimal_places=2, default=0.0)
    last_updated = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name_plural = "Webinar Analytics"

    def __str__(self):
        return f"Analytics for {self.webinar.title}"


class PlatformMetrics(models.Model):
    date = models.DateField(unique=True)
    total_users = models.IntegerField(default=0)
    new_users = models.IntegerField(default=0)
    active_users = models.IntegerField(default=0)
    total_instructors = models.IntegerField(default=0)
    active_instructors = models.IntegerField(default=0)
    total_webinars = models.IntegerField(default=0)
    live_webinars = models.IntegerField(default=0)
    completed_webinars = models.IntegerField(default=0)
    total_enrollments = models.IntegerField(default=0)
    new_enrollments = models.IntegerField(default=0)
    daily_revenue = models.DecimalField(max_digits=10, decimal_places=2, default=0.00)
    total_revenue = models.DecimalField(max_digits=10, decimal_places=2, default=0.00)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-date']
        indexes = [
            models.Index(fields=['date']),
        ]

    def __str__(self):
        return f"Platform Metrics - {self.date}"


class UserActivity(models.Model):
    ACTIVITY_CHOICES = [
        ('login', 'Login'),
        ('logout', 'Logout'),
        ('webinar_view', 'Webinar View'),
        ('webinar_join', 'Webinar Join'),
        ('webinar_leave', 'Webinar Leave'),
        ('enrollment', 'Enrollment'),
        ('payment', 'Payment'),
        ('profile_update', 'Profile Update'),
    ]

    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name='analytics_activities'   # 👈 renamed to avoid clash with users.UserActivity
    )
    activity_type = models.CharField(max_length=50, choices=ACTIVITY_CHOICES)
    webinar = models.ForeignKey(
        Webinar,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="analytics_user_activities"  # 👈 explicit related_name
    )
    metadata = models.JSONField(default=dict, blank=True)
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    user_agent = models.TextField(blank=True)
    timestamp = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-timestamp']
        indexes = [
            models.Index(fields=['user', 'activity_type']),
            models.Index(fields=['timestamp']),
            models.Index(fields=['webinar', 'activity_type']),
        ]

    def __str__(self):
        return f"{self.user.email} - {self.activity_type} - {self.timestamp}"


class RevenueAnalytics(models.Model):
    date = models.DateField()
    instructor = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name='analytics_revenue'  # 👈 renamed
    )
    webinar = models.ForeignKey(
        Webinar,
        on_delete=models.CASCADE,
        related_name='analytics_revenue'  # 👈 renamed
    )
    gross_revenue = models.DecimalField(max_digits=10, decimal_places=2, default=0.00)
    platform_fee = models.DecimalField(max_digits=10, decimal_places=2, default=0.00)
    net_revenue = models.DecimalField(max_digits=10, decimal_places=2, default=0.00)
    enrollments_count = models.IntegerField(default=0)
    refunds_count = models.IntegerField(default=0)
    refund_amount = models.DecimalField(max_digits=10, decimal_places=2, default=0.00)

    class Meta:
        unique_together = ['date', 'instructor', 'webinar']
        ordering = ['-date']
        indexes = [
            models.Index(fields=['date', 'instructor']),
            models.Index(fields=['webinar']),
        ]

    def __str__(self):
        return f"Revenue - {self.instructor.email} - {self.webinar.title} - {self.date}"
