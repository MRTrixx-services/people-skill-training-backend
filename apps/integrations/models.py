# apps/integrations/models.py - ENHANCED for conditional webinar types and auto-conversion
from django.db import models
from django.utils import timezone
from django.core.exceptions import ValidationError
from django.core.validators import MinValueValidator, MaxValueValidator
from apps.users.models import User
import logging

logger = logging.getLogger(__name__)

class ZoomCredentials(models.Model):
    """Store Zoom API credentials for server-to-server OAuth"""
    
    client_id = models.CharField(max_length=255, unique=True)
    client_secret = models.CharField(max_length=255)
    account_id = models.CharField(max_length=255, help_text="Required for server-to-server OAuth")
    is_active = models.BooleanField(default=True)
    
    # Management fields
    name = models.CharField(max_length=100, default='Default Zoom App')
    description = models.TextField(blank=True, null=True)
    
    # ENHANCED: Token caching for better performance
    cached_access_token = models.TextField(
        blank=True, null=True, 
        help_text="Cached access token (encrypted in production)"
    )
    token_expires_at = models.DateTimeField(
        blank=True, null=True, 
        help_text="When cached token expires"
    )
    last_token_refresh = models.DateTimeField(
        blank=True, null=True,
        help_text="Last successful token refresh"
    )
    
    # ADDED: Usage tracking
    total_api_calls = models.BigIntegerField(
        default=0,
        help_text="Total API calls made with these credentials"
    )
    last_used = models.DateTimeField(
        blank=True, null=True,
        help_text="Last time these credentials were used"
    )
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        db_table = 'zoom_credentials'
        verbose_name = 'Zoom Credentials'
        verbose_name_plural = 'Zoom Credentials'
        ordering = ['-created_at']
        constraints = [
            models.UniqueConstraint(
                fields=['is_active'], 
                condition=models.Q(is_active=True),
                name='unique_active_zoom_credentials'
            )
        ]
        indexes = [
            models.Index(fields=['is_active']),
            models.Index(fields=['last_used']),
        ]
    
    def clean(self):
        """Ensure only one active credential exists"""
        if self.is_active and ZoomCredentials.objects.filter(
            is_active=True
        ).exclude(pk=self.pk).exists():
            raise ValidationError('Only one active Zoom credential is allowed.')
    
    def save(self, *args, **kwargs):
        self.clean()
        super().save(*args, **kwargs)
    
    @property
    def is_token_valid(self):
        """Check if cached token is still valid"""
        if not self.cached_access_token or not self.token_expires_at:
            return False
        return timezone.now() < self.token_expires_at
    
    def update_usage_stats(self):
        """Update usage statistics"""
        self.total_api_calls += 1
        self.last_used = timezone.now()
        self.save(update_fields=['total_api_calls', 'last_used'])
    
    def __str__(self):
        return f"{self.name} - {self.client_id[:10]}..."

class ZoomMeeting(models.Model):
    """Store Zoom meeting details for live webinars"""
    
    MEETING_TYPES = [
        (1, 'Instant Meeting'),
        (2, 'Scheduled Meeting'),
        (3, 'Recurring Meeting with no fixed time'),
        (8, 'Recurring Meeting with fixed time'),
    ]
    
    STATUS_CHOICES = [
        ('waiting', 'Waiting'),
        ('started', 'Started'),
        ('ended', 'Ended'),
        ('paused', 'Paused'),  # ADDED: Additional status
    ]
    
    RECORDING_CHOICES = [
        ('none', 'None'),
        ('local', 'Local'),
        ('cloud', 'Cloud'),
    ]
    
    AUDIO_CHOICES = [
        ('both', 'Both'),
        ('telephony', 'Telephony'),
        ('voip', 'VoIP'),
    ]
    
    # FIXED: Use OneToOneField for proper relationship
    # webinar = models.OneToOneField(
    #     'webinars.Webinar',
    #     on_delete=models.CASCADE, 
    #     related_name='zoom_meeting_rel',
    #     null=True, 
    #     blank=True,
    #     help_text="Associated live webinar"
    # )
    webinar = models.ForeignKey(
        'webinars.Webinar',
        on_delete=models.CASCADE, 
        related_name='zoom_meetings',  # Changed to plural
        null=True, 
        blank=True,
        help_text="Associated webinar (one Zoom meeting can be shared across multiple webinars)"
    )
    zoom_meeting_id = models.CharField(max_length=20, db_index=True)
    # Zoom meeting details
    # zoom_meeting_id = models.CharField(max_length=20, unique=True, db_index=True)
    uuid = models.CharField(max_length=255, blank=True, null=True)
    host_id = models.CharField(max_length=100)
    topic = models.CharField(max_length=300)
    agenda = models.TextField(blank=True, null=True)
    meeting_type = models.IntegerField(choices=MEETING_TYPES, default=2)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='waiting')
    
    # Meeting settings
    start_time = models.DateTimeField()
    duration = models.IntegerField(
        validators=[MinValueValidator(1), MaxValueValidator(1440)],
        help_text="Duration in minutes"
    )
    timezone = models.CharField(max_length=50, default='Asia/Kolkata')
    password = models.CharField(max_length=10, blank=True, null=True)
    
    # URLs
    join_url = models.URLField(max_length=1000)
    start_url = models.URLField(max_length=1000)
    
    # Meeting options
    waiting_room = models.BooleanField(default=True)
    join_before_host = models.BooleanField(default=False)
    mute_upon_entry = models.BooleanField(default=True)
    auto_recording = models.CharField(
        max_length=20,
        choices=RECORDING_CHOICES,
        default='cloud'
    )
    
    # ADDED: Enhanced meeting settings
    enable_chat = models.BooleanField(default=True)
    enable_qa = models.BooleanField(default=True)
    allow_screen_share = models.BooleanField(default=True)
    enable_polls = models.BooleanField(default=True)
    
    # Registration settings
    use_pmi = models.BooleanField(default=False)
    approval_type = models.IntegerField(
        choices=[
            (0, 'Automatically approve'),
            (1, 'Manually approve'),
            (2, 'No registration required'),
        ],
        default=2
    )
    registration_type = models.IntegerField(
        choices=[
            (1, 'Register once and attend any occurrence'),
            (2, 'Register for each occurrence'),
            (3, 'Register once and choose occurrences'),
        ],
        default=1
    )
    
    # Audio/Video settings
    audio = models.CharField(max_length=20, choices=AUDIO_CHOICES, default='both')
    video_host = models.BooleanField(default=True)
    video_participant = models.BooleanField(default=True)
    is_linked_existing = models.BooleanField(
        default=False,
        db_index=True,
        help_text="True if this meeting was linked from existing Zoom meetings, False if created by us"
    )
    
    # ADDED: Analytics tracking
    total_participants = models.IntegerField(
        default=0,
        validators=[MinValueValidator(0)],
        help_text="Total number of participants who joined"
    )
    peak_concurrent = models.IntegerField(
        default=0,
        validators=[MinValueValidator(0)],
        help_text="Peak concurrent participants"
    )
    actual_start_time = models.DateTimeField(
        blank=True, null=True,
        help_text="Actual meeting start time from Zoom"
    )
    actual_end_time = models.DateTimeField(
        blank=True, null=True,
        help_text="Actual meeting end time from Zoom"
    )
    
    # Metadata
    created_by = models.ForeignKey(
        User, 
        on_delete=models.CASCADE, 
        related_name='created_zoom_meetings'
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        db_table = 'zoom_meetings'
        verbose_name = 'Zoom Meeting'
        verbose_name_plural = 'Zoom Meetings'
        ordering = ['-start_time']
        indexes = [
            models.Index(fields=['zoom_meeting_id']),
            models.Index(fields=['host_id']),
            models.Index(fields=['status']),
            models.Index(fields=['start_time']),
            models.Index(fields=['created_by']),
            # Composite indexes for better query performance
            models.Index(fields=['status', 'start_time']),
            models.Index(fields=['webinar', 'status']),
        ]
          # ✅ ADDED: Prevent duplicate webinar+meeting combinations
        constraints = [
            models.UniqueConstraint(
                fields=['webinar', 'zoom_meeting_id'],
                name='unique_webinar_zoom_meeting'
            )
        ]

    @property
    def is_active(self):
        if not self.actual_start_time:
            # Use scheduled times if actual times not available
            now = timezone.now()
            start = self.start_time
            end = start + timezone.timedelta(minutes=self.duration)

            # Convert naive to aware if needed
            if timezone.is_naive(start):
                start = timezone.make_aware(start, timezone.get_default_timezone())
            if timezone.is_naive(end):
                end = timezone.make_aware(end, timezone.get_default_timezone())

            return start <= now <= end

        # Use actual times if available
        if self.actual_start_time and not self.actual_end_time:
            return True  # Started but not ended

        return False  # Either not started or already ended

    
    # @property
    # def is_active(self):
    #     """Check if meeting is currently active"""
    #     if not self.actual_start_time:
    #         # Use scheduled times if actual times not available
    #         now = timezone.now()
    #         start = self.start_time
    #         end = start + timezone.timedelta(minutes=self.duration)
    #         return start <= now <= end
        
    #     # Use actual times if available
    #     if self.actual_start_time and not self.actual_end_time:
    #         return True  # Started but not ended
        
    #     return False  # Either not started or already ended
    
    @property
    def actual_duration_minutes(self):
        """Get actual meeting duration in minutes"""
        if self.actual_start_time and self.actual_end_time:
            duration = self.actual_end_time - self.actual_start_time
            return int(duration.total_seconds() / 60)
        return None
    
    def update_analytics(self, participants=None, peak_concurrent=None):
        """Update meeting analytics"""
        if participants is not None:
            self.total_participants = max(self.total_participants, participants)
        if peak_concurrent is not None:
            self.peak_concurrent = max(self.peak_concurrent, peak_concurrent)
        self.save(update_fields=['total_participants', 'peak_concurrent'])
    
    def __str__(self):
        return f"Zoom Meeting: {self.topic} ({self.zoom_meeting_id})"

class ZoomWebinar(models.Model):
    """Store Zoom webinar details for large live events"""
    
    WEBINAR_TYPES = [
        (5, 'Webinar'),
        (6, 'Recurring webinar with no fixed time'),
        (9, 'Recurring webinar with fixed time'),
    ]
    
    STATUS_CHOICES = [
        ('waiting', 'Waiting'),
        ('started', 'Started'),
        ('ended', 'Ended'),
        ('paused', 'Paused'),
    ]
    
    RECORDING_CHOICES = [
        ('none', 'None'),
        ('local', 'Local'),
        ('cloud', 'Cloud'),
    ]
    
    # FIXED: Use OneToOneField for proper relationship
    # webinar = models.OneToOneField(
    #     'webinars.Webinar',
    #     on_delete=models.CASCADE, 
    #     related_name='zoom_webinar_rel',
    #     null=True, 
    #     blank=True,
    #     help_text="Associated live webinar"
    # )
    
    # Zoom webinar details
    # zoom_webinar_id = models.CharField(max_length=20, unique=True, db_index=True)
    webinar = models.ForeignKey(
        'webinars.Webinar',
        on_delete=models.CASCADE, 
        related_name='zoom_webinars',  # Changed to plural
        null=True, 
        blank=True,
        help_text="Associated webinar (one Zoom webinar can be shared across multiple webinars)"
    )
    
    # ✅ CHANGED: Removed unique=True
    zoom_webinar_id = models.CharField(max_length=20, db_index=True)
    uuid = models.CharField(max_length=255, blank=True, null=True)
    host_id = models.CharField(max_length=100)
    topic = models.CharField(max_length=300)
    agenda = models.TextField(blank=True, null=True)
    webinar_type = models.IntegerField(choices=WEBINAR_TYPES, default=5)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='waiting')
    
    # Webinar settings
    start_time = models.DateTimeField()
    duration = models.IntegerField(
        validators=[MinValueValidator(1), MaxValueValidator(1440)],
        help_text="Duration in minutes"
    )
    timezone = models.CharField(max_length=50, default='Asia/Kolkata')
    password = models.CharField(max_length=10, blank=True, null=True)
    
    # URLs
    join_url = models.URLField(max_length=1000)
    registration_url = models.URLField(max_length=1000, blank=True, null=True)
    
    # Webinar options
    approval_type = models.IntegerField(
        choices=[
            (0, 'Automatically approve'),
            (1, 'Manually approve'),
            (2, 'No registration required'),
        ],
        default=0
    )
    registration_type = models.IntegerField(
        choices=[
            (1, 'Attendees register once and can attend any of the occurrences'),
            (2, 'Attendees need to register for each occurrence to attend'),
            (3, 'Attendees register once and can choose one or more occurrences to attend'),
        ],
        default=1
    )
    auto_recording = models.CharField(
        max_length=20,
        choices=RECORDING_CHOICES,
        default='cloud'
    )
    
    # Additional webinar settings
    hd_video = models.BooleanField(default=True)
    hd_video_for_attendees = models.BooleanField(default=True)
    on_demand = models.BooleanField(default=False)
    
    # ADDED: Enhanced webinar features
    enable_qa = models.BooleanField(default=True)
    enable_polls = models.BooleanField(default=True)
    enable_practice_session = models.BooleanField(default=False)
    enable_panelist_chat = models.BooleanField(default=True)
    enable_attendee_chat = models.BooleanField(default=True)
    
    # ADDED: Analytics tracking
    total_attendees = models.IntegerField(
        default=0,
        validators=[MinValueValidator(0)],
        help_text="Total number of attendees who joined"
    )
    peak_concurrent = models.IntegerField(
        default=0,
        validators=[MinValueValidator(0)],
        help_text="Peak concurrent attendees"
    )
    actual_start_time = models.DateTimeField(
        blank=True, null=True,
        help_text="Actual webinar start time from Zoom"
    )
    actual_end_time = models.DateTimeField(
        blank=True, null=True,
        help_text="Actual webinar end time from Zoom"
    )
    
    # Metadata
    created_by = models.ForeignKey(
        User, 
        on_delete=models.CASCADE, 
        related_name='created_zoom_webinars'
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        db_table = 'zoom_webinars'
        verbose_name = 'Zoom Webinar'
        verbose_name_plural = 'Zoom Webinars'
        ordering = ['-start_time']
        indexes = [
            models.Index(fields=['zoom_webinar_id']),
            models.Index(fields=['host_id']),
            models.Index(fields=['status']),
            models.Index(fields=['start_time']),
            models.Index(fields=['created_by']),
            # Composite indexes
            models.Index(fields=['status', 'start_time']),
            models.Index(fields=['webinar', 'status']),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=['webinar', 'zoom_webinar_id'],
                name='unique_webinar_zoom_webinar'
            )
        ]
    
    # @property
    # def is_active(self):
    #     """Check if webinar is currently active"""
    #     if not self.actual_start_time:
    #         # Use scheduled times if actual times not available
    #         now = timezone.now()
    #         start = self.start_time
    #         end = start + timezone.timedelta(minutes=self.duration)
    #         return start <= now <= end
        
    #     # Use actual times if available
    #     if self.actual_start_time and not self.actual_end_time:
    #         return True  # Started but not ended
        
    #     return False  # Either not started or already ended
    @property
    def is_active(self):
        if not self.actual_start_time:
            now = timezone.now()
            start = self.start_time
            end = start + timezone.timedelta(minutes=self.duration)

            # Convert naive to aware if needed
            if timezone.is_naive(start):
                start = timezone.make_aware(start, timezone.get_default_timezone())
            if timezone.is_naive(end):
                end = timezone.make_aware(end, timezone.get_default_timezone())

            return start <= now <= end

        if self.actual_start_time and not self.actual_end_time:
            return True

        return False

    @property
    def actual_duration_minutes(self):
        """Get actual webinar duration in minutes"""
        if self.actual_start_time and self.actual_end_time:
            duration = self.actual_end_time - self.actual_start_time
            return int(duration.total_seconds() / 60)
        return None
    
    def update_analytics(self, attendees=None, peak_concurrent=None):
        """Update webinar analytics"""
        if attendees is not None:
            self.total_attendees = max(self.total_attendees, attendees)
        if peak_concurrent is not None:
            self.peak_concurrent = max(self.peak_concurrent, peak_concurrent)
        self.save(update_fields=['total_attendees', 'peak_concurrent'])
    
    def __str__(self):
        return f"Zoom Webinar: {self.topic} ({self.zoom_webinar_id})"

class ZoomRecording(models.Model):
    """Store Zoom recording details with enhanced auto-conversion support"""
    
    RECORDING_TYPES = [
        ('shared_screen_with_speaker_view', 'Shared screen with speaker view'),
        ('shared_screen_with_gallery_view', 'Shared screen with gallery view'),
        ('speaker_view', 'Speaker view'),
        ('gallery_view', 'Gallery view'),
        ('shared_screen', 'Shared screen'),
        ('audio_only', 'Audio only'),
        ('audio_transcript', 'Audio transcript'),
        ('chat_file', 'Chat file'),
        ('timeline', 'Timeline'),
        ('closed_caption', 'Closed caption'),
        ('poll', 'Poll'),
        ('active_speaker', 'Active speaker'),
        ('whiteboard', 'Whiteboard'),  # ADDED: New Zoom feature
    ]
    
    STATUS_CHOICES = [
        ('processing', 'Processing'),
        ('completed', 'Completed'),
        ('failed', 'Failed'),
        ('expired', 'Expired'),  # ADDED: Recordings can expire
    ]
    
    FILE_TYPE_CHOICES = [
        ('MP4', 'MP4 Video'),
        ('M4A', 'M4A Audio'),
        ('TXT', 'Text'),
        ('VTT', 'VTT Subtitle'),
        ('CSV', 'CSV'),
        ('JSON', 'JSON'),
        ('CHAT', 'Chat File'),  # ADDED: Chat file type
    ]
    
    zoom_meeting = models.ForeignKey(
        ZoomMeeting, 
        on_delete=models.CASCADE, 
        related_name='recordings',
        null=True, 
        blank=True
    )
    zoom_webinar = models.ForeignKey(
        ZoomWebinar, 
        on_delete=models.CASCADE, 
        related_name='recordings',
        null=True, 
        blank=True
    )
    
    # Recording details
    recording_id = models.CharField(max_length=255, unique=True, db_index=True)
    meeting_id = models.CharField(max_length=20, db_index=True)
    recording_type = models.CharField(max_length=50, choices=RECORDING_TYPES)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='processing')
    
    # File details
    file_type = models.CharField(max_length=10, choices=FILE_TYPE_CHOICES)
    file_size = models.BigIntegerField(
        null=True, 
        blank=True,
        validators=[MinValueValidator(0)]
    )
    file_extension = models.CharField(max_length=10, blank=True, null=True)
    download_url = models.URLField(max_length=2000)  # INCREASED: Zoom URLs can be very long
    play_url = models.URLField(max_length=2000, blank=True, null=True)
    
    # ADDED: Additional URLs for different quality
    share_url = models.URLField(max_length=2000, blank=True, null=True)
    embed_url = models.URLField(max_length=2000, blank=True, null=True)
    
    # Timestamps
    recording_start = models.DateTimeField()
    recording_end = models.DateTimeField()
    
    # ADDED: Enhanced metadata
    participant_count = models.IntegerField(
        null=True, 
        blank=True,
        validators=[MinValueValidator(0)]
    )
    topic = models.CharField(max_length=300, blank=True, null=True)
    
    # ADDED: Auto-conversion tracking
    is_primary_recording = models.BooleanField(
        default=False,
        help_text="Whether this is the main recording for auto-conversion"
    )
    auto_converted = models.BooleanField(
        default=False,
        help_text="Whether this recording was used for auto-conversion"
    )
    conversion_date = models.DateTimeField(
        blank=True, null=True,
        help_text="When auto-conversion occurred"
    )
    
    # ADDED: Access control
    password_protected = models.BooleanField(default=False)
    expiry_date = models.DateTimeField(
        blank=True, null=True,
        help_text="When recording expires and becomes unavailable"
    )
    download_allowed = models.BooleanField(
        default=True,
        help_text="Whether download is allowed for this recording"
    )
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        db_table = 'zoom_recordings'
        verbose_name = 'Zoom Recording'
        verbose_name_plural = 'Zoom Recordings'
        ordering = ['-recording_start']
        indexes = [
            models.Index(fields=['recording_id']),
            models.Index(fields=['meeting_id']),
            models.Index(fields=['status']),
            models.Index(fields=['recording_start']),
            models.Index(fields=['is_primary_recording']),
            models.Index(fields=['auto_converted']),
            # Composite indexes
            models.Index(fields=['status', 'recording_start']),
            models.Index(fields=['recording_type', 'status']),
        ]
        constraints = [
            models.CheckConstraint(
                check=models.Q(zoom_meeting__isnull=False) | models.Q(zoom_webinar__isnull=False),
                name='recording_must_have_meeting_or_webinar'
            )
        ]
    
    def clean(self):
        """Enhanced validation for recording data"""
        if not self.zoom_meeting and not self.zoom_webinar:
            raise ValidationError('Recording must be associated with either a meeting or webinar')
        
        if self.zoom_meeting and self.zoom_webinar:
            raise ValidationError('Recording cannot be associated with both meeting and webinar')
        
        if self.recording_end and self.recording_start and self.recording_end <= self.recording_start:
            raise ValidationError('Recording end time must be after start time')
        
        if self.expiry_date and self.expiry_date <= timezone.now():
            self.status = 'expired'
    
    def save(self, *args, **kwargs):
        self.clean()
        super().save(*args, **kwargs)
    
    @property
    def file_size_mb(self):
        """Return file size in MB"""
        if self.file_size:
            return round(self.file_size / (1024 * 1024), 2)
        return 0
    
    @property
    def file_size_gb(self):
        """Return file size in GB for large recordings"""
        if self.file_size:
            return round(self.file_size / (1024 * 1024 * 1024), 2)
        return 0
    
    @property
    def duration_minutes(self):
        """Calculate recording duration in minutes"""
        if self.recording_start and self.recording_end:
            duration = self.recording_end - self.recording_start
            return int(duration.total_seconds() / 60)
        return 0
    
    @property
    def is_expired(self):
        """Check if recording has expired"""
        return self.expiry_date and self.expiry_date <= timezone.now()
    
    @property
    def is_available(self):
        """Check if recording is available for viewing"""
        return (
            self.status == 'completed' and 
            not self.is_expired and
            (self.download_url or self.play_url)
        )
    
    def mark_as_primary(self):
        """Mark this recording as primary for auto-conversion"""
        # Unmark other recordings from the same meeting/webinar
        if self.zoom_meeting:
            self.zoom_meeting.recordings.exclude(pk=self.pk).update(is_primary_recording=False)
        elif self.zoom_webinar:
            self.zoom_webinar.recordings.exclude(pk=self.pk).update(is_primary_recording=False)
        
        self.is_primary_recording = True
        self.save(update_fields=['is_primary_recording'])
    
    def mark_as_auto_converted(self):
        """Mark this recording as used for auto-conversion"""
        self.auto_converted = True
        self.conversion_date = timezone.now()
        self.save(update_fields=['auto_converted', 'conversion_date'])
    
    def __str__(self):
        return f"Recording {self.recording_id} - {self.recording_type}"

class ZoomWebhookEvent(models.Model):
    """Store Zoom webhook events with enhanced processing tracking"""
    
    EVENT_TYPES = [
        ('meeting.started', 'Meeting Started'),
        ('meeting.ended', 'Meeting Ended'),
        ('meeting.participant_joined', 'Participant Joined'),
        ('meeting.participant_left', 'Participant Left'),
        ('meeting.participant_joined_waiting_room', 'Participant in Waiting Room'),
        ('meeting.participant_admitted', 'Participant Admitted'),
        ('meeting.participant_put_in_waiting_room', 'Participant Put in Waiting Room'),
        ('recording.completed', 'Recording Completed'),
        ('recording.started', 'Recording Started'),  # ADDED
        ('recording.stopped', 'Recording Stopped'),  # ADDED
        ('recording.paused', 'Recording Paused'),  # ADDED
        ('recording.resumed', 'Recording Resumed'),  # ADDED
        ('webinar.started', 'Webinar Started'),
        ('webinar.ended', 'Webinar Ended'),
        ('webinar.participant_joined', 'Webinar Participant Joined'),
        ('webinar.participant_left', 'Webinar Participant Left'),
        ('webinar.registration_created', 'Webinar Registration Created'),  # ADDED
        ('webinar.registration_approved', 'Webinar Registration Approved'),  # ADDED
    ]
    
    event_type = models.CharField(max_length=100, db_index=True)
    event_ts = models.BigIntegerField(null=True, blank=True)  # Zoom timestamp
    event_data = models.JSONField()
    
    # ENHANCED: Processing status tracking
    processed = models.BooleanField(default=False, db_index=True)
    processing_error = models.TextField(blank=True, null=True)
    processing_attempts = models.IntegerField(
        default=0,
        validators=[MinValueValidator(0), MaxValueValidator(10)]
    )
    requires_retry = models.BooleanField(
        default=False,
        help_text="Whether this event should be retried"
    )
    retry_after = models.DateTimeField(
        blank=True, null=True,
        help_text="Earliest time to retry processing"
    )
    
    # ADDED: Event categorization
    priority = models.CharField(
        max_length=10,
        choices=[
            ('low', 'Low'),
            ('medium', 'Medium'),
            ('high', 'High'),
            ('critical', 'Critical'),
        ],
        default='medium'
    )
    
    # Metadata
    source_ip = models.GenericIPAddressField(null=True, blank=True)
    user_agent = models.TextField(blank=True, null=True)
    
    # ADDED: Related objects tracking
    zoom_meeting_id = models.CharField(
        max_length=20, blank=True, null=True, db_index=True,
        help_text="Extracted Zoom meeting ID for faster queries"
    )
    zoom_webinar_id = models.CharField(
        max_length=20, blank=True, null=True, db_index=True,
        help_text="Extracted Zoom webinar ID for faster queries"
    )
    
    created_at = models.DateTimeField(auto_now_add=True)
    processed_at = models.DateTimeField(null=True, blank=True)
    
    class Meta:
        db_table = 'zoom_webhook_events'
        verbose_name = 'Zoom Webhook Event'
        verbose_name_plural = 'Zoom Webhook Events'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['event_type']),
            models.Index(fields=['processed']),
            models.Index(fields=['created_at']),
            models.Index(fields=['priority']),
            models.Index(fields=['zoom_meeting_id']),
            models.Index(fields=['zoom_webinar_id']),
            # Composite indexes
            models.Index(fields=['processed', 'processing_attempts']),
            models.Index(fields=['processed', 'priority', 'created_at']),
            models.Index(fields=['requires_retry', 'retry_after']),
        ]
    
    def save(self, *args, **kwargs):
        # Extract meeting/webinar IDs on save
        if not self.zoom_meeting_id and not self.zoom_webinar_id:
            self._extract_ids()
        
        # Set priority based on event type
        if not self.priority or self.priority == 'medium':
            self._set_priority()
        
        super().save(*args, **kwargs)
    
    def _extract_ids(self):
        """Extract meeting/webinar IDs from event data"""
        try:
            payload = self.event_data.get('payload', {})
            obj = payload.get('object', {})
            
            if 'meeting' in self.event_type:
                self.zoom_meeting_id = str(obj.get('id', ''))
            elif 'webinar' in self.event_type:
                self.zoom_webinar_id = str(obj.get('id', ''))
            elif self.event_type.startswith('recording'):
                self.zoom_meeting_id = str(obj.get('id', ''))  # Recording events use meeting ID
        except Exception as e:
            logger.warning(f"Failed to extract IDs from webhook event: {e}")
    
    def _set_priority(self):
        """Set priority based on event type"""
        high_priority_events = [
            'meeting.started', 'meeting.ended',
            'webinar.started', 'webinar.ended',
            'recording.completed'
        ]
        
        if self.event_type in high_priority_events:
            self.priority = 'high'
        elif 'recording' in self.event_type:
            self.priority = 'medium'
        else:
            self.priority = 'low'
    
    def mark_for_retry(self, delay_minutes=5):
        """Mark event for retry with delay"""
        self.requires_retry = True
        self.retry_after = timezone.now() + timezone.timedelta(minutes=delay_minutes)
        self.save(update_fields=['requires_retry', 'retry_after'])
    
    def __str__(self):
        return f"Webhook: {self.event_type} - {self.created_at}"

class ZoomIntegrationLog(models.Model):
    """Enhanced log for Zoom API interactions with better categorization"""
    
    LOG_LEVELS = [
        ('DEBUG', 'Debug'),
        ('INFO', 'Info'),
        ('WARNING', 'Warning'),
        ('ERROR', 'Error'),
        ('CRITICAL', 'Critical'),
    ]
    
    ACTION_TYPES = [
        ('auth', 'Authentication'),
        ('get_token', 'Get Access Token'),
        ('refresh_token', 'Refresh Token'),
        ('create_meeting', 'Create Meeting'),
        ('update_meeting', 'Update Meeting'),
        ('delete_meeting', 'Delete Meeting'),
        ('get_meeting', 'Get Meeting'),
        ('list_meetings', 'List Meetings'),
        ('create_webinar', 'Create Webinar'),
        ('update_webinar', 'Update Webinar'),
        ('delete_webinar', 'Delete Webinar'),
        ('get_webinar', 'Get Webinar'),
        ('list_webinars', 'List Webinars'),
        ('get_recordings', 'Get Recordings'),
        ('delete_recording', 'Delete Recording'),  # ADDED
        ('webhook_received', 'Webhook Received'),
        ('webhook_processed', 'Webhook Processed'),
        ('sync_recordings', 'Sync Recordings'),  # ADDED
        ('auto_conversion', 'Auto Conversion'),  # ADDED
    ]
    
    user = models.ForeignKey(
        User, 
        on_delete=models.SET_NULL,
        related_name='zoom_logs',
        null=True, 
        blank=True
    )
    
    level = models.CharField(max_length=10, choices=LOG_LEVELS, default='INFO')
    action_type = models.CharField(max_length=50, choices=ACTION_TYPES)
    message = models.TextField()
    
    # Request/Response details
    request_data = models.JSONField(null=True, blank=True)
    response_data = models.JSONField(null=True, blank=True)
    status_code = models.IntegerField(
        null=True, 
        blank=True,
        validators=[MinValueValidator(100), MaxValueValidator(599)]
    )
    
    # ADDED: Enhanced metadata
    zoom_meeting_id = models.CharField(max_length=20, blank=True, null=True, db_index=True)
    zoom_webinar_id = models.CharField(max_length=20, blank=True, null=True, db_index=True)
    webinar_id = models.CharField(max_length=20, blank=True, null=True, db_index=True)
    
    # Timing and performance
    execution_time = models.FloatField(
        null=True, 
        blank=True,
        validators=[MinValueValidator(0)]
    )
    
    # ADDED: Error tracking
    error_code = models.CharField(max_length=50, blank=True, null=True)
    retry_count = models.IntegerField(
        default=0,
        validators=[MinValueValidator(0)]
    )
    
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        db_table = 'zoom_integration_logs'
        verbose_name = 'Zoom Integration Log'
        verbose_name_plural = 'Zoom Integration Logs'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['level']),
            models.Index(fields=['action_type']),
            models.Index(fields=['created_at']),
            models.Index(fields=['user']),
            models.Index(fields=['zoom_meeting_id']),
            models.Index(fields=['zoom_webinar_id']),
            models.Index(fields=['webinar_id']),
            # Composite indexes
            models.Index(fields=['level', 'created_at']),
            models.Index(fields=['action_type', 'created_at']),
            models.Index(fields=['level', 'action_type']),
        ]
    
    @classmethod
    def log_action(cls, action_type, message, level='INFO', user=None, **kwargs):
        """Convenience method to create log entries"""
        return cls.objects.create(
            action_type=action_type,
            message=message,
            level=level,
            user=user,
            **kwargs
        )
    
    @classmethod
    def log_api_call(cls, action_type, user=None, request_data=None, 
                     response_data=None, status_code=None, execution_time=None, 
                     error_code=None, **kwargs):
        """Log API calls with structured data"""
        level = 'ERROR' if status_code and status_code >= 400 else 'INFO'
        message = f"API call: {action_type}"
        
        if status_code:
            message += f" (HTTP {status_code})"
        if execution_time:
            message += f" in {execution_time:.2f}s"
        
        return cls.objects.create(
            action_type=action_type,
            message=message,
            level=level,
            user=user,
            request_data=request_data,
            response_data=response_data,
            status_code=status_code,
            execution_time=execution_time,
            error_code=error_code,
            **kwargs
        )
    
    def __str__(self):
        return f"[{self.level}] {self.action_type} - {self.created_at}"
