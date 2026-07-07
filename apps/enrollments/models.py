from django.db import models
from django.core.validators import MinValueValidator, MaxValueValidator
from django.utils import timezone
from apps.users.models import User
from apps.webinars.models import Webinar


class Enrollment(models.Model):
    """User enrollment in webinars - Platform-specific"""
    
    STATUS_CHOICES = [
        ('enrolled', 'Enrolled'),
        ('attended', 'Attended'),
        ('missed', 'Missed'),
        ('cancelled', 'Cancelled'),
        ('refunded', 'Refunded'),
        ('completed', 'Completed')
    ]
    
    ACCESS_TYPE_CHOICES = [
        ('liveOne', 'Live - Single Attendee'),
        ('liveGroup', 'Live - Multi Attendees'),
        ('recordedOne', 'Recorded - Single Attendee'),
        ('recordedGroup', 'Recorded - Multi Attendees'),
        ('comboOne', 'Combo - Single Attendee'),
        ('comboGroup', 'Combo - Multi Attendees'),
    ]
    
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='enrollments')
    webinar = models.ForeignKey(Webinar, on_delete=models.CASCADE, related_name='enrollments')
    
    # ✅ PLATFORM ASSIGNMENT (automatically from user.platform)
    platform = models.ForeignKey(
        'platforms.Platform',
        on_delete=models.CASCADE,
        related_name='enrollments',
        help_text="Platform where enrollment was created (from user.platform)"
    )
    
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='enrolled')
    access_type = models.CharField(
        max_length=20, 
        choices=ACCESS_TYPE_CHOICES, 
        default='liveOne',
        help_text='Type of access purchased: live, recorded, or combo'
    )
    
    # Enrollment details
    enrolled_at = models.DateTimeField(auto_now_add=True)
    payment_amount = models.DecimalField(
        max_digits=10, 
        decimal_places=2, 
        default=0.00,
        validators=[MinValueValidator(0)]
    )
    payment_method = models.CharField(max_length=50, blank=True)
    transaction_id = models.CharField(max_length=100, blank=True)
    
    # Attendance tracking
    joined_at = models.DateTimeField(null=True, blank=True)
    left_at = models.DateTimeField(null=True, blank=True)
    attendance_duration = models.IntegerField(default=0)  # minutes
    
    # Engagement metrics
    questions_asked = models.IntegerField(default=0)
    chat_messages_sent = models.IntegerField(default=0)
    polls_participated = models.IntegerField(default=0)
    
    # Completion tracking
    completion_percentage = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=0.0,
        validators=[MinValueValidator(0.0), MaxValueValidator(100.0)]
    )
    certificate_issued = models.BooleanField(default=False)
    certificate_url = models.URLField(blank=True)
    
    # Feedback
    feedback_submitted = models.BooleanField(default=False)
    would_recommend = models.BooleanField(null=True, blank=True)
    
    # Timestamps
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        db_table = 'enrollments'
        verbose_name = 'Enrollment'
        verbose_name_plural = 'Enrollments'
        unique_together = ['user', 'webinar']
        ordering = ['-enrolled_at']
        indexes = [
            models.Index(fields=['platform', 'status']),
            models.Index(fields=['platform', 'user']),
            models.Index(fields=['platform', 'enrolled_at']),
            models.Index(fields=['status', 'enrolled_at']),
        ]
    
    def save(self, *args, **kwargs):
        # Auto-assign platform from user
        if not self.platform_id and self.user and self.user.platform:
            self.platform = self.user.platform
        super().save(*args, **kwargs)
    
    def __str__(self):
        platform_name = self.platform.name if self.platform else 'No Platform'
        return f"{self.user.full_name} - {self.webinar.title} ({platform_name})"
    
    @property
    def is_active(self):
        return self.status in ['enrolled', 'attended']
    
    @property
    def attended_webinar(self):
        return self.status == 'attended'
    
    def mark_as_attended(self):
        """Mark enrollment as attended"""
        if self.status == 'enrolled':
            self.status = 'attended'
            if not self.joined_at:
                self.joined_at = timezone.now()
            self.save()
    
    def calculate_attendance_duration(self):
        """Calculate attendance duration in minutes"""
        if self.joined_at and self.left_at:
            duration = self.left_at - self.joined_at
            self.attendance_duration = int(duration.total_seconds() / 60)
            self.save()
            return self.attendance_duration
        return 0
    
    def calculate_completion_percentage(self):
        """Calculate completion percentage based on attendance"""
        if self.attendance_duration and self.webinar.duration:
            percentage = (self.attendance_duration / self.webinar.duration) * 100
            self.completion_percentage = min(100.0, percentage)
            self.save()
            return self.completion_percentage
        return 0.0


class EnrollmentFeedback(models.Model):
    """Detailed feedback for enrollments"""
    
    enrollment = models.OneToOneField(
        Enrollment, 
        on_delete=models.CASCADE, 
        related_name='detailed_feedback'
    )
    
    # Overall ratings
    overall_rating = models.IntegerField(
        validators=[MinValueValidator(1), MaxValueValidator(5)],
        help_text="Overall rating from 1 to 5 stars"
    )
    content_rating = models.IntegerField(
        validators=[MinValueValidator(1), MaxValueValidator(5)],
        null=True, blank=True
    )
    instructor_rating = models.IntegerField(
        validators=[MinValueValidator(1), MaxValueValidator(5)],
        null=True, blank=True
    )
    technical_rating = models.IntegerField(
        validators=[MinValueValidator(1), MaxValueValidator(5)],
        null=True, blank=True
    )
    
    # Detailed feedback
    what_liked = models.TextField(blank=True)
    what_improved = models.TextField(blank=True)
    additional_comments = models.TextField(blank=True)
    
    # Recommendations
    would_recommend = models.BooleanField(default=True)
    would_attend_again = models.BooleanField(default=True)
    
    # Learning outcomes
    learning_objectives_met = models.BooleanField(null=True, blank=True)
    skill_level_after = models.CharField(
        max_length=20,
        choices=[
            ('beginner', 'Beginner'),
            ('intermediate', 'Intermediate'),
            ('advanced', 'Advanced'),
            ('expert', 'Expert'),
        ],
        blank=True
    )
    
    submitted_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        db_table = 'enrollment_feedback'
        verbose_name = 'Enrollment Feedback'
        verbose_name_plural = 'Enrollment Feedback'
    
    def __str__(self):
        return f"Feedback for {self.enrollment}"


class AttendanceLog(models.Model):
    """Detailed attendance logging"""
    
    ACTION_CHOICES = [
        ('joined', 'Joined'),
        ('left', 'Left'),
        ('reconnected', 'Reconnected'),
        ('disconnected', 'Disconnected'),
    ]
    
    enrollment = models.ForeignKey(
        Enrollment, 
        on_delete=models.CASCADE, 
        related_name='attendance_logs'
    )
    action = models.CharField(max_length=20, choices=ACTION_CHOICES)
    timestamp = models.DateTimeField(auto_now_add=True)
    
    # Technical details
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    user_agent = models.TextField(blank=True)
    device_info = models.JSONField(default=dict, blank=True)
    
    # Session details
    session_id = models.CharField(max_length=100, blank=True)
    connection_quality = models.CharField(
        max_length=20,
        choices=[
            ('excellent', 'Excellent'),
            ('good', 'Good'),
            ('fair', 'Fair'),
            ('poor', 'Poor'),
        ],
        blank=True
    )
    
    class Meta:
        db_table = 'attendance_logs'
        verbose_name = 'Attendance Log'
        verbose_name_plural = 'Attendance Logs'
        ordering = ['-timestamp']
        indexes = [
            models.Index(fields=['enrollment', 'timestamp']),
            models.Index(fields=['action', 'timestamp']),
        ]
    
    def __str__(self):
        return f"{self.enrollment.user.full_name} - {self.get_action_display()} at {self.timestamp}"


class Certificate(models.Model):
    """Certificates issued for completed webinars"""
    
    enrollment = models.OneToOneField(
        Enrollment, 
        on_delete=models.CASCADE, 
        related_name='certificate'
    )
    
    # Certificate details
    certificate_id = models.CharField(max_length=50, unique=True, db_index=True)
    issued_at = models.DateTimeField(auto_now_add=True)
    
    # Certificate content
    template_used = models.CharField(max_length=100, default='default')
    custom_message = models.TextField(blank=True)
    
    # File storage
    certificate_file = models.FileField(
        upload_to='certificates/', 
        null=True, 
        blank=True
    )
    certificate_url = models.URLField(blank=True)
    
    # Verification
    verification_code = models.CharField(max_length=20, unique=True, db_index=True)
    is_verified = models.BooleanField(default=True)
    
    class Meta:
        db_table = 'certificates'
        verbose_name = 'Certificate'
        verbose_name_plural = 'Certificates'
        ordering = ['-issued_at']
        indexes = [
            models.Index(fields=['certificate_id']),
            models.Index(fields=['verification_code']),
        ]
    
    def __str__(self):
        return f"Certificate for {self.enrollment}"
    
    def save(self, *args, **kwargs):
        if not self.certificate_id:
            # Generate unique certificate ID
            import uuid
            self.certificate_id = f"CERT-{uuid.uuid4().hex[:8].upper()}"
        
        if not self.verification_code:
            # Generate verification code
            import random
            import string
            self.verification_code = ''.join(
                random.choices(string.ascii_uppercase + string.digits, k=8)
            )
        
        super().save(*args, **kwargs)


class EnrollmentReminder(models.Model):
    """Reminders sent to enrolled users"""
    
    REMINDER_TYPES = [
        ('enrollment_confirmation', 'Enrollment Confirmation'),
        ('24h_reminder', '24 Hour Reminder'),
        ('1h_reminder', '1 Hour Reminder'),
        ('starting_now', 'Starting Now'),
        ('missed_webinar', 'Missed Webinar'),
        ('feedback_request', 'Feedback Request'),
    ]
    
    enrollment = models.ForeignKey(
        Enrollment, 
        on_delete=models.CASCADE, 
        related_name='reminders'
    )
    reminder_type = models.CharField(max_length=30, choices=REMINDER_TYPES)
    
    # Scheduling
    scheduled_at = models.DateTimeField()
    sent_at = models.DateTimeField(null=True, blank=True)
    
    # Content
    subject = models.CharField(max_length=200)
    message = models.TextField()
    
    # Status
    is_sent = models.BooleanField(default=False, db_index=True)
    send_email = models.BooleanField(default=True)
    send_sms = models.BooleanField(default=False)
    
    # Tracking
    email_opened = models.BooleanField(default=False)
    email_clicked = models.BooleanField(default=False)
    
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        db_table = 'enrollment_reminders'
        verbose_name = 'Enrollment Reminder'
        verbose_name_plural = 'Enrollment Reminders'
        ordering = ['-scheduled_at']
        indexes = [
            models.Index(fields=['is_sent', 'scheduled_at']),
            models.Index(fields=['reminder_type', 'sent_at']),
        ]
    
    def __str__(self):
        return f"{self.get_reminder_type_display()} for {self.enrollment}"


class WaitlistEntry(models.Model):
    """Waitlist for full webinars - Platform-specific"""
    
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='waitlist_entries')
    webinar = models.ForeignKey(Webinar, on_delete=models.CASCADE, related_name='waitlist_entries')
    
    # ✅ PLATFORM ASSIGNMENT
    platform = models.ForeignKey(
        'platforms.Platform',
        on_delete=models.CASCADE,
        related_name='waitlist_entries',
        help_text="Platform where waitlist entry was created"
    )
    
    # Waitlist details
    joined_at = models.DateTimeField(auto_now_add=True)
    position = models.PositiveIntegerField(default=0)
    
    # Notification preferences
    notify_on_availability = models.BooleanField(default=True)
    notification_sent = models.BooleanField(default=False)
    notification_sent_at = models.DateTimeField(null=True, blank=True)
    
    # Status
    is_active = models.BooleanField(default=True, db_index=True)
    converted_to_enrollment = models.BooleanField(default=False)
    converted_at = models.DateTimeField(null=True, blank=True)
    
    class Meta:
        db_table = 'waitlist_entries'
        verbose_name = 'Waitlist Entry'
        verbose_name_plural = 'Waitlist Entries'
        unique_together = ['user', 'webinar']
        ordering = ['joined_at']
        indexes = [
            models.Index(fields=['platform', 'webinar', 'is_active']),
            models.Index(fields=['platform', 'position']),
        ]
    
    def save(self, *args, **kwargs):
        # Auto-assign platform from user
        if not self.platform_id and self.user and self.user.platform:
            self.platform = self.user.platform
        
        if not self.position:
            # Set position based on existing waitlist entries for THIS PLATFORM
            last_position = WaitlistEntry.objects.filter(
                webinar=self.webinar,
                platform=self.platform,  # ✅ Platform-specific position
                is_active=True
            ).aggregate(
                max_position=models.Max('position')
            )['max_position'] or 0
            
            self.position = last_position + 1
        
        super().save(*args, **kwargs)
    
    def __str__(self):
        platform_name = self.platform.name if self.platform else 'No Platform'
        return f"{self.user.full_name} - {self.webinar.title} (Pos: {self.position}, {platform_name})"
