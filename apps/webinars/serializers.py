# apps/webinars/serializers.py - CLEANED VERSION
import re
from rest_framework import serializers
from django.core.validators import URLValidator
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError as DjangoValidationError
from django.db.models import Avg, Count
from .models import (
    Category, Webinar, WebinarResource, WebinarSession, 
    WebinarReview, WebinarAnalytics
)
import logging
from apps.speakers.models import Speaker
from django.utils import timezone

logger = logging.getLogger(__name__)
User = get_user_model()

def get_avatar_full_url(request, avatar_field):
    if avatar_field and hasattr(avatar_field, 'url'):
        return request.build_absolute_uri(avatar_field.url) if request else avatar_field.url
    return None



class WebinarSpeakerSerializer(serializers.ModelSerializer):
    """Optimized Speaker serializer for webinar context - CLEANED"""
    
    full_name = serializers.CharField(read_only=True)
    email = serializers.CharField(source='user.email', read_only=True)
    avatar = serializers.SerializerMethodField()
    
    class Meta:
        model = Speaker
        fields = [
            'id', 'full_name', 'title', 'bio', 'company', 'email', 
            'avatar',
            'is_active', 'is_verified', 'total_sessions'
        ]
        read_only_fields = fields
     
    def get_avatar(self, obj):
        """Get full URL for avatar"""
        request = self.context.get('request')
        return get_avatar_full_url(request, obj.user.avatar) if obj.user else None
    


class WebinarUserSerializer(serializers.ModelSerializer):
    """Simple user serializer for webinar context"""
    
    full_name = serializers.CharField(read_only=True)
    
    class Meta:
        model = User
        fields = [
            'id', 'email', 'first_name', 'last_name', 'full_name', 
            'role', 'avatar', 'is_verified'
        ]
        read_only_fields = fields


class CategorySerializer(serializers.ModelSerializer):
    """Category serializer with webinar count"""
    
    webinar_count = serializers.IntegerField(read_only=True)
    
    class Meta:
        model = Category
        fields = [
            'id', 'name', 'description', 'color', 'icon', 
            'is_active', 'webinar_count', 'created_at', 'updated_at'
        ]
        read_only_fields = ('webinar_count', 'created_at', 'updated_at')

# apps/webinars/serializers.py

class BaseWebinarSerializer(serializers.ModelSerializer):
    """Base serializer with common webinar access control logic"""
    
    def _get_request_user(self):
        """Get user from request context consistently"""
        request = self.context.get('request')
        if request and hasattr(request, 'user'):
            return request.user if request.user.is_authenticated else None
        return None

    def _is_admin_user(self):
        """Check if current user is admin/staff"""
        user = self._get_request_user()
        return user and (user.is_staff or user.is_superuser)

    def _can_user_access_zoom(self, obj, user):
        """Centralized zoom access control logic"""
        if not user or not user.is_authenticated:
            return False
        
        # Admin users get full access
        if user.is_staff or user.is_superuser:
            return True
        
        # Speaker gets access to their own webinars
        if hasattr(obj, 'speaker') and obj.speaker.user == user:
            return True
        
        # Check enrollment status with payment verification
        if hasattr(obj, 'enrollments'):
            enrollment = obj.enrollments.filter(
                user=user, 
                status__in=['enrolled', 'attended', 'completed']
            ).first()
            
            if enrollment:
                # Additional payment verification if needed
                if hasattr(enrollment, 'payment_status') and enrollment.payment_status != 'completed':
                    return False
                return True
        
        return False
    
    def _get_conditional_zoom_url(self, obj):
        """Get zoom_url with conditional access control"""
        user = self._get_request_user()
        
        if not user:
            return "no access"
        
        if self._can_user_access_zoom(obj, user):
            # ✅ UPDATED: Check for zoom_meetings (plural) instead of zoom_meeting_rel
            if hasattr(obj, 'zoom_meetings') and obj.zoom_meetings.exists():
                meeting = obj.zoom_meetings.first()
                return meeting.join_url
            elif hasattr(obj, 'zoom_webinars') and obj.zoom_webinars.exists():
                webinar = obj.zoom_webinars.first()
                return webinar.join_url
            return obj.zoom_url or ""
        
        return "no access"
    
    def _get_conditional_zoom_access(self, obj):
        """Get zoom_access with conditional access control"""
        user = self._get_request_user()
        
        if not user:
            return {'can_join': False, 'message': 'Authentication required'}
        
        if not self._can_user_access_zoom(obj, user):
            return {'can_join': False, 'message': 'no access'}
        
        # ✅ UPDATED: Use zoom_meetings (plural)
        has_meeting = hasattr(obj, 'zoom_meetings') and obj.zoom_meetings.exists()
        has_webinar = hasattr(obj, 'zoom_webinars') and obj.zoom_webinars.exists()
        
        if not (has_meeting or has_webinar):
            return {
                'can_join': False,
                'can_start': False,
                'message': 'No Zoom meeting configured'
            }
        
        # Get the meeting/webinar
        zoom_obj = None
        if has_meeting:
            zoom_obj = obj.zoom_meetings.first()
        elif has_webinar:
            zoom_obj = obj.zoom_webinars.first()
        
        # Check access
        is_instructor = user and obj.speaker and user == obj.speaker.user
        is_admin = user and (user.is_staff or user.is_superuser)
        has_enrollment = False
        
        if user and user.is_authenticated:
            has_enrollment = obj.enrollments.filter(user=user).exists()
        
        can_join = has_enrollment or is_instructor or is_admin
        can_start = is_instructor or is_admin
        
        result = {
            'can_join': can_join,
            'can_start': can_start,
        }
        
        if can_join and zoom_obj:
            result['join_url'] = zoom_obj.join_url
        
        if can_start and zoom_obj:
            result['start_url'] = zoom_obj.start_url
        
        if can_join or can_start:
            result['message'] = 'Host access available' if can_start else 'Attendee access available'
        else:
            result['message'] = 'Enrollment required to access this webinar'
        
        return result
    
    def _get_recording_links(self, obj):
        """Get recording links with conditional access"""
        user = self._get_request_user()
        
        # Only users with webinar access can see recordings
        if not user or not self._can_user_access_zoom(obj, user):
            return []
        
        # ✅ UPDATED: Use zoom_meetings (plural)
        recordings = []
        
        # Get recordings from zoom_meetings
        if hasattr(obj, 'zoom_meetings'):
            for meeting in obj.zoom_meetings.all():
                if hasattr(meeting, 'recordings'):
                    recordings.extend(meeting.recordings.filter(
                        status='completed',
                        file_type='MP4'
                    ))
        
        # Get recordings from zoom_webinars
        if hasattr(obj, 'zoom_webinars'):
            for webinar in obj.zoom_webinars.all():
                if hasattr(webinar, 'recordings'):
                    recordings.extend(webinar.recordings.filter(
                        status='completed',
                        file_type='MP4'
                    ))
        
        return [{
            'id': rec.recording_id,
            'download_url': rec.download_url,
            'play_url': rec.play_url,
            'duration': rec.duration_minutes,
            'file_size': rec.file_size_mb,
        } for rec in recordings]
    
    def _get_user_enrollment_status(self, obj):
        """Get user's enrollment status"""
        user = self._get_request_user()
        if not user:
            return None
        return obj.get_user_enrollment_status(user)
    
    def _get_can_access_webinar(self, obj):
        """Check if user can access webinar"""
        user = self._get_request_user()
        if not user:
            return False
        return obj.can_user_access_webinar(user)
    
    def _get_cover_image_url(self, obj):
        """Get absolute URL for cover image"""
        if obj.cover_image:
            request = self.context.get('request')
            if request:
                return request.build_absolute_uri(obj.cover_image.url)
        return None

    def _get_user_access_types(self, obj):
        """Get list of access types user has purchased for this webinar"""
        user = self._get_request_user()
        if not user:
            return []
        
        # Check payment_webinars for this user
        from apps.payments.models import Payment, PaymentWebinar
        
        # Get completed payments for this user and webinar
        payment_webinars = PaymentWebinar.objects.filter(
            payment__user=user,
            payment__status='completed',
            webinar=obj
        ).select_related('payment')
        
        # Extract access types
        access_types = []
        for pw in payment_webinars:
            if pw.access_type:
                access_types.append(pw.access_type)
        
        return list(set(access_types))
    
    def _get_current_platform(self, obj):
        """
        Get current platform information from request
        ONLY for admin users
        """
        # ✅ ADDED: Admin-only check
        if not self._is_admin_user():
            return None
        
        request = self.context.get('request')
        
        if not request or not hasattr(request, 'platform') or not request.platform:
            return None
        
        platform = request.platform
        
        return {
            'platform_id': platform.platform_id,
            'platform_name': platform.name,
            'domain': platform.domain,
            'logo': platform.logo.url if platform.logo else None,
        }
    

    # def _get_applicable_prices_for_platform(self, obj):
    #     """
    #     Get applicable prices with platform-specific overrides applied
    #     Returns final prices user should see based on their platform
    #     """
    #     user = self._get_request_user()
        
    #     # Get base prices from webinar
    #     base_prices = obj.get_applicable_prices()
        
    #     # If no user or no platform, return base prices
    #     if not user or not hasattr(user, 'platform') or not user.platform:
    #         return base_prices
        
    #     # Get platform-specific pricing if exists
    #     try:
    #         platform_price = obj.platform_prices.get(
    #             platform=user.platform,
    #             is_active=True
    #         )
            
    #         # Merge platform pricing with base prices
    #         if platform_price and platform_price.pricing_data:
    #             # Start with base prices
    #             final_prices = base_prices.copy()
                
    #             # Override with platform-specific prices
    #             final_prices.update(platform_price.pricing_data)
                
    #             return final_prices
                
    #     except Exception as e:
    #         # If no platform pricing found, return base prices
    #         pass
        
    #     return base_prices
    def _get_applicable_prices_for_platform(self, obj):
        """
        Get applicable prices with platform-specific overrides applied
        Returns final prices user should see based on their platform
        """
        request = self.context.get('request')
        
        # Get base prices from webinar
        base_prices = obj.get_applicable_prices()
        
        # ✅ CHANGED: Get platform from request (set by middleware)
        if not request or not hasattr(request, 'platform') or not request.platform:
            logger.warning("No platform found in request, using base prices")
            return base_prices
        
        platform = request.platform
        
        # Get platform-specific pricing if exists
        try:
            from apps.webinars.models import WebinarPlatformPrice
            
            platform_price = WebinarPlatformPrice.objects.select_related('platform').get(
                webinar=obj,
                platform=platform,
                is_active=True
            )
            
            if platform_price and platform_price.pricing_data:
                pricing_data = platform_price.pricing_data
                
                # Format and return platform-specific prices
                result = {}
                
                # Map pricing_data keys to applicable_prices format
                price_mapping = {
                    'live_single_price': 'live_single',
                    'live_multi_price': 'live_multi',
                    'recorded_single_price': 'recorded_single',
                    'recorded_multi_price': 'recorded_multi',
                    'combo_single_price': 'combo_single',
                    'combo_multi_price': 'combo_multi',
                }
                
                # Only include prices that are actually set (not None/null)
                for data_key, price_key in price_mapping.items():
                    value = pricing_data.get(data_key)
                    if value is not None and value != '':
                        result[price_key] = str(value)
                
                # Fill in missing prices with base prices
                for key, value in base_prices.items():
                    if key not in result:
                        result[key] = value
                
                # logger.info(f"✅ Platform pricing for {platform.name}: {result}")
                return result
                
        except Exception as e:
            logger.warning(f"No platform pricing found: {str(e)}")
        
        return base_prices


class WebinarListSerializer(BaseWebinarSerializer):
    """Optimized webinar list serializer with conditional access control"""
    
    # Related objects (use select_related in views)
    speaker = WebinarSpeakerSerializer(read_only=True)
    category = CategorySerializer(read_only=True)
    
    # Model properties (no database queries)
    enrolled_count = serializers.ReadOnlyField()
    available_spots = serializers.ReadOnlyField()
    is_full = serializers.ReadOnlyField()
    has_unlimited_capacity = serializers.ReadOnlyField()
    is_upcoming = serializers.ReadOnlyField()
    is_live_now = serializers.ReadOnlyField()
    is_completed = serializers.ReadOnlyField()
    main_price = serializers.ReadOnlyField()
    is_free = serializers.ReadOnlyField()
    display_status = serializers.ReadOnlyField()
    has_recording = serializers.ReadOnlyField()
    # applicable_prices = serializers.ReadOnlyField(source='get_applicable_prices')
    applicable_prices = serializers.SerializerMethodField()
    # Conditional access fields
    zoom_url = serializers.SerializerMethodField()
    zoom_access = serializers.SerializerMethodField()
    user_enrollment_status = serializers.SerializerMethodField()
    can_access_webinar = serializers.SerializerMethodField()
    cover_image_url = serializers.SerializerMethodField()
    user_access_types = serializers.SerializerMethodField()
    recording_links = serializers.SerializerMethodField()
    class Meta:
        model = Webinar
        fields = [
            # Basic info
            'id', 'webinar_id', 'title', 'description', 'speaker', 'category',
            'webinar_type', 'scheduled_date', 'duration', 'timezone', 'skill_level', 
            'status', 'display_status',
            
            # Enrollment and capacity
            'enrolled_count', 'available_spots', 'is_full',
            'has_enrollment_limit', 'max_attendees', 'has_unlimited_capacity',
            
            # Status properties
            'is_upcoming', 'is_live_now', 'is_completed',
            
            # Pricing
            'main_price', 'is_free', 'applicable_prices', 
            
            # Recording and access
           'user_access_types',   'has_recording', 'zoom_url', 'zoom_access',
            'recording_links', 
            # Media
            'cover_image', 'cover_image_url',
            
            # User-specific access
            'user_enrollment_status', 'can_access_webinar',
            
            # Timestamps
            'created_at', 'updated_at'
        ]
    def get_applicable_prices(self, obj):
        """Get platform-specific prices automatically"""
        return self._get_applicable_prices_for_platform(obj)
    # Optimized conditional access methods
    def get_zoom_url(self, obj):
        return self._get_conditional_zoom_url(obj)
    def get_user_access_types(self, obj):
        return self._get_user_access_types(obj)
    def get_zoom_access(self, obj):
        return self._get_conditional_zoom_access(obj)
    
    def get_user_enrollment_status(self, obj):
        return self._get_user_enrollment_status(obj)
    
    def get_can_access_webinar(self, obj):
        return self._get_can_access_webinar(obj)
    
    def get_cover_image_url(self, obj):
        return self._get_cover_image_url(obj)
    def get_recording_links(self, obj):
        """Get recording links based on user access"""
        user = self._get_request_user()
        
        # Only users with webinar access can see recordings
        if not user or not obj.can_user_access_webinar(user):
            return []
        
        return obj.recording_links

class WebinarPlatformPriceSerializer(serializers.ModelSerializer):
    """Platform-specific pricing serializer"""
    platform_id = serializers.CharField(source='platform.platform_id', read_only=True)
    platform_name = serializers.CharField(source='platform.name', read_only=True)
    
    class Meta:
        from apps.webinars.models import WebinarPlatformPrice
        model = WebinarPlatformPrice
        fields = [
            'id',
            'platform_id',
            'platform_name',
            'pricing_data',
            'discount_percentage',
            'is_active',
            'created_at',
            'updated_at'
        ]
        read_only_fields = ['created_at', 'updated_at']


class WebinarDetailSerializer(BaseWebinarSerializer):
    """Optimized webinar detail serializer with full conditional access control"""
    
    # Related objects (use select_related/prefetch_related in views)
    speaker = WebinarSpeakerSerializer(read_only=True)
    category = CategorySerializer(read_only=True)
    
    # Model properties (no database queries)
    enrolled_count = serializers.ReadOnlyField()
    has_unlimited_capacity = serializers.ReadOnlyField()
    is_full = serializers.ReadOnlyField()
    is_upcoming = serializers.ReadOnlyField()
    is_live_now = serializers.ReadOnlyField()
    is_completed = serializers.ReadOnlyField()
    end_time = serializers.ReadOnlyField()
    main_price = serializers.ReadOnlyField()
    is_free = serializers.ReadOnlyField()
    has_early_bird_pricing = serializers.ReadOnlyField()
    display_status = serializers.ReadOnlyField()
    has_recording = serializers.ReadOnlyField()
    # platform_prices = WebinarPlatformPriceSerializer(many=True, read_only=True)
    
    # applicable_prices = serializers.ReadOnlyField(source='get_applicable_prices')
    applicable_prices = serializers.SerializerMethodField()
    platform_prices = serializers.SerializerMethodField()
    current_platform = serializers.SerializerMethodField() 
    # Conditional access fields
    zoom_url = serializers.SerializerMethodField()
    zoom_access = serializers.SerializerMethodField()
    user_enrollment_status = serializers.SerializerMethodField()
    can_access_webinar = serializers.SerializerMethodField()
    recording_links = serializers.SerializerMethodField()
    cover_image_url = serializers.SerializerMethodField()
    available_spots = serializers.SerializerMethodField()
    user_access_types = serializers.SerializerMethodField()
   
    class Meta:
        model = Webinar
        fields = [
            # Basic info
            'id', 'webinar_id', 'title', 'description', 'speaker', 'category',
            'skill_level', 'status', 'display_status', 'webinar_type',
            
            # Scheduling
            'scheduled_date', 'duration', 'timezone', 'end_time',
            
            # Capacity and enrollment
            'has_enrollment_limit', 'max_attendees', 'enrolled_count', 
            'available_spots', 'is_full', 'has_unlimited_capacity',
            
            # Pricing
            'main_price', 'is_free', 'has_early_bird_pricing', 'applicable_prices',
              # ✅ ADD: Platform pricing
            'platform_prices',
             'current_platform',
            
            # Recording and access
            'user_access_types', 'has_recording', 'zoom_url', 'zoom_access', 'recording_links',
            
            # Media
            'cover_image', 'cover_image_url',
            
            # User-specific access
            'user_enrollment_status', 'can_access_webinar',
            
            # Status properties
            'is_upcoming', 'is_live_now', 'is_completed',
            
            # Timestamps
            'created_at', 'updated_at'
        ]
    def get_applicable_prices(self, obj):
        """Get platform-specific prices automatically"""
        user = self._get_request_user()
        
        # Admin sees original prices
        if user and (user.is_staff or user.is_superuser):
            return obj.get_applicable_prices()
        
        # Regular users see platform-adjusted prices
        return self._get_applicable_prices_for_platform(obj)
    def get_current_platform(self, obj):
        """
        Get current platform from request
        ONLY shown to admin users
        """
        return self._get_current_platform(obj) 

    
    def get_platform_prices(self, obj):
        """
        Get all platform pricing configurations
        - Admin: Show all platform prices with current_platform flag
        - Regular users: Hide (return None)
        """
        if not self._is_admin_user():
            return None  # ✅ Hide for regular users
        
        request = self.context.get('request')
        
        # Get current platform from request
        current_platform_id = None
        if request and hasattr(request, 'platform') and request.platform:
            current_platform_id = request.platform.platform_id
        
        try:
            from apps.webinars.models import WebinarPlatformPrice
            
            platform_prices = obj.platform_prices.filter(is_active=True).select_related('platform')
            
            result = []
            for pp in platform_prices:
                price_data = {
                    'id': pp.id,
                    'platform_id': pp.platform.platform_id,
                    'platform_name': pp.platform.name,
                    'pricing_data': pp.pricing_data,
                    'discount_percentage': str(pp.discount_percentage),
                    'is_active': pp.is_active,
                    'created_at': pp.created_at,
                    'updated_at': pp.updated_at,
                }
                
                # ✅ Mark current platform
                if current_platform_id and pp.platform.platform_id == current_platform_id:
                    price_data['current_platform'] = True
                else:
                    price_data['current_platform'] = False
                
                result.append(price_data)
            
            return result
            
        except Exception as e:
            logger.error(f"Error getting platform prices: {e}")
            return []

    # ✅ NEW: Conditional platform_prices (only admin)
    # def get_platform_prices(self, obj):
    #     """Only show platform_prices to admin/staff users"""
    #     user = self._get_request_user()
        
    #     # Only show to admin/staff
    #     if user and (user.is_staff or user.is_superuser):
    #         return WebinarPlatformPriceSerializer(
    #             obj.platform_prices.filter(is_active=True), 
    #             many=True
    #         ).data
        
    #     return None 
        
    # def get_applicable_prices(self, obj):
    #     """Get platform-specific prices automatically"""
    #     return self._get_applicable_prices_for_platform(obj)

    
    def get_applicable_prices(self, obj):
        """
        Get applicable prices based on user role
        - Admin: Show BASE/DEFAULT prices (not platform-specific)
        - Regular users: Show PLATFORM-SPECIFIC prices
        """
        # ✅ Admin sees BASE prices (for editing/reference)
        if self._is_admin_user():
            base_prices = obj.get_applicable_prices()
            logger.info(f"🔑 Admin view - showing base prices: {base_prices}")
            return base_prices
        
        # ✅ Regular users see PLATFORM-SPECIFIC prices
        platform_prices = self._get_applicable_prices_for_platform(obj)
        logger.info(f"👤 User view - showing platform prices: {platform_prices}")
        return platform_prices
    
    def to_representation(self, instance):
        """
        Customize representation based on user role
        Remove platform-specific fields for non-admin users
        """
        representation = super().to_representation(instance)
        
        # ✅ Clean up response for regular users
        if not self._is_admin_user():
            # Remove fields that regular users don't need
            representation.pop('current_platform', None)
            representation.pop('platform_prices', None)
        
        return representation
    
    def get_user_access_types(self, obj):
        return self._get_user_access_types(obj)
    # Optimized conditional access methods
    def get_zoom_url(self, obj):
        return self._get_conditional_zoom_url(obj)
    
    def get_zoom_access(self, obj):
        return self._get_conditional_zoom_access(obj)
    
    def get_user_enrollment_status(self, obj):
        return self._get_user_enrollment_status(obj)
    
    def get_can_access_webinar(self, obj):
        return self._get_can_access_webinar(obj)
    
    def get_recording_links(self, obj):
        """Get recording links based on user access"""
        user = self._get_request_user()
        
        # Only users with webinar access can see recordings
        if not user or not obj.can_user_access_webinar(user):
            return []
        
        return obj.recording_links
    
    def get_available_spots(self, obj):
        """Handle infinity values for JSON serialization"""
        spots = obj.available_spots
        if spots is None or spots == float('inf'):
            return None
        return spots
    
    def get_cover_image_url(self, obj):
        return self._get_cover_image_url(obj)


class WebinarCreateUpdateSerializer(serializers.ModelSerializer):
    """Enhanced webinar serializer with conditional validation and pricing"""
    
    # Read-only fields
    webinar_id = serializers.CharField(read_only=True)
    status = serializers.CharField(read_only=True) 
    display_status = serializers.CharField(read_only=True)
    applicable_prices = serializers.ReadOnlyField(source='get_applicable_prices')
    has_recording = serializers.BooleanField(read_only=True)
    
    # Speaker relationship with optimized queryset - CLEANED
    speaker = serializers.PrimaryKeyRelatedField(
        queryset=Speaker.objects.select_related('user').filter(
            is_active=True, 
            user__is_active=True, 
            user__role='instructor'
        ),
        required=True
    )
    description = serializers.CharField(
        required=True,
        allow_blank=False,
        help_text="HTML content for the webinar description, areas covered, who will benefit, etc."
    )

    class Meta:
        model = Webinar
        fields = [
            # Auto-generated fields
            'webinar_id', 'status', 'display_status', 'applicable_prices', 'has_recording',
            
            # Basic Info
            'title', 'description', 'category', 'skill_level', 'speaker',
            
            # Webinar type
            'webinar_type',
            
            # Conditional Scheduling (only for live)
            'scheduled_date', 'duration', 'timezone',
            
            # Zoom URL (only for recorded)
            'zoom_url',
            
            # Pricing and enrollment
            'has_enrollment_limit', 'max_attendees', 'pricing_data',
            
            # Media
            'cover_image',
            
            # Settings (only for live)
            'zoom_preferences', 'auto_convert_to_recorded'
        ]
    
    def validate_description(self, value):
        """Validate HTML content field"""
        if not value or not value.strip():
            raise serializers.ValidationError("Content is required and cannot be empty")
        
        # Basic HTML validation - check for minimum content length
        # Remove HTML tags for length check
        import re
        text_content = re.sub(r'<[^>]+>', '', value).strip()
        if len(text_content) < 50:  # Minimum 50 characters of actual text content
            raise serializers.ValidationError("Content must contain at least 50 characters of text")
        
        return value
        
    def validate_zoom_preferences(self, value):
        """Validate zoom preferences structure"""
        if not isinstance(value, dict):
            return {}
        
        allowed_fields = [
            'recordingPreference', 'interactionLevel', 'waitingRoom',
            'enableChat', 'enableQA', 'enablePolls', 'allowScreenShare', 'muteOnEntry'
        ]
        
        return {k: v for k, v in value.items() if k in allowed_fields}
    
    # def validate_scheduled_date(self, value):
    #     """Validate scheduled date is in future"""
    #     if value:
    #         from django.utils import timezone
    #         if value <= timezone.now():
    #             raise serializers.ValidationError("Scheduled date must be in the future")
    #     return value
    def validate_scheduled_date(self, value):
        """Validate scheduled date is in the future, considering webinar timezone"""
        if value:
            from django.utils import timezone
            import pytz

            # Get webinar timezone from initial data, default to UTC
            webinar_timezone = self.initial_data.get('timezone', 'UTC')
            try:
                tz = pytz.timezone(webinar_timezone)
            except pytz.UnknownTimeZoneError:
                tz = pytz.UTC

            # Get current time in webinar timezone
            now_in_tz = timezone.now().astimezone(tz)

            # Ensure value is timezone-aware in webinar's timezone
            if timezone.is_naive(value):
                value = tz.localize(value)
            else:
                value = value.astimezone(tz)

            if value <= now_in_tz:
                raise serializers.ValidationError(f"Scheduled date and time must be in the future according to {webinar_timezone} timezone")
        return value

    
    def validate_max_attendees(self, value):
        """Validate max attendees is positive"""
        if value is not None and value <= 0:
            raise serializers.ValidationError("Maximum attendees must be a positive number")
        return value
    
    # def validate_pricing_data(self, value):
    #     """Conditional pricing validation based on webinar type"""
    #     if not isinstance(value, dict):
    #         return {}
        
    #     webinar_type = self.initial_data.get('webinar_type', 'live')
        
    #     # Validate price values are numeric and non-negative
    #     price_fields = [
    #         'live_single_price', 'live_multi_price', 
    #         'recorded_single_price', 'recorded_multi_price',
    #         'combo_single_price', 'combo_multi_price',
    #         'early_bird_single_price', 'early_bird_multi_price'
    #     ]
        
    #     for field in price_fields:
    #         if field in value and value[field] is not None:
    #             try:
    #                 price_value = float(value[field])
    #                 if price_value < 0:
    #                     raise serializers.ValidationError(f"{field} cannot be negative")
    #             except (ValueError, TypeError):
    #                 raise serializers.ValidationError(f"{field} must be a valid number")
        
    #     # Conditional pricing validation based on webinar type
    #     if webinar_type == 'live':
    #         # Live webinars: require live pricing
    #         required_fields = ['live_single_price', 'live_multi_price']
    #         has_required_price = any(value.get(field) for field in required_fields)
            
    #         if not has_required_price:
    #             raise serializers.ValidationError(
    #                 "Live webinars require at least one live pricing option"
    #             )
            
    #         # Keep only allowed pricing for live webinars
    #         allowed_prefixes = ['live_', 'combo_', 'early_bird_']
    #         return {k: v for k, v in value.items() 
    #                if any(k.startswith(prefix) for prefix in allowed_prefixes)}
            
    #     elif webinar_type == 'recorded':
    #         # Recorded webinars: require recorded pricing only
    #         required_fields = ['recorded_single_price', 'recorded_multi_price']
    #         has_required_price = any(value.get(field) for field in required_fields)
            
    #         if not has_required_price:
    #             raise serializers.ValidationError(
    #                 "Recorded webinars require at least one recorded pricing option"
    #             )
            
    #         # Keep only recorded and early bird pricing
    #         allowed_prefixes = ['recorded_', 'early_bird_']
    #         return {k: v for k, v in value.items() 
    #                if any(k.startswith(prefix) for prefix in allowed_prefixes)}
        
    #     return value

    def validate_pricing_data(self, value):
        """Conditional pricing validation based on webinar type"""
        if not isinstance(value, dict):
            return {}
        
        webinar_type = self.initial_data.get('webinar_type', 'live')
        
        # Validate price values are numeric and non-negative
        price_fields = [
            'live_single_price', 'live_multi_price', 
            'recorded_single_price', 'recorded_multi_price',
            'combo_single_price', 'combo_multi_price',
            'early_bird_single_price', 'early_bird_multi_price'
        ]
        
        for field in price_fields:
            if field in value and value[field] is not None:
                try:
                    price_value = float(value[field])
                    if price_value < 0:
                        raise serializers.ValidationError(f"{field} cannot be negative")
                except (ValueError, TypeError):
                    raise serializers.ValidationError(f"{field} must be a valid number")
        
        # Conditional pricing validation based on webinar type
        if webinar_type == 'live':
            # Live webinars: require live pricing
            required_fields = ['live_single_price', 'live_multi_price']
            has_required_price = any(value.get(field) for field in required_fields)
            
            if not has_required_price:
                raise serializers.ValidationError(
                    "Live webinars require at least one live pricing option"
                )
            
            # Keep live, combo, recorded, and early_bird pricing for live webinars
            # Recorded pricing indicates recording will be available in future
            allowed_prefixes = ['live_', 'combo_', 'recorded_', 'early_bird_']
            return {k: v for k, v in value.items() 
                if any(k.startswith(prefix) for prefix in allowed_prefixes)}
            
        elif webinar_type == 'recorded':
            # Recorded webinars: require recorded pricing only
            required_fields = ['recorded_single_price', 'recorded_multi_price']
            has_required_price = any(value.get(field) for field in required_fields)
            
            if not has_required_price:
                raise serializers.ValidationError(
                    "Recorded webinars require at least one recorded pricing option"
                )
            
            # Keep only recorded and early bird pricing
            allowed_prefixes = ['recorded_', 'early_bird_']
            return {k: v for k, v in value.items() 
                if any(k.startswith(prefix) for prefix in allowed_prefixes)}
        
        return value

    
    # def validate(self, attrs):
    #     """Enhanced cross-field validation based on webinar type"""
    #     webinar_type = attrs.get('webinar_type', 'live')
        
    #     if webinar_type == 'live':
    #         # Live webinar validation
    #         if not attrs.get('scheduled_date'):
    #             raise serializers.ValidationError({
    #                 'scheduled_date': 'Scheduled date is required for live webinars'
    #             })
    #         if not attrs.get('duration'):
    #             raise serializers.ValidationError({
    #                 'duration': 'Duration is required for live webinars'
    #             })
            
    #         # Validate future scheduling
    #         from django.utils import timezone
    #         if attrs.get('scheduled_date') and attrs['scheduled_date'] <= timezone.now():
    #             raise serializers.ValidationError({
    #                 'scheduled_date': 'Scheduled date must be in the future'
    #             })
            
    #         # Clear zoom_url for live webinars
    #         attrs['zoom_url'] = ''
                
    #     elif webinar_type == 'recorded':
    #         # Recorded webinar validation
    #         if not attrs.get('zoom_url'):
    #             raise serializers.ValidationError({
    #                 'zoom_url': 'Zoom URL is required for recorded webinars'
    #             })
            
    #         # Validate Zoom URL format
    #         zoom_url = attrs.get('zoom_url', '')
    #         if zoom_url and not self._is_valid_zoom_url(zoom_url):
    #             raise serializers.ValidationError({
    #                 'zoom_url': 'Please enter a valid Zoom URL'
    #             })
            
    #         # Clear scheduling fields for recorded webinars
    #         attrs.update({
    #             'scheduled_date': None,
    #             'duration': None,
    #             'timezone': 'UTC',
    #             'zoom_preferences': {},
    #             'auto_convert_to_recorded': False
    #         })
        
    #     # Enrollment validation
    #     has_enrollment_limit = attrs.get('has_enrollment_limit', False)
    #     max_attendees = attrs.get('max_attendees')
        
    #     if has_enrollment_limit:
    #         if not max_attendees or max_attendees <= 0:
    #             raise serializers.ValidationError({
    #                 'max_attendees': 'Maximum attendees is required when enrollment limit is enabled'
    #             })
    #     else:
    #         attrs['max_attendees'] = None
        
    #     return attrs
    def validate(self, attrs):
        """Enhanced cross-field validation based on webinar type"""
        webinar_type = attrs.get('webinar_type', 'live')
        
        if webinar_type == 'live':
            # Live webinar validation
            if not attrs.get('scheduled_date'):
                raise serializers.ValidationError({
                    'scheduled_date': 'Scheduled date is required for live webinars'
                })
            if not attrs.get('duration'):
                raise serializers.ValidationError({
                    'duration': 'Duration is required for live webinars'
                })
            
            # Validate future scheduling in the webinar's timezone
            scheduled_date = attrs.get('scheduled_date')
            webinar_timezone = attrs.get('timezone', 'UTC')
            
            if scheduled_date:
                import pytz
                
                # Get the webinar's timezone
                try:
                    tz = pytz.timezone(webinar_timezone)
                except pytz.UnknownTimeZoneError:
                    tz = pytz.UTC
                
                # Get current time in the webinar's timezone
                now_in_webinar_tz = timezone.now().astimezone(tz)
                
                # Convert scheduled_date to the webinar's timezone if needed
                if timezone.is_aware(scheduled_date):
                    scheduled_date_in_tz = scheduled_date.astimezone(tz)
                else:
                    scheduled_date_in_tz = tz.localize(scheduled_date)
                
                # Compare in the webinar's timezone
                if scheduled_date_in_tz <= now_in_webinar_tz:
                    raise serializers.ValidationError({
                        'scheduled_date': f'Scheduled date and time must be in the future (Timezone: {webinar_timezone})'
                    })
            
            # Clear zoom_url for live webinars
            attrs['zoom_url'] = ''
                
        elif webinar_type == 'recorded':
            # Recorded webinar validation
            if not attrs.get('zoom_url'):
                raise serializers.ValidationError({
                    'zoom_url': 'Zoom URL is required for recorded webinars'
                })
            
            # Validate Zoom URL format
            zoom_url = attrs.get('zoom_url', '')
            if zoom_url and not self._is_valid_zoom_url(zoom_url):
                raise serializers.ValidationError({
                    'zoom_url': 'Please enter a valid Zoom URL'
                })
            
            # Clear scheduling fields for recorded webinars
            attrs.update({
                'scheduled_date': None,
                'duration': None,
                'timezone': 'UTC',
                'zoom_preferences': {},
                'auto_convert_to_recorded': False
            })
        
        # Enrollment validation
        has_enrollment_limit = attrs.get('has_enrollment_limit', False)
        max_attendees = attrs.get('max_attendees')
        
        if has_enrollment_limit:
            if not max_attendees or max_attendees <= 0:
                raise serializers.ValidationError({
                    'max_attendees': 'Maximum attendees is required when enrollment limit is enabled'
                })
        else:
            attrs['max_attendees'] = None
        
        return attrs

    def _is_valid_zoom_url(self, url):
        """Validate Zoom URL format"""
        zoom_patterns = [
            r'^https://.*\.?zoom\.us/j/\d+',              # Meeting join links
            r'^https://.*\.?zoom\.us/w/\d+',              # Webinar join links  
            r'^https://.*\.?zoom\.us/meeting/\d+',        # Meeting links
            r'^https://.*\.?zoom\.us/webinar/register/',  # Webinar registration
            r'^https://.*\.?zoom\.us/s/\d+',              # Personal meeting room
            r'^https://.*\.?zoom\.us/rec/'                # Cloud recordings
        ]
        return any(re.match(pattern, url) for pattern in zoom_patterns)


# Keep all the remaining serializers as they are since they don't reference Speaker fields directly
class WebinarResourceSerializer(serializers.ModelSerializer):
    """Webinar resource serializer with optimized file URL generation"""
    
    file_url = serializers.SerializerMethodField()
    
    class Meta:
        model = WebinarResource
        fields = [
            'id', 'webinar', 'title', 'description', 'resource_type', 
            'file', 'file_url', 'url', 'is_public', 'is_downloadable', 
            'file_size', 'uploaded_at'
        ]
        read_only_fields = ('uploaded_at', 'file_size')
    
    def get_file_url(self, obj):
        """Get absolute URL for file"""
        if obj.file:
            request = self.context.get('request')
            if request:
                return request.build_absolute_uri(obj.file.url)
        return None



class WebinarSessionSerializer(serializers.ModelSerializer):
    """Webinar session serializer"""
    
    class Meta:
        model = WebinarSession
        fields = [
            'id', 'webinar', 'title', 'description', 'session_number',
            'scheduled_date', 'duration', 'zoom_meeting_id', 'zoom_join_url',
            'recording_url', 'is_completed', 'created_at'
        ]
        read_only_fields = ('created_at',)


class WebinarReviewSerializer(serializers.ModelSerializer):
    """Webinar review serializer with user information"""
    
    user = WebinarUserSerializer(read_only=True)
    user_name = serializers.CharField(source='user.full_name', read_only=True)
    
    class Meta:
        model = WebinarReview
        fields = [
            'id', 'webinar', 'user', 'user_name', 'rating', 'review_text',
            'content_quality', 'instructor_performance', 'technical_quality',
            'would_recommend', 'is_verified_purchase', 'created_at', 'updated_at'
        ]
        read_only_fields = ('user', 'created_at', 'updated_at', 'is_verified_purchase')


class WebinarAnalyticsSerializer(serializers.ModelSerializer):
    """Webinar analytics serializer"""
    
    class Meta:
        model = WebinarAnalytics
        fields = [
            'webinar', 'total_enrollments', 'total_attendees', 'peak_concurrent_attendees',
            'average_attendance_duration', 'total_questions_asked', 'total_chat_messages',
            'average_rating', 'total_reviews', 'total_revenue', 'completion_rate',
            'last_updated'
        ]
        read_only_fields = ('last_updated',)


# Stats and utility serializers
class WebinarStatsSerializer(serializers.Serializer):
    """Webinar statistics serializer"""
    
    total_webinars = serializers.IntegerField()
    live_webinars = serializers.IntegerField()
    recorded_webinars = serializers.IntegerField()
    upcoming_webinars = serializers.IntegerField()
    currently_live = serializers.IntegerField()
    completed_webinars = serializers.IntegerField()
    available_webinars = serializers.IntegerField()
    with_recordings = serializers.IntegerField()
    total_enrollments = serializers.IntegerField()
    total_revenue = serializers.DecimalField(max_digits=10, decimal_places=2)
    average_rating = serializers.DecimalField(max_digits=3, decimal_places=2, allow_null=True)
    popular_categories = serializers.ListField(child=serializers.DictField(), allow_empty=True)
    zoom_integrated_webinars = serializers.IntegerField()
    auto_converted_webinars = serializers.IntegerField()


class InstructorWebinarStatsSerializer(serializers.Serializer):
    """Instructor webinar statistics serializer"""
    
    total_webinars = serializers.IntegerField()
    live_webinars = serializers.IntegerField()
    recorded_webinars = serializers.IntegerField()
    total_students = serializers.IntegerField()
    total_revenue = serializers.DecimalField(max_digits=10, decimal_places=2)
    average_rating = serializers.DecimalField(max_digits=3, decimal_places=2, allow_null=True)
    upcoming_webinars = serializers.IntegerField()
    completed_webinars = serializers.IntegerField()
    available_webinars = serializers.IntegerField()
    with_recordings = serializers.IntegerField()


class WebinarEnrollmentSerializer(serializers.Serializer):
    """Webinar enrollment data serializer"""
    
    webinar_id = serializers.CharField()
    user_id = serializers.IntegerField()
    enrollment_type = serializers.ChoiceField(choices=[
        ('live', 'Live Only'),
        ('recorded', 'Recorded Only'),
        ('combo', 'Live + Recorded')
    ])
    payment_method = serializers.ChoiceField(choices=[
        ('free', 'Free'),
        ('stripe', 'Credit Card'),
        ('paypal', 'PayPal'),
        ('bank_transfer', 'Bank Transfer')
    ])
    coupon_code = serializers.CharField(required=False, allow_blank=True)


class WebinarSearchSerializer(serializers.Serializer):
    """Webinar search parameters serializer"""
    
    query = serializers.CharField(required=False, allow_blank=True)
    category = serializers.CharField(required=False, allow_blank=True)
    webinar_type = serializers.ChoiceField(
        choices=Webinar.WEBINAR_TYPE_CHOICES,
        required=False,
        allow_blank=True
    )
    skill_level = serializers.ChoiceField(
        choices=Webinar.DIFFICULTY_CHOICES,
        required=False,
        allow_blank=True
    )
    price_min = serializers.DecimalField(max_digits=10, decimal_places=2, required=False)
    price_max = serializers.DecimalField(max_digits=10, decimal_places=2, required=False)
    date_from = serializers.DateTimeField(required=False)
    date_to = serializers.DateTimeField(required=False)
    instructor = serializers.CharField(required=False, allow_blank=True)
    status = serializers.ChoiceField(
        choices=Webinar.STATUS_CHOICES,
        required=False,
        allow_blank=True
    )
    is_free = serializers.BooleanField(required=False)
    has_recording = serializers.BooleanField(required=False)
    sort_by = serializers.ChoiceField(
        choices=[
            ('scheduled_date', 'Date'),
            ('title', 'Title'),
            ('main_price', 'Price'),
            ('enrolled_count', 'Popularity'),
            ('created_at', 'Latest')
        ],
        default='created_at'
    )
    sort_order = serializers.ChoiceField(
        choices=[('asc', 'Ascending'), ('desc', 'Descending')],
        default='desc'
    )


class WebinarBulkActionSerializer(serializers.Serializer):
    """Bulk actions on webinars serializer"""
    
    webinar_ids = serializers.ListField(
        child=serializers.IntegerField(),
        min_length=1,
        max_length=100
    )
    action = serializers.ChoiceField(choices=[
        ('cancel', 'Cancel'),
        ('reschedule', 'Reschedule'),
        ('duplicate', 'Duplicate'),
        ('delete', 'Delete'),
        ('change_status', 'Change Status'),
        ('sync_recordings', 'Sync Recordings'),
    ])
    new_date = serializers.DateTimeField(required=False)
    new_status = serializers.ChoiceField(
        choices=Webinar.STATUS_CHOICES,
        required=False
    )
    copy_settings = serializers.BooleanField(default=True)


class WebinarReportSerializer(serializers.Serializer):
    """Webinar reports serializer"""
    
    date_from = serializers.DateField()
    date_to = serializers.DateField()
    instructor = serializers.PrimaryKeyRelatedField(
        queryset=User.objects.filter(role='instructor'),
        required=False
    )
    category = serializers.PrimaryKeyRelatedField(
        queryset=Category.objects.all(),
        required=False
    )
    webinar_type = serializers.ChoiceField(
        choices=Webinar.WEBINAR_TYPE_CHOICES,
        required=False
    )
    include_cancelled = serializers.BooleanField(default=False)
    group_by = serializers.ChoiceField(
        choices=[
            ('day', 'Daily'),
            ('week', 'Weekly'),
            ('month', 'Monthly'),
            ('instructor', 'By Instructor'),
            ('category', 'By Category'),
            ('webinar_type', 'By Webinar Type'),
        ],
        default='month'
    )
    metrics = serializers.ListField(
        child=serializers.ChoiceField(choices=[
            ('enrollments', 'Enrollments'),
            ('attendance', 'Attendance'),
            ('revenue', 'Revenue'),
            ('ratings', 'Ratings'),
            ('completion', 'Completion Rate'),
            ('recordings', 'Recordings Available'),
        ]),
        default=['enrollments', 'attendance', 'revenue']
    )
