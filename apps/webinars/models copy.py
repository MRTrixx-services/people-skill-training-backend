# apps/webinars/models.py - ENHANCED with complete auto-conversion workflow and conditional access
from django.db import models
from django.core.validators import MinValueValidator, MaxValueValidator, URLValidator
from django.utils import timezone
from django.core.exceptions import ValidationError
from apps.speakers.models import Speaker
from apps.users.models import User
import logging
from decimal import Decimal

logger = logging.getLogger(__name__)


class Category(models.Model):
    """Webinar categories with optimized performance"""
    
    name = models.CharField(max_length=100, unique=True, db_index=True)
    description = models.TextField(blank=True)
    color = models.CharField(max_length=7, default='#3B82F6')  # Hex color
    icon = models.CharField(max_length=50, blank=True)  # Icon class name
    is_active = models.BooleanField(default=True, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        db_table = 'webinar_categories'
        verbose_name = 'Category'
        verbose_name_plural = 'Categories'
        ordering = ['name']
        indexes = [
            models.Index(fields=['name']),
            models.Index(fields=['is_active']),
        ]
    
    def __str__(self):
        return self.name


class Webinar(models.Model):
    """Main webinar model with Live/Recorded types and auto-conversion"""
    
    STATUS_CHOICES = [
        ('draft', 'Draft'),
        ('scheduled', 'Scheduled'),    # Live webinars before start
        ('live', 'Live'),              # Live webinars currently running  
        ('completed', 'Completed'),    # Live webinars finished
        ('available', 'Available'),    # Recorded webinars ready to watch
        ('cancelled', 'Cancelled'),
    ]
    
    DIFFICULTY_CHOICES = [
        ('beginner', 'Beginner'),
        ('intermediate', 'Intermediate'),
        ('advanced', 'Advanced'),
        ('all-levels', 'All Levels'),
    ]
    
    WEBINAR_TYPE_CHOICES = [
        ('live', 'Live Webinar'),      # Creates Zoom meeting, scheduled sessions
        ('recorded', 'Recorded Only'), # Direct Zoom URL, immediately available
    ]

    # Auto-generated webinar ID
    webinar_id = models.CharField(max_length=20, unique=True, blank=True, db_index=True)
    
    # Basic info
    title = models.CharField(max_length=400, db_index=True)
    description = models.TextField()
    speaker = models.ForeignKey(
        Speaker, 
        on_delete=models.CASCADE, 
        related_name='webinars',
        db_index=True
    )
    category = models.ForeignKey(
        Category, 
        on_delete=models.SET_NULL, 
        null=True, 
        blank=True,
        db_index=True
    )
    skill_level = models.CharField(
        max_length=20, 
        choices=DIFFICULTY_CHOICES, 
        default='beginner',
        db_index=True
    )
    
    # Webinar type field
    webinar_type = models.CharField(
        max_length=20, 
        choices=WEBINAR_TYPE_CHOICES, 
        default='live',
        db_index=True,
        help_text="Live: Creates Zoom meeting | Recorded: Direct Zoom URL"
    )
    platforms = models.ManyToManyField(
        'platforms.Platform',
        related_name='webinars',
        blank=True,
        help_text="Platforms where this webinar is available (leave empty for all platforms)"
    )
    # Scheduling (only for live webinars)
    scheduled_date = models.DateTimeField(null=True, blank=True, db_index=True)
    duration = models.IntegerField(
        null=True, blank=True,
        validators=[MinValueValidator(15), MaxValueValidator(480)],
        help_text="Duration in minutes (required for live webinars)"
    )
    timezone = models.CharField(max_length=50, default='UTC', blank=True)
    
    # Zoom URL (for recorded webinars or post-completion recordings)
    zoom_url = models.URLField(
        blank=True, 
        help_text="Direct Zoom URL for recorded webinars or auto-added recordings"
    )
    
    # Auto-conversion settings and recording tracking
    auto_convert_to_recorded = models.BooleanField(
        default=True,
        help_text="Auto-add recording URL when live webinar completes"
    )
    has_recording = models.BooleanField(
        default=False,
        db_index=True,
        help_text="Whether this webinar has recordings available"
    )
    recording_check_count = models.IntegerField(
        default=0,
        help_text="Number of times we've checked for recordings"
    )
    last_recording_check = models.DateTimeField(
        null=True, blank=True,
        help_text="Last time we checked for recordings"
    )
    
    # Capacity and pricing
    has_enrollment_limit = models.BooleanField(default=False)
    max_attendees = models.IntegerField(null=True, blank=True)
    pricing_data = models.JSONField(default=dict, blank=True)

    # Content details
  
   
    
    # Media
    cover_image = models.ImageField(upload_to='webinar_covers/', null=True, blank=True)
   
    # Status and settings
    status = models.CharField(
        max_length=20, 
        choices=STATUS_CHOICES, 
        default='draft',
        db_index=True
    )
    zoom_preferences = models.JSONField(default=dict, blank=True)
    
    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        db_table = 'webinars'
        verbose_name = 'Webinar'
        verbose_name_plural = 'Webinars'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['webinar_id']),
            models.Index(fields=['title']),
            models.Index(fields=['speaker']),
            models.Index(fields=['category']),
            models.Index(fields=['skill_level']),
            models.Index(fields=['webinar_type']),
            models.Index(fields=['scheduled_date']),
            models.Index(fields=['status']),
            models.Index(fields=['has_recording']),
            models.Index(fields=['created_at']),
            # Composite indexes for better query performance
            models.Index(fields=['webinar_type', 'status']),
            models.Index(fields=['webinar_type', 'scheduled_date']),
            models.Index(fields=['status', 'scheduled_date']),
            models.Index(fields=['speaker', 'status']),
            models.Index(fields=['category', 'status']),
            models.Index(fields=['has_recording', 'status']),
        ]
    
    def __str__(self):
        return f"{self.webinar_id} - {self.get_webinar_type_display()}"
   
    # def clean(self):
    #     """Enhanced model-level validation for conditional fields"""
    #     errors = {}
        
    #     # Validate based on webinar type
    #     if self.webinar_type == 'live':
    #         # Live webinars require scheduling
    #         if not self.scheduled_date:
    #             errors['scheduled_date'] = 'Scheduled date is required for live webinars'
    #         if not self.duration:
    #             errors['duration'] = 'Duration is required for live webinars'
    #     elif self.webinar_type == 'recorded':
    #         # Recorded webinars require Zoom URL
    #         if not self.zoom_url:
    #             errors['zoom_url'] = 'Zoom URL is required for recorded webinars'
    #         # Clear scheduling fields for recorded webinars
    #         self.scheduled_date = None
    #         self.duration = None
    #         self.timezone = 'UTC'
    #         self.zoom_preferences = {}
        
    #     # Enrollment limit validation
    #     if self.has_enrollment_limit and not self.max_attendees:
    #         errors['max_attendees'] = 'Maximum attendees is required when enrollment limit is enabled'
    #     elif not self.has_enrollment_limit:
    #         self.max_attendees = None
        
    #     if errors:
    #         raise ValidationError(errors)

    def is_available_on_platform(self, platform):
        """Check if webinar is available on a specific platform"""
        if not platform:
            return True  # Available on all if no platforms specified
        
        # If no platforms assigned, available on all
        if not self.platforms.exists():
            return True
        
        # Otherwise check if platform is in the list
        return self.platforms.filter(id=platform.id).exists()
    
    def get_platform_names(self):
        """Get comma-separated platform names"""
        platforms = self.platforms.all()
        if not platforms:
            return "All Platforms"
        return ", ".join([p.name for p in platforms])
    
    def clean(self):
        """Enhanced model-level validation for conditional fields"""
        errors = {}
        
        # Validate based on webinar type
        if self.webinar_type == 'live':
            # Live webinars require scheduling
            if not self.scheduled_date:
                errors['scheduled_date'] = 'Scheduled date is required for live webinars'
            if not self.duration:
                errors['duration'] = 'Duration is required for live webinars'
        elif self.webinar_type == 'recorded':
            # Recorded webinars require Zoom URL
            if not self.zoom_url:
                errors['zoom_url'] = 'Zoom URL is required for recorded webinars'
            # Clear scheduling fields EXCEPT duration (needed for recording length)
            self.scheduled_date = None
            # KEEP self.duration - it represents recording length
            self.timezone = 'UTC'
            self.zoom_preferences = {}
        
        # Enrollment limit validation
        if self.has_enrollment_limit and not self.max_attendees:
            errors['max_attendees'] = 'Maximum attendees is required when enrollment limit is enabled'
        elif not self.has_enrollment_limit:
            self.max_attendees = None
        
        if errors:
            raise ValidationError(errors)

    def save(self, *args, **kwargs):
        is_new = self.pk is None
        old_status = None
        old_webinar_type = None
        
        if not is_new:
            try:
                old_instance = Webinar.objects.get(pk=self.pk)
                old_status = old_instance.status
                old_webinar_type = old_instance.webinar_type
            except Webinar.DoesNotExist:
                pass
        
        if not self.webinar_id:
            self.webinar_id = self.generate_webinar_id()
        
        # Set appropriate status based on webinar type
        if is_new:
            if self.webinar_type == 'recorded':
                self.status = 'available'  # Recorded webinars immediately available
            elif self.status == 'draft':
                self.status = 'scheduled'  # Live webinars start as scheduled
        
        # Only update time-based status for live webinars
        if self.webinar_type == 'live':
            self.update_status_based_on_time()
            
            # Check for recordings when live webinar completes
            if old_status != 'completed' and self.status == 'completed' and self.auto_convert_to_recorded:
                self._schedule_recording_check()
        
        self.full_clean()
        super().save(*args, **kwargs)
        
        # Only handle Zoom integration for LIVE webinars
        if self.webinar_type == 'live':
            self._handle_zoom_integration(is_new, old_status)
        elif old_webinar_type == 'live' and self.webinar_type == 'recorded':
            self._cleanup_zoom_integration()

    def _schedule_recording_check(self):
        """Schedule recording check after live webinar completion"""
        from threading import Timer
        logger.info(f"📅 Scheduling recording check for live webinar {self.webinar_id}")
        
        # Check immediately, then schedule delayed checks
        Timer(10.0, self.check_for_recordings).start()   # 10 seconds later
        Timer(1800.0, self.check_for_recordings).start() # 30 minutes later

    def check_for_recordings(self):
        """Check for recordings and add to completed live webinars"""
        if self.webinar_type != 'live' or self.status != 'completed':
            return
        
        try:
            logger.info(f"🔍 Checking for recordings for completed live webinar {self.webinar_id}")
            
            from apps.integrations.services import ZoomWebinarService
            zoom_service = ZoomWebinarService()
            
            # Get recordings from Zoom
            recordings = zoom_service.sync_recordings(self)
            
            self.recording_check_count += 1
            self.last_recording_check = timezone.now()
            
            if recordings and len(recordings) > 0:
                logger.info(f"✅ Found {len(recordings)} recordings for live webinar {self.webinar_id}")
                
                # Get the main recording URL
                main_recording = recordings[0]
                if hasattr(main_recording, 'play_url') and main_recording.play_url:
                    self.zoom_url = main_recording.play_url
                elif hasattr(main_recording, 'download_url') and main_recording.download_url:
                    self.zoom_url = main_recording.download_url
                
                self.has_recording = True
                
                # Add recorded pricing if live pricing exists but no recorded pricing
                if self.pricing_data:
                    updated_pricing = False
                    if not self.pricing_data.get('recorded_single_price') and self.pricing_data.get('live_single_price'):
                        self.pricing_data['recorded_single_price'] = self.pricing_data['live_single_price']
                        updated_pricing = True
                    if not self.pricing_data.get('recorded_multi_price') and self.pricing_data.get('live_multi_price'):
                        self.pricing_data['recorded_multi_price'] = self.pricing_data['live_multi_price']
                        updated_pricing = True
                    
                    if updated_pricing:
                        logger.info(f"💰 Added recorded pricing options to completed live webinar")
                
                logger.info(f"🎉 Added recording access to completed live webinar {self.webinar_id}")
                
            else:
                logger.info(f"📝 No recordings found yet for webinar {self.webinar_id} (attempt {self.recording_check_count})")
            
            # Save updates
            self.save(update_fields=[
                'zoom_url', 'has_recording', 'recording_check_count', 
                'last_recording_check', 'pricing_data'
            ])
            
        except Exception as e:
            logger.error(f"❌ Error checking recordings for webinar {self.webinar_id}: {str(e)}")

    def _handle_zoom_integration(self, is_new: bool, old_status: str = None):
        """Handle Zoom integration ONLY for live webinars"""
        if self.webinar_type != 'live':
            logger.info(f"⏭️ Skipping Zoom integration for {self.webinar_type} webinar: {self.webinar_id}")
            return
            
        try:
            logger.info(f"🔗 Starting Zoom integration for LIVE webinar: {self.webinar_id}")
            
            from apps.integrations.services import ZoomWebinarService
            zoom_service = ZoomWebinarService()
            
            if self.status == 'scheduled':
                if is_new:
                    logger.info(f"🆕 Creating NEW Zoom meeting for live webinar: {self.webinar_id}")
                    zoom_result = zoom_service.create_webinar_meeting(
                        self, 
                        user=self.speaker.user, 
                        preferences=self.zoom_preferences
                    )
                    if zoom_result:
                        logger.info(f"✅ Zoom meeting created successfully!")
                else:
                    logger.info(f"🔄 Updating existing Zoom meeting for live webinar: {self.webinar_id}")
                    zoom_service.update_webinar_meeting(self, preferences=self.zoom_preferences)
            
            elif self.status == 'cancelled' and old_status == 'scheduled':
                logger.info(f"🗑️ Deleting Zoom meeting for cancelled live webinar: {self.webinar_id}")
                zoom_service.delete_webinar_meeting(self)
                    
        except Exception as e:
            logger.error(f"❌ Zoom integration failed for live webinar {self.webinar_id}: {str(e)}")

    def _cleanup_zoom_integration(self):
        """Clean up Zoom integration when switching to recorded type"""
        try:
            logger.info(f"🧹 Cleaning up Zoom integration for webinar: {self.webinar_id}")
            from apps.integrations.services import ZoomWebinarService
            zoom_service = ZoomWebinarService()
            zoom_service.delete_webinar_meeting(self)
        except Exception as e:
            logger.error(f"Failed to cleanup Zoom integration for webinar {self.webinar_id}: {str(e)}")
  
    def update_status_based_on_time(self):
        """Update status based on time (only for live webinars)"""
        if self.webinar_type != 'live' or not self.scheduled_date or not self.duration:
            return
            
        now = timezone.now()
        end_time = self.scheduled_date + timezone.timedelta(minutes=self.duration)
        
        if self.status in ['cancelled', 'draft']:
            return
        
        if now < self.scheduled_date:
            if self.status != 'scheduled':
                self.status = 'scheduled'
        elif self.scheduled_date <= now <= end_time:
            if self.status != 'live':
                self.status = 'live'
        # elif now > end_time:
        #     if self.status != 'completed':
        #         self.status = 'completed'

    # ENHANCED: Methods for conditional Zoom access
    def get_zoom_links_for_user(self, user):
        """Get user-specific Zoom access information with conditional access control"""
        if not user or not user.is_authenticated:
            return {'can_join': False, 'message': 'Authentication required'}
        
        # Check access permissions first
        if not self._can_user_access_zoom(user):
            return {'can_join': False, 'message': 'no access'}
        
        # For recorded webinars
        if self.webinar_type == 'recorded':
            if self.zoom_url:
                return {
                    'can_join': True,
                    'join_url': self.zoom_url,
                    'message': 'Recording available',
                    'type': 'recorded'
                }
            else:
                return {'can_join': False, 'message': 'Recording not available'}
        
        # For live webinars
        if self.webinar_type == 'live':
            # Admin users and speakers get full host access
            if user.is_staff or user.is_superuser or user == self.speaker.user:
                zoom_meeting = getattr(self, 'zoom_meeting_rel', None)
                zoom_webinar = getattr(self, 'zoom_webinar_rel', None)
                
                if zoom_meeting:
                    return {
                        'can_join': True,
                        'can_start': True,
                        'join_url': zoom_meeting.join_url,
                        'start_url': zoom_meeting.start_url,
                        'message': 'Host access available'
                    }
                elif zoom_webinar:
                    return {
                        'can_join': True,
                        'can_start': True,
                        'join_url': zoom_webinar.join_url,
                        'message': 'Webinar host access available'
                    }
            
            # Enrolled users get participant access only
            elif self._is_user_enrolled(user):
                zoom_meeting = getattr(self, 'zoom_meeting_rel', None)
                zoom_webinar = getattr(self, 'zoom_webinar_rel', None)
                
                if zoom_meeting:
                    return {
                        'can_join': True,
                        'can_start': False,  # No start access for attendees
                        'join_url': zoom_meeting.join_url,
                        'message': 'Ready to join live session'
                    }
                elif zoom_webinar:
                    return {
                        'can_join': True,
                        'can_start': False,  # No start access for attendees
                        'join_url': zoom_webinar.join_url,
                        'message': 'Ready to join webinar'
                    }
            
            # Recording access for completed live webinars
            if self.status == 'completed' and self.has_recording and self.zoom_url:
                return {
                    'can_join': True,
                    'can_start': False,
                    'join_url': self.zoom_url,
                    'message': 'Recording available from live session',
                    'type': 'recording'
                }
        
        return {'can_join': False, 'message': 'no access'}

    def _can_user_access_zoom(self, user):
        """Helper method to check if user can access Zoom links"""
        if not user or not user.is_authenticated:
            return False
        
        # Admin users get full access
        if user.is_staff or user.is_superuser:
            return True
        
        # Speaker gets access to their own webinars
        if hasattr(self, 'speaker') and self.speaker.user == user:
            return True
        
        # Check if user is enrolled/purchased
        return self._is_user_enrolled(user)

    def _is_user_enrolled(self, user):
        """Helper method to check if user is enrolled"""
        if not hasattr(self, 'enrollments'):
            return False
            
        enrollment = self.enrollments.filter(
            user=user, 
            status__in=['enrolled', 'attended', 'completed']
        ).first()
        
        if enrollment:
            # Additional payment verification if needed
            if hasattr(enrollment, 'payment_status') and enrollment.payment_status != 'completed':
                return False
            return True
        
        return False

    def can_user_access_webinar(self, user=None):
        """Check if user can access webinar details"""
        if not user or not user.is_authenticated:
            return False
        
        # Admins can access everything
        if user.is_admin():
            return True
        
        # Instructors can access their own webinars
        if user == self.speaker.user:
            return True
        
        # Enrolled users can access
        return self._is_user_enrolled(user)

    def get_user_enrollment_status(self, user=None):
        """Get user's enrollment status for this webinar"""
        if not user or not user.is_authenticated:
            return None
        
        if hasattr(self, 'enrollments'):
            enrollment = self.enrollments.filter(user=user).first()
            return enrollment.status if enrollment else None
        
        return None

    # Get applicable prices based on webinar type and availability
    # def get_applicable_prices(self):
    #     """Get pricing options based on webinar type"""
    #     if not self.pricing_data:
    #         return {}
        
    #     prices = {}
        
    #     if self.webinar_type == 'live':
    #         # Live webinar: show live and combo pricing
    #         if self.pricing_data.get('live_single_price'):
    #             prices['live_single'] = self.pricing_data['live_single_price']
    #         if self.pricing_data.get('live_multi_price'):
    #             prices['live_multi'] = self.pricing_data['live_multi_price']
    #         if self.pricing_data.get('combo_single_price'):
    #             prices['combo_single'] = self.pricing_data['combo_single_price']
    #         if self.pricing_data.get('combo_multi_price'):
    #             prices['combo_multi'] = self.pricing_data['combo_multi_price']
            
    #         # If has recording, also show recorded pricing
    #         # if self.has_recording:
    #         if self.pricing_data.get('recorded_single_price'):
    #             prices['recorded_single'] = self.pricing_data['recorded_single_price']
    #         if self.pricing_data.get('recorded_multi_price'):
    #             prices['recorded_multi'] = self.pricing_data['recorded_multi_price']
                    
    #     elif self.webinar_type == 'recorded':
    #         # Recorded webinar: only recorded pricing
    #         if self.pricing_data.get('recorded_single_price'):
    #             prices['recorded_single'] = self.pricing_data['recorded_single_price']
    #         if self.pricing_data.get('recorded_multi_price'):
    #             prices['recorded_multi'] = self.pricing_data['recorded_multi_price']
        
    #     return prices
    def get_applicable_prices(self):
        """Get pricing options based on webinar type"""
        if not self.pricing_data:
            return {}
        
        prices = {}
        
        if self.webinar_type == 'live':
            # Live webinar: show live and combo pricing
            if self.pricing_data.get('live_single_price'):
                prices['live_single'] = self.pricing_data['live_single_price']
            if self.pricing_data.get('live_multi_price'):
                prices['live_multi'] = self.pricing_data['live_multi_price']
            if self.pricing_data.get('combo_single_price'):
                prices['combo_single'] = self.pricing_data['combo_single_price']
            if self.pricing_data.get('combo_multi_price'):
                prices['combo_multi'] = self.pricing_data['combo_multi_price']
            
            # If recorded prices exist, recording will be available in future
            # Show recorded pricing as a future purchase option
            if self.pricing_data.get('recorded_single_price'):
                prices['recorded_single'] = self.pricing_data['recorded_single_price']
            if self.pricing_data.get('recorded_multi_price'):
                prices['recorded_multi'] = self.pricing_data['recorded_multi_price']
                    
        elif self.webinar_type == 'recorded':
            # Recorded webinar: only recorded pricing
            if self.pricing_data.get('recorded_single_price'):
                prices['recorded_single'] = self.pricing_data['recorded_single_price']
            if self.pricing_data.get('recorded_multi_price'):
                prices['recorded_multi'] = self.pricing_data['recorded_multi_price']
        
        return prices


# Add these methods to your Webinar model after get_applicable_prices()

    def get_price_for_platform(self, platform, price_type=None):
        """
        Get platform-specific price or fallback to default
        platform: Platform instance
        price_type: 'live_single_price', 'recorded_single_price', etc.
        """
        if not platform:
            if price_type:
                return self.pricing_data.get(price_type)
            return self.get_applicable_prices()
        
        # Try to get platform-specific price
        try:
            platform_price = self.platform_prices.get(
                platform=platform,
                is_active=True
            )
            
            if price_type:
                price = platform_price.get_price(price_type)
                if price is not None:
                    return price
            else:
                prices = platform_price.get_all_prices()
                if prices:
                    return prices
                    
        except:
            pass
        
        # Fallback to default pricing
        if price_type:
            return self.pricing_data.get(price_type)
        return self.get_applicable_prices()

    def get_all_prices_for_platform(self, platform):
        """
        Get all access type prices for a specific platform
        Returns platform-specific pricing if available, otherwise defaults
        """
        if not platform:
            return self.get_applicable_prices()
        
        # Try platform-specific pricing first
        try:
            platform_price = self.platform_prices.get(
                platform=platform,
                is_active=True
            )
            prices = platform_price.get_all_prices()
            if prices:
                return prices
        except:
            pass
        
        # Fallback to default
        return self.get_applicable_prices()



    @property
    def is_past_cancellation_deadline(self):
        """Check if 24 hours past scheduled end time (in meeting timezone)"""
        if not self.scheduled_date or not self.duration or self.webinar_type != 'live':
            return False
        
        try:
            meeting_tz = pytz.timezone(self.timezone) if self.timezone else pytz.UTC
            scheduled_end = self.scheduled_date + timedelta(minutes=self.duration)
            cancellation_deadline = scheduled_end + timedelta(hours=24)
            
            now_utc = timezone.now().astimezone(pytz.UTC)
            deadline_utc = cancellation_deadline.astimezone(pytz.UTC)
            
            return now_utc > deadline_utc
        except:
            return False

    @property
    def display_status(self):
        """Get user-friendly status display"""
        if self.webinar_type == 'recorded':
            return 'Available Now'
        elif self.webinar_type == 'live':
            if self.status == 'completed' and self.has_recording:
                return 'Live Session + Recording Available'
            return self.get_status_display()
        return self.get_status_display()

    def generate_webinar_id(self):
        """Generate unique webinar ID"""
        from datetime import datetime
        
        current_date = datetime.now()
        short_year = str(current_date.year)[2:]
        current_month = current_date.strftime('%m')
        prefix = f"WEB{short_year}{current_month}"
        
        last_webinar = Webinar.objects.filter(
            webinar_id__startswith=prefix
        ).order_by('webinar_id').last()
        
        if last_webinar:
            last_sequence = int(last_webinar.webinar_id[len(prefix):])
            new_sequence = last_sequence + 1
        else:
            new_sequence = 1
        
        return f"{prefix}{new_sequence:03d}"

    # Properties with conditional logic and null checks
    @property
    def instructor(self):
        """Alias for backward compatibility"""
        return self.speaker
    
    @property
    def is_upcoming(self):
        if self.webinar_type == 'recorded':
            return False  # Recorded webinars are always available
        return self.scheduled_date and self.scheduled_date > timezone.now()
    
    @property
    def is_live_now(self):
        if self.webinar_type == 'recorded':
            return False  # Recorded webinars are never "live"
        if not self.scheduled_date or not self.duration:
            return False
        now = timezone.now()
        end_time = self.scheduled_date + timezone.timedelta(minutes=self.duration)
        return self.scheduled_date <= now <= end_time
    
    @property
    def is_completed(self):
        if self.webinar_type == 'recorded':
            return self.status == 'available'  # Recorded are "completed" when available
        if not self.scheduled_date or not self.duration:
            return False
        now = timezone.now()
        end_time = self.scheduled_date + timezone.timedelta(minutes=self.duration)
        return now > end_time
    
    @property
    def end_time(self):
        if self.webinar_type == 'live' and self.scheduled_date and self.duration:
            return self.scheduled_date + timezone.timedelta(minutes=self.duration)
        return None
    
    @property
    def enrolled_count(self):
        if hasattr(self, 'enrollments'):
            return self.enrollments.filter(status='enrolled').count()
        return 0
    
    @property
    def available_spots(self):
        if not self.has_enrollment_limit:
            return None
        return max(0, self.max_attendees - self.enrolled_count)

    @property
    def is_full(self):
        if not self.has_enrollment_limit:
            return False
        return self.enrolled_count >= self.max_attendees
    
    @property
    def has_unlimited_capacity(self):
        return not self.has_enrollment_limit
    # In apps/webinars/models.py - Update the Webinar model

        
    @property
    def main_price(self):
        """
        Calculate and return the minimum price among all applicable pricing options for this webinar,
        including platform-specific prices.
        """
        try:
            prices = self.get_applicable_prices()  # Should return dict of prices (strings or numbers)
            if not prices:
                return Decimal('0.00')

            price_values = []
            for p in prices.values():
                try:
                    val = float(p)
                    if val > 0:
                        price_values.append(val)
                except (ValueError, TypeError):
                    continue

            if price_values:
                return Decimal(str(min(price_values)))
            else:
                return Decimal('0.00')

        except Exception as e:
            logger.error(f"Error computing main_price for webinar {self.webinar_id}: {e}")
            return Decimal('0.00')
    # @property
    # def main_price(self):
    #     """Get the main price from pricing data based on webinar type"""
    #     if not self.pricing_data:
    #         return 0.00
        
    #     # Priority based on webinar type
    #     if self.webinar_type == 'live':
    #         price_fields = ['live_single_price', 'live_multi_price', 'combo_single_price', 'combo_multi_price']
    #     else:
    #         price_fields = ['recorded_single_price', 'recorded_multi_price']
        
    #     for field in price_fields:
    #         if self.pricing_data.get(field):
    #             return float(self.pricing_data[field])
        
    #     return 0.00

    @property
    def is_free(self):
        return self.main_price == 0.00
    
    @property
    def has_early_bird_pricing(self):
        return self.pricing_data.get('has_early_bird', False)
    
    @property
    def zoom_webinar_link(self):
        """Get Zoom link - either from integration or direct URL"""
        # For recorded webinars, return the zoom_url directly
        if self.webinar_type == 'recorded' and self.zoom_url:
            return self.zoom_url
            
        # For live webinars, get from integration
        if hasattr(self, 'zoom_meeting_rel') and self.zoom_meeting_rel:
            return self.zoom_meeting_rel.join_url
        elif hasattr(self, 'zoom_webinar_rel') and self.zoom_webinar_rel:
            return self.zoom_webinar_rel.join_url
        return ''

    @property
    def recording_links(self):
        """Get recording links from Zoom recordings or direct URL"""
        recordings = []
        
        # Add direct zoom_url if available (for recorded webinars or completed live)
        if self.zoom_url:
            recordings.append({
                'title': f"Recording - {self.title}",
                'url': self.zoom_url,
                'type': 'primary_recording',
                'file_type': 'URL',
                'duration': self.duration if self.duration else 0,
                'size': 0
            })
        
        # Get recordings from Zoom meetings
        if hasattr(self, 'zoom_meeting_rel') and self.zoom_meeting_rel:
            for recording in self.zoom_meeting_rel.recordings.all():
                recordings.append({
                    'title': f"{recording.recording_type} - {recording.topic}",
                    'url': recording.play_url or recording.download_url,
                    'type': recording.recording_type,
                    'file_type': recording.file_type,
                    'duration': recording.duration_minutes,
                    'size': recording.file_size_mb
                })
        
        # Get recordings from Zoom webinars
        if hasattr(self, 'zoom_webinar_rel') and self.zoom_webinar_rel:
            for recording in self.zoom_webinar_rel.recordings.all():
                recordings.append({
                    'title': f"{recording.recording_type} - {recording.topic}",
                    'url': recording.play_url or recording.download_url,
                    'type': recording.recording_type,
                    'file_type': recording.file_type,
                    'duration': recording.duration_minutes,
                    'size': recording.file_size_mb
                })
        
        return recordings

    @classmethod
    def update_all_statuses(cls):
        """Class method to update all live webinar statuses"""
        webinars = cls.objects.filter(webinar_type='live').exclude(status__in=['cancelled', 'draft'])
        updated_count = 0
        
        for webinar in webinars:
            old_status = webinar.status
            webinar.update_status_based_on_time()
            if old_status != webinar.status:
                webinar.save(update_fields=['status', 'updated_at'])
                updated_count += 1
        
        return updated_count

class WebinarPlatformPrice(models.Model):
    """Platform-specific pricing for webinars"""
    
    webinar = models.ForeignKey(
        Webinar,
        on_delete=models.CASCADE,
        related_name='platform_prices'
    )
    platform = models.ForeignKey(
        'platforms.Platform',
        on_delete=models.CASCADE,
        related_name='webinar_prices'
    )
    
    # Pricing data (matches webinar pricing structure)
    pricing_data = models.JSONField(
        default=dict,
        blank=True,
        help_text="Platform-specific pricing override"
    )
    
    # Discount settings
    discount_percentage = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=0,
        validators=[MinValueValidator(0), MaxValueValidator(100)],
        help_text="Discount percentage for this platform"
    )
    
    is_active = models.BooleanField(default=True, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        db_table = 'webinar_platform_prices'
        verbose_name = 'Webinar Platform Price'
        verbose_name_plural = 'Webinar Platform Prices'
        unique_together = ['webinar', 'platform']
        ordering = ['platform__name']
        indexes = [
            models.Index(fields=['webinar', 'platform']),
            models.Index(fields=['platform', 'is_active']),
            models.Index(fields=['is_active']),
        ]
    
    def __str__(self):
        return f"{self.webinar.title} - {self.platform.name}"
    
    def get_price(self, price_type):
        """
        Get price for specific type with discount applied
        price_type: 'live_single_price', 'recorded_single_price', etc.
        """
        if not self.pricing_data or price_type not in self.pricing_data:
            return None
        
        base_price = self.pricing_data[price_type]
        
        if base_price and self.discount_percentage > 0:
            from decimal import Decimal
            discount = Decimal(str(base_price)) * (self.discount_percentage / 100)
            return float(Decimal(str(base_price)) - discount)
        
        return float(base_price) if base_price else None
    
    def get_all_prices(self):
        """Get all prices with discounts applied"""
        prices = {}
        
        for price_key, base_price in self.pricing_data.items():
            if base_price:
                if self.discount_percentage > 0:
                    from decimal import Decimal
                    discount = Decimal(str(base_price)) * (self.discount_percentage / 100)
                    prices[price_key] = float(Decimal(str(base_price)) - discount)
                else:
                    prices[price_key] = float(base_price)
        
        return prices

class WebinarResource(models.Model):
    """Resources attached to webinars with optimized performance"""
    
    RESOURCE_TYPES = [
        ('pdf', 'PDF Document'),
        ('video', 'Video'),
        ('audio', 'Audio'),
        ('image', 'Image'),
        ('link', 'External Link'),
        ('other', 'Other'),
    ]
    
    webinar = models.ForeignKey(
        Webinar, 
        on_delete=models.CASCADE, 
        related_name='resources',
        db_index=True
    )
    title = models.CharField(max_length=200, db_index=True)
    description = models.TextField(blank=True)
    resource_type = models.CharField(
        max_length=20, 
        choices=RESOURCE_TYPES, 
        default='pdf',
        db_index=True
    )
    
    # File or URL
    file = models.FileField(upload_to='webinar_resources/', null=True, blank=True)
    url = models.URLField(blank=True)
    
    # Access control
    is_public = models.BooleanField(default=False, db_index=True)
    is_downloadable = models.BooleanField(default=True)
    
    # Metadata
    file_size = models.BigIntegerField(null=True, blank=True)
    uploaded_at = models.DateTimeField(auto_now_add=True, db_index=True)
    
    class Meta:
        db_table = 'webinar_resources'
        verbose_name = 'Webinar Resource'
        verbose_name_plural = 'Webinar Resources'
        ordering = ['title']
        indexes = [
            models.Index(fields=['webinar']),
            models.Index(fields=['title']),
            models.Index(fields=['resource_type']),
            models.Index(fields=['is_public']),
            models.Index(fields=['uploaded_at']),
            # Composite indexes
            models.Index(fields=['webinar', 'is_public']),
            models.Index(fields=['webinar', 'resource_type']),
        ]
    
    def __str__(self):
        return f"{self.webinar.title} - {self.title}"


class WebinarSession(models.Model):
    """Individual sessions within a webinar (for multi-session webinars)"""
    
    webinar = models.ForeignKey(
        Webinar, 
        on_delete=models.CASCADE, 
        related_name='sessions',
        db_index=True
    )
    title = models.CharField(max_length=200, db_index=True)
    description = models.TextField(blank=True)
    session_number = models.PositiveIntegerField(db_index=True)
    scheduled_date = models.DateTimeField(db_index=True)
    duration = models.IntegerField()  # minutes
    
    # Session-specific settings
    zoom_meeting_id = models.CharField(max_length=100, blank=True, db_index=True)
    zoom_join_url = models.URLField(blank=True)
    recording_url = models.URLField(blank=True)
    
    is_completed = models.BooleanField(default=False, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        db_table = 'webinar_sessions'
        verbose_name = 'Webinar Session'
        verbose_name_plural = 'Webinar Sessions'
        ordering = ['session_number']
        unique_together = ['webinar', 'session_number']
        indexes = [
            models.Index(fields=['webinar']),
            models.Index(fields=['session_number']),
            models.Index(fields=['scheduled_date']),
            models.Index(fields=['zoom_meeting_id']),
            models.Index(fields=['is_completed']),
            # Composite indexes
            models.Index(fields=['webinar', 'session_number']),
            models.Index(fields=['webinar', 'is_completed']),
        ]
    
    def __str__(self):
        return f"{self.webinar.title} - Session {self.session_number}"


class WebinarReview(models.Model):
    """Reviews and ratings for completed webinars with optimized queries"""
    
    webinar = models.ForeignKey(
        Webinar, 
        on_delete=models.CASCADE, 
        related_name='reviews',
        db_index=True
    )
    user = models.ForeignKey(
        User, 
        on_delete=models.CASCADE, 
        related_name='webinar_reviews',
        db_index=True
    )
    
    rating = models.IntegerField(
        validators=[MinValueValidator(1), MaxValueValidator(5)],
        help_text="Rating from 1 to 5 stars",
        db_index=True
    )
    review_text = models.TextField(blank=True)
    
    # Review aspects
    content_quality = models.IntegerField(
        validators=[MinValueValidator(1), MaxValueValidator(5)],
        null=True, blank=True
    )
    instructor_performance = models.IntegerField(
        validators=[MinValueValidator(1), MaxValueValidator(5)],
        null=True, blank=True
    )
    technical_quality = models.IntegerField(
        validators=[MinValueValidator(1), MaxValueValidator(5)],
        null=True, blank=True
    )
    
    would_recommend = models.BooleanField(default=True, db_index=True)
    is_verified_purchase = models.BooleanField(default=False, db_index=True)
    
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        db_table = 'webinar_reviews'
        verbose_name = 'Webinar Review'
        verbose_name_plural = 'Webinar Reviews'
        ordering = ['-created_at']
        unique_together = ['webinar', 'user']
        indexes = [
            models.Index(fields=['webinar']),
            models.Index(fields=['user']),
            models.Index(fields=['rating']),
            models.Index(fields=['would_recommend']),
            models.Index(fields=['is_verified_purchase']),
            models.Index(fields=['created_at']),
            # Composite indexes
            models.Index(fields=['webinar', 'rating']),
            models.Index(fields=['webinar', 'is_verified_purchase']),
        ]
    
    def __str__(self):
        return f"{self.webinar.title} - {self.user.full_name} ({self.rating}★)"


class WebinarAnalytics(models.Model):
    """Analytics data for webinars with optimized calculations"""
    
    webinar = models.OneToOneField(
        Webinar, 
        on_delete=models.CASCADE, 
        related_name='analytics'
    )
    
    # Enrollment metrics
    total_enrollments = models.IntegerField(default=0, db_index=True)
    total_attendees = models.IntegerField(default=0, db_index=True)
    peak_concurrent_attendees = models.IntegerField(default=0)
    
    # Engagement metrics
    average_attendance_duration = models.IntegerField(default=0)  # minutes
    total_questions_asked = models.IntegerField(default=0)
    total_chat_messages = models.IntegerField(default=0)
    
    # Quality metrics
    average_rating = models.DecimalField(
        max_digits=3, 
        decimal_places=2, 
        default=0.0,
        validators=[MinValueValidator(0.0), MaxValueValidator(5.0)],
        db_index=True
    )
    total_reviews = models.IntegerField(default=0)
    
    # Financial metrics
    total_revenue = models.DecimalField(
        max_digits=10, 
        decimal_places=2, 
        default=0.00,
        db_index=True
    )
    
    # Completion metrics
    completion_rate = models.DecimalField(
        max_digits=5, 
        decimal_places=2, 
        default=0.0,
        validators=[MinValueValidator(0.0), MaxValueValidator(100.0)]
    )
    
    # Timestamps
    last_updated = models.DateTimeField(auto_now=True, db_index=True)
    
    class Meta:
        db_table = 'webinar_analytics'
        verbose_name = 'Webinar Analytics'
        verbose_name_plural = 'Webinar Analytics'
        indexes = [
            models.Index(fields=['total_enrollments']),
            models.Index(fields=['total_attendees']),
            models.Index(fields=['average_rating']),
            models.Index(fields=['total_revenue']),
            models.Index(fields=['last_updated']),
        ]
    
    def __str__(self):
        return f"Analytics for {self.webinar.title}"
    
    def update_metrics(self):
        """Update analytics metrics with optimized queries"""
        from apps.enrollments.models import Enrollment
        
        enrollments = self.webinar.enrollments.all()
        self.total_enrollments = enrollments.count()
        self.total_attendees = enrollments.filter(status='attended').count()
        
        # Calculate average attendance duration
        attended_enrollments = enrollments.filter(status='attended')
        if attended_enrollments.exists():
            total_duration = sum(e.attendance_duration for e in attended_enrollments if e.attendance_duration)
            if total_duration > 0:
                self.average_attendance_duration = total_duration // attended_enrollments.count()
        
        # Calculate completion rate
        if self.total_enrollments > 0:
            self.completion_rate = (self.total_attendees / self.total_enrollments) * 100
        
        # Calculate average rating using database aggregation
        from django.db.models import Avg
        reviews = self.webinar.reviews.all()
        if reviews.exists():
            avg_rating = reviews.aggregate(avg_rating=Avg('rating'))['avg_rating']
            self.average_rating = avg_rating if avg_rating else 0.0
            self.total_reviews = reviews.count()
        
        self.save()
