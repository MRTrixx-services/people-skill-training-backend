from rest_framework import serializers
from django.contrib.auth import get_user_model
from django.utils import timezone
from .models import (
    ZoomCredentials, 
    ZoomMeeting, 
    ZoomWebinar, 
    ZoomRecording,
    ZoomWebhookEvent,
    ZoomIntegrationLog
)

User = get_user_model()

class ZoomMeetingSearchResultSerializer(serializers.Serializer):
    """Serializer for Zoom meeting search results"""
    
    id = serializers.CharField()
    topic = serializers.CharField()
    start_time = serializers.DateTimeField()
    duration = serializers.IntegerField()
    timezone = serializers.CharField()
    join_url = serializers.URLField()
    start_url = serializers.URLField(required=False)
    host_email = serializers.EmailField(required=False)
    host_name = serializers.CharField(required=False)
    type = serializers.ChoiceField(choices=['meeting', 'webinar'])
    match_score = serializers.IntegerField()
    match_reasons = serializers.ListField(child=serializers.CharField())
    time_diff_hours = serializers.FloatField()
    agenda = serializers.CharField(required=False, allow_blank=True)
    scheduled_date_formatted = serializers.CharField(required=False)


# NEW: Serializer for search request
class SearchZoomMeetingsSerializer(serializers.Serializer):
    """Serializer for meeting search request parameters"""
    
    start_date = serializers.DateTimeField(
        required=True,
        help_text="Scheduled date to search around (ISO format)"
    )
    topic = serializers.CharField(
        required=False,
        allow_blank=True,
        max_length=300,
        help_text="Topic/title to match (partial match)"
    )
    duration = serializers.IntegerField(
        required=False,
        min_value=1,
        max_value=1440,
        help_text="Duration in minutes"
    )
    days_range = serializers.IntegerField(
        required=False,
        default=3,
        min_value=1,
        max_value=30,
        help_text="Number of days before/after to search"
    )
    
    def validate_start_date(self, value):
        """Validate start date format"""
        if not value:
            raise serializers.ValidationError("start_date is required")
        return value


# NEW: Serializer for linking existing meeting
class LinkExistingZoomMeetingSerializer(serializers.Serializer):
    """Serializer for linking an existing Zoom meeting to a webinar"""
    
    webinar_id = serializers.IntegerField(
        required=True,
        help_text="ID of the webinar to link to"
    )
    zoom_meeting_id = serializers.CharField(
        required=True,
        help_text="Zoom meeting ID to link"
    )
    zoom_join_url = serializers.URLField(
        required=True,
        help_text="Join URL of the Zoom meeting"
    )
    zoom_start_url = serializers.URLField(
        required=False,
        allow_blank=True,
        help_text="Start URL of the Zoom meeting (optional)"
    )
    
    def validate_webinar_id(self, value):
        """Validate webinar exists"""
        from apps.webinars.models import Webinar
        
        try:
            webinar = Webinar.objects.get(id=value)
            
            # Check webinar type
            if webinar.webinar_type != 'live':
                raise serializers.ValidationError(
                    f"Can only link Zoom meetings to live webinars, not {webinar.webinar_type} webinars"
                )
            
            return value
        except Webinar.DoesNotExist:
            raise serializers.ValidationError("Webinar not found")
    
    def validate_zoom_meeting_id(self, value):
        """Validate meeting ID format"""
        if not value or len(str(value)) < 10:
            raise serializers.ValidationError("Invalid Zoom meeting ID")
        return str(value)


# NEW: Serializer for meeting suggestions response
class MeetingSuggestionSerializer(serializers.Serializer):
    """Serializer for meeting suggestion response"""
    
    success = serializers.BooleanField()
    has_existing = serializers.BooleanField()
    count = serializers.IntegerField()
    suggestions = ZoomMeetingSearchResultSerializer(many=True)
    webinar = serializers.DictField(required=False)
    message = serializers.CharField(required=False)
    
class ZoomCredentialsSerializer(serializers.ModelSerializer):
    """Serializer for Zoom credentials (admin only)"""
    
    # Add validation for required fields
    client_secret = serializers.CharField(write_only=True, style={'input_type': 'password'})
    
    class Meta:
        model = ZoomCredentials
        fields = [
            'id', 'name', 'description', 'client_id', 'client_secret', 
            'account_id', 'is_active', 'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']
        extra_kwargs = {
            'client_secret': {'write_only': True},
            'account_id': {'required': True}  # Required for server-to-server OAuth
        }
    
    def validate_client_id(self, value):
        """Validate client ID format"""
        if not value or len(value) < 10:
            raise serializers.ValidationError("Client ID must be at least 10 characters long")
        return value
    
    def validate_client_secret(self, value):
        """Validate client secret format"""
        if not value or len(value) < 20:
            raise serializers.ValidationError("Client secret must be at least 20 characters long")
        return value
    
    def validate_account_id(self, value):
        """Validate account ID format"""
        if not value:
            raise serializers.ValidationError("Account ID is required for server-to-server OAuth")
        return value
    
    def validate(self, data):
        """Object-level validation"""
        # Ensure only one active credential exists
        if data.get('is_active', False):
            existing_active = ZoomCredentials.objects.filter(is_active=True)
            if self.instance:
                existing_active = existing_active.exclude(pk=self.instance.pk)
            
            if existing_active.exists():
                raise serializers.ValidationError(
                    "Only one active Zoom credential is allowed. Please deactivate the current one first."
                )
        
        return data
    
    def to_representation(self, instance):
        """Mask sensitive data in responses"""
        data = super().to_representation(instance)
        
        # Mask client_id for security
        if 'client_id' in data and data['client_id']:
            data['client_id'] = data['client_id'][:10] + '...' if len(data['client_id']) > 10 else data['client_id']
        
        # Never expose client_secret in responses
        data.pop('client_secret', None)
        
        return data


class ZoomMeetingSerializer(serializers.ModelSerializer):
    """Serializer for Zoom meetings"""
    
    webinar_title = serializers.CharField(source='webinar.title', read_only=True)
    created_by_name = serializers.CharField(source='created_by.get_full_name', read_only=True)
    is_active = serializers.BooleanField(read_only=True)
    
    # Add choice field display values
    meeting_type_display = serializers.CharField(source='get_meeting_type_display', read_only=True)
    status_display = serializers.CharField(source='get_status_display', read_only=True)
    auto_recording_display = serializers.CharField(source='get_auto_recording_display', read_only=True)
    
    class Meta:
        model = ZoomMeeting
        fields = [
            'id', 'webinar', 'webinar_title', 'zoom_meeting_id', 'uuid', 'host_id',
            'topic', 'agenda', 'meeting_type', 'meeting_type_display', 'status', 'status_display',
            'start_time', 'duration', 'timezone', 'password', 'join_url', 'start_url',
            'waiting_room', 'join_before_host', 'mute_upon_entry', 'auto_recording', 
            'auto_recording_display', 'use_pmi', 'approval_type', 'registration_type',
            'audio', 'video_host', 'video_participant', 'created_by', 'created_by_name',
            'is_active', 'created_at', 'updated_at'
        ]
        read_only_fields = [
            'id', 'webinar_title', 'zoom_meeting_id', 'uuid', 'host_id', 'join_url',
            'start_url', 'password', 'created_by', 'created_by_name', 'is_active',
            'meeting_type_display', 'status_display', 'auto_recording_display',
            'created_at', 'updated_at'
        ]
    
    def validate_start_time(self, value):
        """Validate start time is not in the past"""
        if value and value < timezone.now():
            raise serializers.ValidationError("Start time cannot be in the past")
        return value
    
    def validate_duration(self, value):
        """Validate duration is within acceptable range"""
        if value and (value < 1 or value > 1440):  # 1 minute to 24 hours
            raise serializers.ValidationError("Duration must be between 1 and 1440 minutes")
        return value


class ZoomWebinarSerializer(serializers.ModelSerializer):
    """Serializer for Zoom webinars"""
    
    webinar_title = serializers.CharField(source='webinar.title', read_only=True)
    created_by_name = serializers.CharField(source='created_by.get_full_name', read_only=True)
    is_active = serializers.BooleanField(read_only=True)
    
    # Add choice field display values
    webinar_type_display = serializers.CharField(source='get_webinar_type_display', read_only=True)
    status_display = serializers.CharField(source='get_status_display', read_only=True)
    auto_recording_display = serializers.CharField(source='get_auto_recording_display', read_only=True)
    approval_type_display = serializers.CharField(source='get_approval_type_display', read_only=True)
    
    class Meta:
        model = ZoomWebinar
        fields = [
            'id', 'webinar', 'webinar_title', 'zoom_webinar_id', 'uuid', 'host_id',
            'topic', 'agenda', 'webinar_type', 'webinar_type_display', 'status', 'status_display',
            'start_time', 'duration', 'timezone', 'password', 'join_url', 'registration_url',
            'approval_type', 'approval_type_display', 'registration_type', 'auto_recording',
            'auto_recording_display', 'hd_video', 'hd_video_for_attendees', 'on_demand',
            'created_by', 'created_by_name', 'is_active', 'created_at', 'updated_at'
        ]
        read_only_fields = [
            'id', 'webinar_title', 'zoom_webinar_id', 'uuid', 'host_id', 'join_url',
            'registration_url', 'password', 'created_by', 'created_by_name', 'is_active',
            'webinar_type_display', 'status_display', 'auto_recording_display',
            'approval_type_display', 'created_at', 'updated_at'
        ]
    
    def validate_start_time(self, value):
        """Validate start time is not in the past"""
        if value and value < timezone.now():
            raise serializers.ValidationError("Start time cannot be in the past")
        return value
    
    def validate_duration(self, value):
        """Validate duration is within acceptable range"""
        if value and (value < 1 or value > 1440):  # 1 minute to 24 hours
            raise serializers.ValidationError("Duration must be between 1 and 1440 minutes")
        return value


class ZoomRecordingSerializer(serializers.ModelSerializer):
    """Serializer for Zoom recordings"""
    
    # Use model properties instead of SerializerMethodField for better performance [web:81][web:84]
    meeting_topic = serializers.CharField(source='zoom_meeting.topic', read_only=True)
    webinar_topic = serializers.CharField(source='zoom_webinar.topic', read_only=True)
    duration_minutes = serializers.ReadOnlyField()  # Uses model property
    file_size_mb = serializers.ReadOnlyField()      # Uses model property
    
    # Add choice field display values
    recording_type_display = serializers.CharField(source='get_recording_type_display', read_only=True)
    status_display = serializers.CharField(source='get_status_display', read_only=True)
    file_type_display = serializers.CharField(source='get_file_type_display', read_only=True)
    
    # Related object info
    related_object = serializers.SerializerMethodField()
    
    class Meta:
        model = ZoomRecording
        fields = [
            'id', 'zoom_meeting', 'zoom_webinar', 'meeting_topic', 'webinar_topic',
            'recording_id', 'meeting_id', 'recording_type', 'recording_type_display',
            'status', 'status_display', 'file_type', 'file_type_display', 'file_size',
            'file_size_mb', 'file_extension', 'download_url', 'play_url',
            'recording_start', 'recording_end', 'duration_minutes', 'participant_count',
            'topic', 'related_object', 'created_at', 'updated_at'
        ]
        read_only_fields = [
            'id', 'meeting_topic', 'webinar_topic', 'recording_id', 'meeting_id',
            'recording_type', 'recording_type_display', 'status', 'status_display',
            'file_type', 'file_type_display', 'file_size', 'file_size_mb', 'file_extension',
            'download_url', 'play_url', 'recording_start', 'recording_end',
            'duration_minutes', 'participant_count', 'topic', 'related_object',
            'created_at', 'updated_at'
        ]
    
    def get_related_object(self, obj):
        """Get information about related meeting or webinar"""
        if obj.zoom_meeting:
            return {
                'type': 'meeting',
                'id': obj.zoom_meeting.id,
                'zoom_id': obj.zoom_meeting.zoom_meeting_id,
                'topic': obj.zoom_meeting.topic
            }
        elif obj.zoom_webinar:
            return {
                'type': 'webinar',
                'id': obj.zoom_webinar.id,
                'zoom_id': obj.zoom_webinar.zoom_webinar_id,
                'topic': obj.zoom_webinar.topic
            }
        return None


class ZoomWebhookEventSerializer(serializers.ModelSerializer):
    """Serializer for Zoom webhook events"""
    
    event_type_display = serializers.CharField(source='get_event_type_display', read_only=True)
    processing_status = serializers.SerializerMethodField()
    
    class Meta:
        model = ZoomWebhookEvent
        fields = [
            'id', 'event_type', 'event_type_display', 'event_ts', 'event_data',
            'processed', 'processing_error', 'processing_attempts', 'processing_status',
            'source_ip', 'user_agent', 'created_at', 'processed_at'
        ]
        read_only_fields = [
            'id', 'event_type_display', 'processing_status', 'created_at', 'processed_at'
        ]
    
    def get_processing_status(self, obj):
        """Get human-readable processing status"""
        if obj.processed:
            return 'Completed'
        elif obj.processing_error:
            return f'Failed (Attempts: {obj.processing_attempts})'
        else:
            return 'Pending'


class ZoomIntegrationLogSerializer(serializers.ModelSerializer):
    """Serializer for Zoom integration logs"""
    
    user_name = serializers.CharField(source='user.get_full_name', read_only=True)
    level_display = serializers.CharField(source='get_level_display', read_only=True)
    action_type_display = serializers.CharField(source='get_action_type_display', read_only=True)
    
    class Meta:
        model = ZoomIntegrationLog
        fields = [
            'id', 'user', 'user_name', 'level', 'level_display', 'action_type',
            'action_type_display', 'message', 'request_data', 'response_data',
            'status_code', 'execution_time', 'created_at'
        ]
        read_only_fields = ['id', 'user_name', 'level_display', 'action_type_display', 'created_at']


# Updated connection status serializer for server-to-server OAuth
class ZoomConnectionStatusSerializer(serializers.Serializer):
    """Serializer for Zoom connection status (server-to-server)"""
    
    is_connected = serializers.BooleanField()
    integration_type = serializers.CharField(default='server_to_server')
    client_id_preview = serializers.CharField(required=False)
    account_id = serializers.CharField(required=False)
    credentials_name = serializers.CharField(required=False)
    status = serializers.CharField()
    last_token_refresh = serializers.DateTimeField(required=False)
    error_message = serializers.CharField(required=False)


# Remove OAuth-related serializers since we're using server-to-server
# class ZoomAuthURLSerializer - REMOVED
# class ZoomAuthCallbackSerializer - REMOVED


class CreateZoomMeetingSerializer(serializers.Serializer):
    """Serializer for creating Zoom meetings"""
    
    webinar_id = serializers.IntegerField()
    host_email = serializers.EmailField()
    meeting_type = serializers.ChoiceField(
        choices=[
            ('auto', 'Auto (based on attendee count)'),
            ('meeting', 'Force Meeting'),
            ('webinar', 'Force Webinar'),
        ],
        default='auto',
        help_text="Auto will choose meeting for ≤500 attendees, webinar for >500"
    )
    use_existing_meeting = serializers.BooleanField(
        required=False,
        default=False,
        help_text="Whether to link to an existing Zoom meeting"
    )
    existing_zoom_meeting_id = serializers.CharField(
        required=False,
        allow_blank=True,
        help_text="ID of existing Zoom meeting to link to"
    )
    # Optional override settings
    settings = serializers.DictField(required=False, help_text="Override default meeting settings")
    def validate(self, data):
        """Validate that if use_existing_meeting is True, meeting_id is provided"""
        if data.get('use_existing_meeting') and not data.get('existing_zoom_meeting_id'):
            raise serializers.ValidationError({
                'existing_zoom_meeting_id': 'Meeting ID is required when linking to existing meeting'
            })
        return data
    # def validate_webinar_id(self, value):
    #     """Validate webinar exists and user has access"""
    #     from apps.webinars.models import Webinar
        
    #     try:
    #         webinar = Webinar.objects.get(id=value)
            
    #         # Check if webinar already has a Zoom meeting/webinar
    #         if hasattr(webinar, 'zoom_meeting') or hasattr(webinar, 'zoom_webinar'):
    #             raise serializers.ValidationError("This webinar already has a Zoom meeting/webinar associated")
            
    #         return value
    #     except Webinar.DoesNotExist:
    #         raise serializers.ValidationError("Webinar not found")
    
    def validate_webinar_id(self, value):
        """Validate webinar exists and user has access"""
        from apps.webinars.models import Webinar
        
        try:
            webinar = Webinar.objects.get(id=value)
            
            # Check webinar type
            if webinar.webinar_type != 'live':
                raise serializers.ValidationError(
                    f"Zoom meetings can only be created for live webinars, not {webinar.webinar_type} webinars"
                )
            
            # Check if webinar already has a Zoom meeting
            if hasattr(webinar, 'zoom_meeting_rel') and webinar.zoom_meeting_rel:
                raise serializers.ValidationError("This webinar already has a Zoom meeting associated")
            
            return value
        except Webinar.DoesNotExist:
            raise serializers.ValidationError("Webinar not found")
            
    def validate_host_email(self, value):
        """Validate host email format"""
        if not value:
            raise serializers.ValidationError("Host email is required")
        return value
    
    # def validate_settings(self, value):
    #     """Validate settings dictionary"""
    #     if value:
    #         allowed_keys = {
    #             'waiting_room', 'join_before_host', 'mute_upon_entry',
    #             'auto_recording', 'approval_type', 'registration_type'
    #         }
            
    #         invalid_keys = set(value.keys()) - allowed_keys
    #         if invalid_keys:
    #             raise serializers.ValidationError(
    #                 f"Invalid settings keys: {', '.join(invalid_keys)}. "
    #                 f"Allowed keys: {', '.join(allowed_keys)}"
    #             )
        
    #     return value

    def validate_settings(self, value):
        """Validate settings dictionary"""
        if value:
            allowed_keys = {
                'recordingPreference', 'waitingRoom', 'interactionLevel',
                'muteOnEntry', 'enableChat', 'enableQA', 'enablePolls',
                'allowScreenShare'
            }
            
            # Allow all keys, just log a warning for unknown ones
            unknown_keys = set(value.keys()) - allowed_keys
            if unknown_keys:
                import logging
                logger = logging.getLogger(__name__)
                logger.warning(f"Unknown settings keys: {', '.join(unknown_keys)}")
        
        return value

# class UpdateZoomMeetingSerializer(serializers.Serializer):
#     """Serializer for updating Zoom meetings"""
    
#     topic = serializers.CharField(max_length=300, required=False)
#     agenda = serializers.CharField(required=False, allow_blank=True)
#     start_time = serializers.DateTimeField(required=False)
#     duration = serializers.IntegerField(min_value=1, max_value=1440, required=False)
#     timezone = serializers.CharField(max_length=50, required=False)
    
#     # Meeting settings
#     waiting_room = serializers.BooleanField(required=False)
#     join_before_host = serializers.BooleanField(required=False)
#     mute_upon_entry = serializers.BooleanField(required=False)
#     auto_recording = serializers.ChoiceField(
#         choices=[('none', 'None'), ('local', 'Local'), ('cloud', 'Cloud')],
#         required=False
#     )
    
#     def validate_start_time(self, value):
#         """Validate start time is not in the past"""
#         if value and value < timezone.now():
#             raise serializers.ValidationError("Start time cannot be in the past")
#         return value


class UpdateZoomMeetingSerializer(serializers.Serializer):
    """Serializer for updating Zoom meetings with complete preference support"""
    
    # Basic meeting details
    topic = serializers.CharField(max_length=300, required=False)
    agenda = serializers.CharField(required=False, allow_blank=True)
    start_time = serializers.DateTimeField(required=False)
    duration = serializers.IntegerField(min_value=1, max_value=1440, required=False)
    timezone = serializers.CharField(max_length=50, required=False)
    
    # Frontend preference fields (matching create serializer)
    recordingPreference = serializers.ChoiceField(
        choices=[
            ('automatic', 'Automatic Recording'),
            ('manual', 'Manual Recording'),
            ('disabled', 'No Recording'),
            ('cloud', 'Cloud Recording'),
            ('local', 'Local Recording'),
            ('none', 'None')
        ],
        required=False,
        help_text="Recording preference for the meeting"
    )
    
    waitingRoom = serializers.ChoiceField(
        choices=[
            ('enabled', 'Enable Waiting Room'),
            ('disabled', 'Disable Waiting Room')
        ],
        required=False,
        help_text="Whether to enable waiting room"
    )
    
    interactionLevel = serializers.ChoiceField(
        choices=[
            ('full', 'Full Interaction'),
            ('limited', 'Limited Interaction'),
            ('presentation', 'Presentation Mode')
        ],
        required=False,
        help_text="Level of attendee interaction allowed"
    )
    
    muteOnEntry = serializers.BooleanField(
        required=False,
        help_text="Automatically mute attendees when they join"
    )
    
    enableChat = serializers.BooleanField(
        required=False,
        help_text="Allow attendees to chat during the meeting"
    )
    
    enableQA = serializers.BooleanField(
        required=False,
        help_text="Allow attendees to submit questions"
    )
    
    enablePolls = serializers.BooleanField(
        required=False,
        help_text="Enable polling during the meeting"
    )
    
    allowScreenShare = serializers.BooleanField(
        required=False,
        help_text="Allow attendees to share their screens"
    )
    
    # Legacy fields for backward compatibility (map to frontend fields)
    waiting_room = serializers.BooleanField(
        required=False,
        write_only=True,
        help_text="[Deprecated] Use waitingRoom instead"
    )
    
    join_before_host = serializers.BooleanField(
        required=False,
        write_only=True,
        help_text="[Deprecated] Use waitingRoom instead"
    )
    
    mute_upon_entry = serializers.BooleanField(
        required=False,
        write_only=True,
        help_text="[Deprecated] Use muteOnEntry instead"
    )
    
    auto_recording = serializers.ChoiceField(
        choices=[('none', 'None'), ('local', 'Local'), ('cloud', 'Cloud')],
        required=False,
        write_only=True,
        help_text="[Deprecated] Use recordingPreference instead"
    )
    
    def validate_start_time(self, value):
        """Validate start time is not in the past"""
        if value and value < timezone.now():
            raise serializers.ValidationError("Start time cannot be in the past")
        return value
    
    def validate_duration(self, value):
        """Validate duration is within acceptable range"""
        if value and (value < 1 or value > 1440):
            raise serializers.ValidationError("Duration must be between 1 and 1440 minutes (24 hours)")
        return value
    
    def validate(self, data):
        """
        Object-level validation and normalization
        Map legacy fields to new frontend preference fields
        """
        # Map legacy fields to frontend fields for backward compatibility
        if 'waiting_room' in data:
            data['waitingRoom'] = 'enabled' if data.pop('waiting_room') else 'disabled'
        
        if 'join_before_host' in data:
            # join_before_host is inverse of waiting_room
            if 'waitingRoom' not in data:
                data['waitingRoom'] = 'disabled' if data.pop('join_before_host') else 'enabled'
            else:
                data.pop('join_before_host')
        
        if 'mute_upon_entry' in data:
            data['muteOnEntry'] = data.pop('mute_upon_entry')
        
        if 'auto_recording' in data:
            recording_map = {
                'none': 'disabled',
                'local': 'local',
                'cloud': 'automatic'
            }
            data['recordingPreference'] = recording_map.get(data.pop('auto_recording'), 'disabled')
        
        return data
    
    def to_internal_value(self, data):
        """
        Convert incoming data to internal format
        This allows the view to receive data in either format
        """
        internal_value = super().to_internal_value(data)
        
        # Build preferences dict for the service
        preferences = {}
        
        if 'recordingPreference' in internal_value:
            preferences['recordingPreference'] = internal_value['recordingPreference']
        
        if 'waitingRoom' in internal_value:
            preferences['waitingRoom'] = internal_value['waitingRoom']
        
        if 'interactionLevel' in internal_value:
            preferences['interactionLevel'] = internal_value['interactionLevel']
        
        if 'muteOnEntry' in internal_value:
            preferences['muteOnEntry'] = internal_value['muteOnEntry']
        
        if 'enableChat' in internal_value:
            preferences['enableChat'] = internal_value['enableChat']
        
        if 'enableQA' in internal_value:
            preferences['enableQA'] = internal_value['enableQA']
        
        if 'enablePolls' in internal_value:
            preferences['enablePolls'] = internal_value['enablePolls']
        
        if 'allowScreenShare' in internal_value:
            preferences['allowScreenShare'] = internal_value['allowScreenShare']
        
        # Store preferences in a nested dict if any exist
        if preferences:
            internal_value['preferences'] = preferences
        
        return internal_value


class ZoomMeetingListSerializer(serializers.ModelSerializer):
    """Lightweight serializer for listing meetings (performance optimized)"""
    
    webinar_title = serializers.CharField(source='webinar.title', read_only=True)
    is_active = serializers.BooleanField(read_only=True)
    
    class Meta:
        model = ZoomMeeting
        fields = [
            'id', 'webinar_title', 'zoom_meeting_id', 'topic', 'status',
            'start_time', 'duration', 'join_url', 'is_active'
        ]


class ZoomWebinarListSerializer(serializers.ModelSerializer):
    """Lightweight serializer for listing webinars (performance optimized)"""
    
    webinar_title = serializers.CharField(source='webinar.title', read_only=True)
    is_active = serializers.BooleanField(read_only=True)
    
    class Meta:
        model = ZoomWebinar
        fields = [
            'id', 'webinar_title', 'zoom_webinar_id', 'topic', 'status',
            'start_time', 'duration', 'join_url', 'is_active'
        ]
