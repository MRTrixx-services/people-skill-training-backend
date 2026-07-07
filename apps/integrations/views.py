# apps/integrations/views.py - ENHANCED with conditional webinar types and auto-conversion
import logging
from typing import Dict, Any
from rest_framework import generics, permissions, status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response
from django.shortcuts import get_object_or_404
from django.utils import timezone
from django.core.exceptions import ValidationError
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods
from django.db import models
from django.http import JsonResponse
import base64, requests, sys

from apps.users.permissions import IsAdminOrReadOnly, IsOwnerOrAdmin
from apps.webinars.models import Webinar
from .models import (
    ZoomCredentials, 
    ZoomMeeting, 
    ZoomWebinar, 
    ZoomRecording,
    ZoomWebhookEvent,
    ZoomIntegrationLog
)
from .serializers import (
    ZoomCredentialsSerializer,
    ZoomMeetingSerializer,
    ZoomWebinarSerializer,
    ZoomRecordingSerializer,
    ZoomWebhookEventSerializer,
    ZoomIntegrationLogSerializer,
    ZoomConnectionStatusSerializer,
    CreateZoomMeetingSerializer,
    UpdateZoomMeetingSerializer,
    ZoomMeetingListSerializer,
    ZoomWebinarListSerializer
)
from .services import ZoomAPIService, ZoomWebinarService
from datetime import datetime, timedelta
import re
from difflib import SequenceMatcher

logger = logging.getLogger(__name__)

class ZoomCredentialsView(generics.ListCreateAPIView):
    """Manage Zoom credentials (admin only)"""
    
    queryset = ZoomCredentials.objects.all()
    serializer_class = ZoomCredentialsSerializer
    permission_classes = [permissions.IsAuthenticated, permissions.IsAdminUser]
    
    def perform_create(self, serializer):
        """Log credential creation"""
        instance = serializer.save()
        logger.info(f"Zoom credentials created by {self.request.user}: {instance.name}")

class ZoomCredentialsDetailView(generics.RetrieveUpdateDestroyAPIView):
    """Zoom credentials detail view (admin only)"""
    
    queryset = ZoomCredentials.objects.all()
    serializer_class = ZoomCredentialsSerializer
    permission_classes = [permissions.IsAuthenticated, permissions.IsAdminUser]
    
    def perform_update(self, serializer):
        """Log credential updates"""
        instance = serializer.save()
        logger.info(f"Zoom credentials updated by {self.request.user}: {instance.name}")
    
    def perform_destroy(self, instance):
        """Log credential deletion"""
        logger.info(f"Zoom credentials deleted by {self.request.user}: {instance.name}")
        instance.delete()

@api_view(['GET'])
@permission_classes([permissions.IsAuthenticated])
def zoom_connection_status(request):
    """Check Zoom integration status (server-to-server)"""
    try:
        credentials = ZoomCredentials.objects.filter(is_active=True).first()
        
        if not credentials:
            data = {
                'is_connected': False,
                'integration_type': 'server_to_server',
                'status': 'no_credentials',
                'error_message': 'No active Zoom credentials configured'
            }
        else:
            try:
                # Test connection by attempting to get access token
                zoom_service = ZoomAPIService()
                connection_test = zoom_service.test_connection()
               
                if connection_test.get('success'):
                    data = {
                        'is_connected': True,
                        'integration_type': 'server_to_server',
                        'client_id_preview': credentials.client_id[:10] + '...',
                        'account_id': credentials.account_id,
                        'credentials_name': credentials.name,
                        'status': 'active',
                        'user_email': connection_test.get('user_email'),
                        'user_type': connection_test.get('user_type')
                    }
                else:
                    data = {
                        'is_connected': False,
                        'integration_type': 'server_to_server',
                        'status': 'connection_failed',
                        'error_message': connection_test.get('error', 'Connection test failed')
                    }
                    
            except Exception as e:
                logger.error(f"Zoom connection test failed: {str(e)}")
                data = {
                    'is_connected': False,
                    'integration_type': 'server_to_server',
                    'status': 'error',
                    'error_message': str(e)
                }
        
        serializer = ZoomConnectionStatusSerializer(data)
        return Response(serializer.data)
    
    except Exception as e:
        logger.error(f"Error checking Zoom connection status: {str(e)}")
        return Response({
            'error': 'Failed to check connection status'
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

# ENHANCED: Create zoom meeting with conditional handling

@api_view(['POST'])
@permission_classes([permissions.IsAuthenticated])
def create_zoom_meeting(request):
    """Create a Zoom meeting OR link to existing one"""
    serializer = CreateZoomMeetingSerializer(data=request.data)
    
    try:
        serializer.is_valid(raise_exception=True)
        
        webinar = get_object_or_404(Webinar, id=serializer.validated_data['webinar_id'])
        
        # Check webinar type
        if webinar.webinar_type != 'live':
            return Response({
                'error': f'Zoom meetings can only be created for live webinars'
            }, status=status.HTTP_400_BAD_REQUEST)
        
        # Check permissions
        if not _check_webinar_permissions(request.user, webinar):
            return Response({
                'error': 'Permission denied'
            }, status=status.HTTP_403_FORBIDDEN)
        
        # Check if Zoom meeting already exists
        if _webinar_has_zoom_meeting(webinar):
            return Response({
                'error': 'Zoom meeting already exists for this webinar'
            }, status=status.HTTP_400_BAD_REQUEST)
        
        # NEW: Check if linking to existing meeting
        use_existing = serializer.validated_data.get('use_existing_meeting', False)
        existing_meeting_id = serializer.validated_data.get('existing_zoom_meeting_id')
        
        if use_existing and existing_meeting_id:
            # Link to existing meeting
            logger.info(f"🔗 Linking webinar {webinar.webinar_id} to existing meeting {existing_meeting_id}")
            
            zoom_meeting = _link_existing_zoom_meeting(
                webinar=webinar,
                meeting_id=existing_meeting_id,
                user=request.user
            )
            
            response_serializer = ZoomMeetingSerializer(zoom_meeting)
            
            return Response({
                'message': 'Successfully linked to existing Zoom meeting',
                'linked': True,
                'data': response_serializer.data
            }, status=status.HTTP_201_CREATED)
        
        else:
            # Create new meeting
            logger.info(f"🆕 Creating new Zoom meeting for webinar {webinar.webinar_id}")
            
            zoom_service = ZoomWebinarService()
            settings = serializer.validated_data.get('settings', {})
            
            zoom_object = zoom_service.create_webinar_meeting(
                webinar, 
                user=request.user,
                preferences=settings
            )
            
            if not zoom_object:
                return Response({
                    'error': 'Failed to create Zoom meeting'
                }, status=status.HTTP_400_BAD_REQUEST)
            
            response_serializer = ZoomMeetingSerializer(zoom_object)
            
            return Response({
                'message': 'Zoom meeting created successfully',
                'created': True,
                'data': response_serializer.data
            }, status=status.HTTP_201_CREATED)
    
    except ValidationError as e:
        logger.error(f"Validation error: {str(e)}")
        return Response({
            'error': str(e)
        }, status=status.HTTP_400_BAD_REQUEST)
    
    except Exception as e:
        logger.error(f"Unexpected error: {str(e)}")
        logger.exception("Full traceback:")
        return Response({
            'error': 'An unexpected error occurred'
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


# apps/integrations/views.py
# apps/integrations/views.py
# apps/integrations/views.py or utils.py

# apps/integrations/views.py or utils.py

def _link_existing_zoom_meeting(webinar, meeting_id, user, force_relink=False):
    """
    Link an existing Zoom meeting to a webinar
    Creates a ZoomMeeting record that links the Zoom meeting to the webinar
    
    Args:
        webinar: Webinar instance to link to
        meeting_id: Zoom meeting ID to link
        user: User performing the action
        force_relink: Not used anymore, kept for compatibility
    
    Returns:
        ZoomMeeting instance
        
    Raises:
        ValidationError: If linking fails
    """
    from apps.integrations.models import ZoomMeeting
    from apps.integrations.services import ZoomAPIService
    from django.core.exceptions import ValidationError
    
    logger.info(f"🔗 Attempting to link meeting {meeting_id} to webinar {webinar.webinar_id}")
    
    # ✅ CHECK: Does this webinar already have this meeting linked?
    existing_link = ZoomMeeting.objects.filter(
        webinar=webinar,
        zoom_meeting_id=str(meeting_id)
    ).first()
    
    if existing_link:
        logger.info(f"ℹ️ Meeting {meeting_id} is already linked to webinar {webinar.webinar_id}")
        return existing_link
    
    # ✅ DELETE ANY OTHER ZOOM MEETINGS FOR THIS WEBINAR
    # (Only if you want one meeting per webinar)
    old_meetings = ZoomMeeting.objects.filter(webinar=webinar)
    if old_meetings.exists():
        old_count = old_meetings.count()
        old_meetings_ids = list(old_meetings.values_list('zoom_meeting_id', flat=True))
        old_meetings.delete()
        logger.info(f"🗑️ Deleted {old_count} existing meeting(s) for webinar {webinar.webinar_id}: {old_meetings_ids}")
    
    # ✅ CHECK: Is this meeting already linked to OTHER webinars?
    other_webinars = ZoomMeeting.objects.filter(
        zoom_meeting_id=str(meeting_id)
    ).exclude(webinar=webinar)
    
    if other_webinars.exists():
        other_count = other_webinars.count()
        other_titles = [zm.webinar.title for zm in other_webinars[:3]]
        logger.info(
            f"ℹ️ Meeting {meeting_id} is already shared with {other_count} other webinar(s): "
            f"{', '.join(other_titles)}"
        )
    
    # ✅ GET MEETING DETAILS FROM ZOOM (or reuse from existing link)
    existing_meeting = ZoomMeeting.objects.filter(zoom_meeting_id=str(meeting_id)).first()
    
    if existing_meeting:
        # Reuse data from existing link
        logger.info(f"✅ Reusing data from existing Zoom meeting record")
        meeting_data = {
            'uuid': existing_meeting.uuid,
            'host_id': existing_meeting.host_id,
            'topic': existing_meeting.topic,
            'type': existing_meeting.meeting_type,
            'join_url': existing_meeting.join_url,
            'start_url': existing_meeting.start_url,
            'password': existing_meeting.password,
            'duration': existing_meeting.duration,
            'timezone': existing_meeting.timezone,
            'settings': {
                'waiting_room': existing_meeting.waiting_room,
                'join_before_host': existing_meeting.join_before_host,
                'mute_upon_entry': existing_meeting.mute_upon_entry,
                'auto_recording': existing_meeting.auto_recording,
                'meeting_chat': existing_meeting.enable_chat,
                'share_screen': existing_meeting.allow_screen_share,
                'audio': existing_meeting.audio,
                'host_video': existing_meeting.video_host,
                'participant_video': existing_meeting.video_participant,
            }
        }
    else:
        # Fetch fresh from Zoom API
        try:
            api = ZoomAPIService()
            meeting_data = api.get_meeting(str(meeting_id))
            
            if not meeting_data:
                raise ValidationError(f'Meeting {meeting_id} not found in Zoom account.')
            
            logger.info(f"✅ Retrieved meeting from Zoom: {meeting_data.get('topic')}")
            
        except ValidationError:
            raise
        except Exception as e:
            logger.error(f"❌ Failed to fetch meeting from Zoom: {str(e)}")
            raise ValidationError(f'Failed to retrieve meeting from Zoom: {str(e)}')
    
    # ✅ CREATE NEW ZOOM MEETING LINK FOR THIS WEBINAR
    try:
        # Parse start time
        start_time = webinar.scheduled_date
        if 'start_time' in meeting_data:
            try:
                from datetime import datetime
                from django.utils import timezone as dj_timezone
                start_time_str = meeting_data['start_time']
                start_time = datetime.fromisoformat(start_time_str.replace('Z', '+00:00'))
                if hasattr(start_time, 'tzinfo') and start_time.tzinfo:
                    start_time = dj_timezone.make_naive(start_time)
            except Exception as e:
                logger.warning(f"Could not parse start_time: {e}")
        
        zoom_meeting = ZoomMeeting.objects.create(
            webinar=webinar,
            zoom_meeting_id=str(meeting_id),
            uuid=meeting_data.get('uuid', ''),
            host_id=meeting_data.get('host_id', ''),
            topic=meeting_data.get('topic', webinar.title),
            agenda=meeting_data.get('agenda', ''),
            meeting_type=meeting_data.get('type', 2),
            start_time=start_time,
            duration=webinar.duration or meeting_data.get('duration', 60),
            timezone=webinar.timezone or meeting_data.get('timezone', 'UTC'),
            password=meeting_data.get('password', ''),
            join_url=meeting_data.get('join_url', ''),
            start_url=meeting_data.get('start_url', ''),
            
            # Settings
            waiting_room=meeting_data.get('settings', {}).get('waiting_room', True),
            join_before_host=meeting_data.get('settings', {}).get('join_before_host', False),
            mute_upon_entry=meeting_data.get('settings', {}).get('mute_upon_entry', True),
            auto_recording=meeting_data.get('settings', {}).get('auto_recording', 'none'),
            enable_chat=meeting_data.get('settings', {}).get('meeting_chat', True),
            enable_qa=meeting_data.get('settings', {}).get('question_and_answer', {}).get('enable', False),
            allow_screen_share=meeting_data.get('settings', {}).get('share_screen', True),
            enable_polls=meeting_data.get('settings', {}).get('polling', False),
            audio=meeting_data.get('settings', {}).get('audio', 'both'),
            video_host=meeting_data.get('settings', {}).get('host_video', True),
            video_participant=meeting_data.get('settings', {}).get('participant_video', True),
            
            # Mark as linked to existing
            is_linked_existing=True,
            created_by=user
        )
        
        # ❌ REMOVED: Don't try to update webinar.zoom_webinar_link
        # It's likely a @property that's dynamically generated from zoom_meetings
        # webinar.zoom_webinar_link = meeting_data.get('join_url', '')
        # webinar.save(update_fields=['zoom_webinar_link'])
        
        if other_webinars.exists():
            logger.info(
                f"✅ Linked meeting {meeting_id} to webinar {webinar.webinar_id} "
                f"(now shared with {other_count + 1} webinars total)"
            )
        else:
            logger.info(f"✅ Successfully linked webinar {webinar.webinar_id} to meeting {meeting_id}")
        
        return zoom_meeting
        
    except Exception as e:
        logger.error(f"❌ Failed to create ZoomMeeting record: {str(e)}")
        logger.exception("Full traceback:")
        raise ValidationError(f"Failed to link meeting: {str(e)}")

# def _link_existing_zoom_meeting(webinar, meeting_id, user):
#     """
#     Link webinar to existing Zoom meeting
#     Fetches meeting details from Zoom API and creates local record
#     """
#     try:
#         # Get credentials
#         credentials = ZoomCredentials.objects.filter(is_active=True).first()
#         if not credentials:
#             raise ValidationError("No active Zoom credentials found")
        
#         # Get access token
#         logger.info("🔐 Getting access token for meeting details...")
#         token_url = f"https://zoom.us/oauth/token?grant_type=account_credentials&account_id={credentials.account_id}"
#         auth_value = base64.b64encode(
#             f"{credentials.client_id}:{credentials.client_secret}".encode()
#         ).decode()
        
#         token_headers = {
#             "Authorization": f"Basic {auth_value}",
#             "Content-Type": "application/x-www-form-urlencoded",
#         }
        
#         token_response = requests.post(token_url, headers=token_headers, timeout=30)
#         token_response.raise_for_status()
#         access_token = token_response.json()["access_token"]
        
#         # Get meeting details from Zoom
#         logger.info(f"📥 Fetching details for meeting {meeting_id}...")
#         meeting_url = f"https://api.zoom.us/v2/meetings/{meeting_id}"
#         meeting_headers = {"Authorization": f"Bearer {access_token}"}
        
#         meeting_response = requests.get(meeting_url, headers=meeting_headers, timeout=30)
#         meeting_response.raise_for_status()
#         meeting_data = meeting_response.json()
        
#         logger.info(f"✅ Retrieved meeting: {meeting_data.get('topic')}")
        
#         # Create ZoomMeeting record
#         zoom_meeting = ZoomMeeting.objects.create(
#             webinar=webinar,
#             zoom_meeting_id=str(meeting_id),
#             uuid=meeting_data.get('uuid', ''),
#             host_id=meeting_data.get('host_id', ''),
#             topic=meeting_data.get('topic', webinar.title),
#             agenda=meeting_data.get('agenda', ''),
#             meeting_type=meeting_data.get('type', 2),
#             start_time=webinar.scheduled_date,
#             duration=webinar.duration,
#             timezone=webinar.timezone or "UTC",
#             password=meeting_data.get('password', ''),
#             join_url=meeting_data.get('join_url', ''),
#             start_url=meeting_data.get('start_url', ''),
            
#             # Get settings from existing meeting
#             waiting_room=meeting_data.get('settings', {}).get('waiting_room', True),
#             join_before_host=meeting_data.get('settings', {}).get('join_before_host', False),
#             mute_upon_entry=meeting_data.get('settings', {}).get('mute_upon_entry', True),
#             auto_recording=meeting_data.get('settings', {}).get('auto_recording', 'none'),
            
#             # Mark as linked to existing
#             is_linked_existing=True,
#             created_by=user
#         )
        
#         logger.info(f"✅ Successfully linked webinar {webinar.webinar_id} to meeting {meeting_id}")
        
#         return zoom_meeting
        
#     except requests.exceptions.HTTPError as e:
#         logger.error(f"❌ HTTP error linking meeting: {str(e)}")
#         if hasattr(e, 'response') and e.response is not None:
#             logger.error(f"Response: {e.response.text}")
#         raise ValidationError(f"Failed to fetch meeting details: {str(e)}")
#     except Exception as e:
#         logger.error(f"❌ Error linking existing meeting: {str(e)}")
#         raise ValidationError(f"Failed to link existing meeting: {str(e)}")


# In apps/integrations/views.py
# apps/integrations/views.py

@api_view(['PATCH'])
@permission_classes([permissions.IsAuthenticated])
def update_zoom_meeting(request, meeting_id):
    """Update a Zoom meeting for live webinars"""
    try:
        # Find meeting
        try:
            zoom_meeting = ZoomMeeting.objects.get(zoom_meeting_id=meeting_id)
            webinar = zoom_meeting.webinar
        except ZoomMeeting.DoesNotExist:
            return Response({
                'error': 'Zoom meeting not found'
            }, status=status.HTTP_404_NOT_FOUND)
        
        # Check webinar type
        if webinar.webinar_type != 'live':
            return Response({
                'error': f'Cannot update Zoom meeting for {webinar.webinar_type} webinar'
            }, status=status.HTTP_400_BAD_REQUEST)
        
        # Check permissions
        if not _check_webinar_permissions(request.user, webinar):
            return Response({
                'error': 'Permission denied'
            }, status=status.HTTP_403_FORBIDDEN)
        
        # NEW: Check if this is a linked existing meeting
        is_linked_existing = getattr(zoom_meeting, 'is_linked_existing', False)
        
        if is_linked_existing:
            logger.warning(f"⚠️ Attempting to update a linked existing meeting {meeting_id}")
            return Response({
                'error': 'Cannot update a linked existing Zoom meeting. Please update directly in Zoom.',
                'is_linked_existing': True,
                'zoom_meeting_url': zoom_meeting.join_url
            }, status=status.HTTP_400_BAD_REQUEST)
        
        serializer = UpdateZoomMeetingSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        
        validated_data = serializer.validated_data
        
        # Build updates dict
        updates = {}
        
        # Basic fields
        if 'topic' in validated_data:
            updates['topic'] = validated_data['topic']
        if 'agenda' in validated_data:
            updates['agenda'] = validated_data['agenda']
        if 'start_time' in validated_data:
            updates['start_time'] = validated_data['start_time']
        if 'duration' in validated_data:
            updates['duration'] = validated_data['duration']
        if 'timezone' in validated_data:
            updates['timezone'] = validated_data['timezone']
        
        # Add preferences if present
        if 'preferences' in validated_data:
            updates['preferences'] = validated_data['preferences']
        
        logger.info(f"🔄 Updating meeting {meeting_id} with updates: {list(updates.keys())}")
        
        # Update via service (only for meetings we created)
        zoom_service = ZoomWebinarService()
        success = zoom_service.update_webinar_meeting(webinar, preferences=updates.get('preferences'))
        
        if success:
            # Update local database fields
            if 'topic' in updates:
                zoom_meeting.topic = updates['topic']
            if 'agenda' in updates:
                zoom_meeting.agenda = updates['agenda']
            if 'start_time' in updates:
                zoom_meeting.start_time = updates['start_time']
                webinar.scheduled_date = updates['start_time']
            if 'duration' in updates:
                zoom_meeting.duration = updates['duration']
                webinar.duration = updates['duration']
            if 'timezone' in updates:
                zoom_meeting.timezone = updates['timezone']
                webinar.timezone = updates['timezone']
            
            # Update preference fields
            if 'preferences' in updates:
                prefs = updates['preferences']
                
                if 'waitingRoom' in prefs:
                    zoom_meeting.waiting_room = prefs['waitingRoom'] == 'enabled'
                
                if 'muteOnEntry' in prefs:
                    zoom_meeting.mute_upon_entry = prefs['muteOnEntry']
                
                if 'recordingPreference' in prefs:
                    recording_map = {
                        'automatic': 'cloud',
                        'manual': 'none',
                        'disabled': 'none',
                        'cloud': 'cloud',
                        'local': 'local',
                        'none': 'none'
                    }
                    zoom_meeting.auto_recording = recording_map.get(prefs['recordingPreference'], 'none')
                
                if 'enableChat' in prefs:
                    zoom_meeting.enable_chat = prefs['enableChat']
                
                if 'enableQA' in prefs:
                    zoom_meeting.enable_qa = prefs['enableQA']
                
                if 'allowScreenShare' in prefs:
                    zoom_meeting.allow_screen_share = prefs['allowScreenShare']
                
                if 'enablePolls' in prefs:
                    zoom_meeting.enable_polls = prefs['enablePolls']
            
            zoom_meeting.save()
            webinar.save(update_fields=['scheduled_date', 'duration', 'timezone'])
            
            zoom_meeting.refresh_from_db()
            response_serializer = ZoomMeetingSerializer(zoom_meeting)
            
            logger.info(f"✅ Meeting {meeting_id} updated successfully")
            
            return Response({
                'message': 'Zoom meeting updated successfully',
                'is_linked_existing': False,
                'data': response_serializer.data
            })
        else:
            return Response({
                'error': 'Failed to update Zoom meeting'
            }, status=status.HTTP_400_BAD_REQUEST)
    
    except Exception as e:
        logger.error(f"❌ Error updating meeting {meeting_id}: {str(e)}")
        logger.exception("Full traceback:")
        return Response({
            'error': str(e)
        }, status=status.HTTP_400_BAD_REQUEST)

# ENHANCED: Update zoom meeting with conditional handling
# @api_view(['PATCH'])
# @permission_classes([permissions.IsAuthenticated])
# def update_zoom_meeting(request, meeting_id):
#     """Update a Zoom meeting for live webinars"""
#     try:
#         # Find meeting
#         try:
#             zoom_meeting = ZoomMeeting.objects.get(zoom_meeting_id=meeting_id)
#             webinar = zoom_meeting.webinar
#         except ZoomMeeting.DoesNotExist:
#             return Response({
#                 'error': 'Zoom meeting not found'
#             }, status=status.HTTP_404_NOT_FOUND)
        
#         # ADDED: Check webinar type
#         if webinar.webinar_type != 'live':
#             return Response({
#                 'error': f'Cannot update Zoom meeting for {webinar.webinar_type} webinar'
#             }, status=status.HTTP_400_BAD_REQUEST)
        
#         # FIXED: Check permissions with Speaker relationship
#         if not _check_webinar_permissions(request.user, webinar):
#             return Response({
#                 'error': 'Permission denied'
#             }, status=status.HTTP_403_FORBIDDEN)
        
#         serializer = UpdateZoomMeetingSerializer(data=request.data)
#         serializer.is_valid(raise_exception=True)
        
#         # Update via service
#         zoom_service = ZoomWebinarService()
#         success = zoom_service.update_webinar_meeting(webinar, preferences=serializer.validated_data)
        
#         if success:
#             # Refresh from database to get updated data
#             zoom_meeting.refresh_from_db()
#             response_serializer = ZoomMeetingSerializer(zoom_meeting)
            
#             return Response({
#                 'message': 'Zoom meeting updated successfully',
#                 'data': response_serializer.data
#             })
#         else:
#             return Response({
#                 'error': 'Failed to update Zoom meeting'
#             }, status=status.HTTP_400_BAD_REQUEST)
    
#     except Exception as e:
#         logger.error(f"Error updating Zoom meeting {meeting_id}: {str(e)}")
#         return Response({
#             'error': str(e)
#         }, status=status.HTTP_400_BAD_REQUEST)

# ENHANCED: Delete zoom meeting with conditional handling



@api_view(['POST'])
@permission_classes([permissions.IsAuthenticated])
def replace_zoom_meeting(request):
    """Replace existing Zoom meeting with a different one"""
    try:
        webinar_id = request.data.get('webinar_id')
        action = request.data.get('action')  # 'unlink' or 'delete'
        current_meeting_id = request.data.get('current_meeting_id')
        new_meeting_id = request.data.get('new_meeting_id')
        
        logger.info(f"🔄 Replace request: webinar={webinar_id}, action={action}, current={current_meeting_id}, new={new_meeting_id}")
        
        # Validate required fields
        if not all([action, current_meeting_id, new_meeting_id]):
            return Response({
                'success': False,
                'error': 'Missing required parameters: action, current_meeting_id, new_meeting_id'
            }, status=status.HTTP_400_BAD_REQUEST)
        
        # Get webinar if webinar_id provided
        webinar = None
        if webinar_id:
            from apps.webinars.models import Webinar
            try:
                webinar = Webinar.objects.get(id=webinar_id)
                
                # Check permissions
                if not _check_webinar_permissions(request.user, webinar):
                    return Response({
                        'success': False,
                        'error': 'Permission denied'
                    }, status=status.HTTP_403_FORBIDDEN)
            except Webinar.DoesNotExist:
                logger.warning(f"⚠️ Webinar {webinar_id} not found")
        
        # Get current meeting from database
        try:
            current_meeting = ZoomMeeting.objects.get(zoom_meeting_id=current_meeting_id)
            logger.info(f"✅ Found current meeting in database: {current_meeting_id}")
            webinar = current_meeting.webinar  # Get webinar from meeting if not provided
        except ZoomMeeting.DoesNotExist:
            logger.error(f"❌ Current meeting {current_meeting_id} not found in database")
            return Response({
                'success': False,
                'error': f'Current meeting {current_meeting_id} not found'
            }, status=status.HTTP_404_NOT_FOUND)
        
        # Handle delete action
        if action == 'delete':
            logger.info(f"🗑️ Deleting meeting {current_meeting_id} from Zoom")
            zoom_service = ZoomWebinarService()
            try:
                # Try to delete from Zoom
                delete_url = f"https://api.zoom.us/v2/meetings/{current_meeting_id}"
                zoom_service._make_zoom_request('DELETE', delete_url)
                logger.info(f"✅ Deleted meeting from Zoom")
            except Exception as e:
                logger.warning(f"⚠️ Failed to delete from Zoom (may not exist): {e}")
                # Continue anyway - will unlink locally
        
        # Unlink current meeting (delete local record)
        logger.info(f"🔗 Unlinking current meeting from database")
        current_meeting.delete()
        logger.info(f"✅ Current meeting unlinked")
        
        # Link new meeting
        logger.info(f"🔗 Linking new meeting {new_meeting_id}")
        new_zoom_meeting = _link_existing_zoom_meeting(
            webinar=webinar,
            meeting_id=new_meeting_id,
            user=request.user
        )
        
        logger.info(f"✅ Successfully replaced meeting")
        
        # Return new meeting details
        from .serializers import ZoomMeetingSerializer
        serializer = ZoomMeetingSerializer(new_zoom_meeting)
        
        return Response({
            'success': True,
            'message': f'Meeting replaced successfully ({action}ed old meeting)',
            'action_taken': action,
            'old_meeting_id': current_meeting_id,
            'new_meeting_id': new_meeting_id,
            'data': serializer.data
        })
        
    except Exception as e:
        logger.error(f"❌ Error replacing meeting: {str(e)}")
        logger.exception("Full traceback:")
        return Response({
            'success': False,
            'error': str(e)
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

@api_view(['DELETE'])
@permission_classes([permissions.IsAuthenticated])
def delete_zoom_meeting(request, meeting_id):
    """Delete a Zoom meeting for live webinars"""
    try:
        # Find meeting
        try:
            zoom_meeting = ZoomMeeting.objects.get(zoom_meeting_id=meeting_id)
            webinar = zoom_meeting.webinar
        except ZoomMeeting.DoesNotExist:
            return Response({
                'error': 'Zoom meeting not found'
            }, status=status.HTTP_404_NOT_FOUND)
        
        # FIXED: Check permissions with Speaker relationship
        if not _check_webinar_permissions(request.user, webinar):
            return Response({
                'error': 'Permission denied'
            }, status=status.HTTP_403_FORBIDDEN)
        
        # Delete via service
        zoom_service = ZoomWebinarService()
        success = zoom_service.delete_webinar_meeting(webinar)
        
        if success:
            return Response({
                'message': f'Zoom meeting deleted successfully for {webinar.webinar_type} webinar'
            })
        else:
            return Response({
                'error': 'Failed to delete Zoom meeting'
            }, status=status.HTTP_400_BAD_REQUEST)
    
    except Exception as e:
        logger.error(f"Error deleting Zoom meeting {meeting_id}: {str(e)}")
        return Response({
            'error': str(e)
        }, status=status.HTTP_400_BAD_REQUEST)
# apps/integrations/views.py

def calculate_similarity_score(str1, str2):
    """
    Calculate similarity between two strings
    Returns score from 0-100
    """
    if not str1 or not str2:
        return 0
    
    # Normalize strings
    s1 = str1.lower().strip()
    s2 = str2.lower().strip()
    
    # Exact match
    if s1 == s2:
        return 100
    
    # Contains match
    if s1 in s2 or s2 in s1:
        return 90
    
    # Word overlap
    words1 = set(re.findall(r'\w+', s1))
    words2 = set(re.findall(r'\w+', s2))
    
    if words1 and words2:
        common_words = words1.intersection(words2)
        word_overlap_score = (len(common_words) / max(len(words1), len(words2))) * 80
    else:
        word_overlap_score = 0
    
    # Sequence matcher
    sequence_score = SequenceMatcher(None, s1, s2).ratio() * 70
    
    # Return best score
    return max(word_overlap_score, sequence_score)


@api_view(['GET'])
@permission_classes([permissions.IsAuthenticated])
def list_zoom_cloud_recordings(request):
    """
    List Zoom cloud recordings from the user's account with smart matching
    """
    try:
        from_date = request.query_params.get(
            'from_date', 
            (timezone.now() - timedelta(days=90)).strftime('%Y-%m-%d')
        )
        to_date = request.query_params.get(
            'to_date', 
            timezone.now().strftime('%Y-%m-%d')
        )
        page_size = request.query_params.get('page_size', 50)
        topic = request.query_params.get('topic', '')  # For smart matching
        min_score = int(request.query_params.get('min_score', 0))  # Minimum similarity score
        
        logger.info("📹 Listing Zoom cloud recordings")
        logger.info(f"- From: {from_date}")
        logger.info(f"- To: {to_date}")
        logger.info(f"- Topic filter: {topic}")
        logger.info(f"- Min score: {min_score}")
        
        # Get credentials
        from .models import ZoomCredentials
        credentials = ZoomCredentials.objects.filter(is_active=True).first()
        
        if not credentials:
            logger.error("❌ No active Zoom credentials found")
            return Response({
                'success': False,
                'error': 'No active Zoom credentials found. Please configure Zoom integration.',
                'recordings': []
            }, status=status.HTTP_400_BAD_REQUEST)
        
        logger.info(f"✅ Found credentials: {credentials.name}")
        
        # Validate credentials fields
        if not all([credentials.client_id, credentials.client_secret, credentials.account_id]):
            logger.error("❌ Incomplete Zoom credentials")
            return Response({
                'success': False,
                'error': 'Zoom credentials are incomplete. Please check client_id, client_secret, and account_id.',
                'recordings': []
            }, status=status.HTTP_400_BAD_REQUEST)
        
        # Get access token
        logger.info("🔑 Getting Zoom access token...")
        
        try:
            token_url = f'https://zoom.us/oauth/token?grant_type=account_credentials&account_id={credentials.account_id}'
            
            # Create Basic Auth header
            auth_string = f'{credentials.client_id}:{credentials.client_secret}'
            auth_value = base64.b64encode(auth_string.encode()).decode()
            
            token_headers = {
                'Authorization': f'Basic {auth_value}',
                'Content-Type': 'application/x-www-form-urlencoded',
            }
            
            token_response = requests.post(
                token_url, 
                headers=token_headers, 
                timeout=30
            )
            
            logger.info(f"Token response status: {token_response.status_code}")
            
            if token_response.status_code != 200:
                logger.error(f"❌ Token request failed: {token_response.text}")
                return Response({
                    'success': False,
                    'error': f'Failed to get Zoom access token: {token_response.text}',
                    'recordings': []
                }, status=status.HTTP_400_BAD_REQUEST)
            
            token_data = token_response.json()
            access_token = token_data.get('access_token')
            
            if not access_token:
                logger.error("❌ No access token in response")
                return Response({
                    'success': False,
                    'error': 'Failed to obtain access token from Zoom',
                    'recordings': []
                }, status=status.HTTP_400_BAD_REQUEST)
            
            logger.info("✅ Got access token successfully")
            
        except requests.exceptions.RequestException as e:
            logger.error(f"❌ Request error getting token: {str(e)}")
            return Response({
                'success': False,
                'error': f'Network error: {str(e)}',
                'recordings': []
            }, status=status.HTTP_400_BAD_REQUEST)
        
        # List cloud recordings
        logger.info("📊 Fetching cloud recordings...")
        
        try:
            recordings_url = 'https://api.zoom.us/v2/users/me/recordings'
            
            recordings_headers = {
                'Authorization': f'Bearer {access_token}',
                'Content-Type': 'application/json',
            }
            
            recordings_params = {
                'from': from_date,
                'to': to_date,
                'page_size': int(page_size),
                'trash_type': 'meeting_recordings'
            }
            
            recordings_response = requests.get(
                recordings_url,
                headers=recordings_headers,
                params=recordings_params,
                timeout=30
            )
            
            logger.info(f"Recordings response status: {recordings_response.status_code}")
            
            if recordings_response.status_code != 200:
                logger.error(f"❌ Recordings request failed: {recordings_response.text}")
                return Response({
                    'success': False,
                    'error': f'Zoom API error: {recordings_response.text}',
                    'recordings': []
                }, status=status.HTTP_400_BAD_REQUEST)
            
            recordings_data = recordings_response.json()
            
            logger.info(f"📊 Raw recordings response: {len(recordings_data.get('meetings', []))} meetings")
            
        except requests.exceptions.RequestException as e:
            logger.error(f"❌ Request error fetching recordings: {str(e)}")
            return Response({
                'success': False,
                'error': f'Network error: {str(e)}',
                'recordings': []
            }, status=status.HTTP_400_BAD_REQUEST)
        
        # Format recordings with similarity scoring
        formatted_recordings = []
        
        for meeting in recordings_data.get('meetings', []):
            meeting_id = str(meeting.get('id', ''))
            meeting_uuid = meeting.get('uuid', '')
            meeting_topic = meeting.get('topic', 'Untitled Recording')
            meeting_start = meeting.get('start_time', '')
            meeting_duration = meeting.get('duration', 0)
            host_email = meeting.get('host_email', '')
            host_id = meeting.get('host_id', '')
            
            # Calculate similarity score if topic filter provided
            similarity_score = 0
            match_reasons = []
            
            if topic:
                similarity_score = calculate_similarity_score(topic, meeting_topic)
                
                # Add match reasons
                if similarity_score >= 90:
                    match_reasons.append('Exact or near-exact match')
                elif similarity_score >= 70:
                    match_reasons.append('Strong similarity in title')
                elif similarity_score >= 50:
                    match_reasons.append('Moderate similarity')
                elif similarity_score >= 30:
                    match_reasons.append('Some common words')
                
                # Skip if below minimum score
                if similarity_score < min_score:
                    continue
            
            # Process recording files
            for rec_file in meeting.get('recording_files', []):
                # Only include video recordings
                file_type = rec_file.get('file_type', '')
                
                if file_type not in ['MP4', 'M4A']:
                    continue
                
                play_url = rec_file.get('play_url')
                share_url = rec_file.get('share_url')
                download_url = rec_file.get('download_url')
                
                if not (play_url or share_url or download_url):
                    continue
                
                # Parse dates safely
                recorded_date = ''
                recorded_time = ''
                
                if meeting_start:
                    try:
                        start_dt = datetime.fromisoformat(meeting_start.replace('Z', '+00:00'))
                        recorded_date = start_dt.strftime('%b %d, %Y')
                        recorded_time = start_dt.strftime('%I:%M %p')
                    except Exception as e:
                        logger.warning(f"⚠️ Error parsing date {meeting_start}: {e}")
                        recorded_date = meeting_start
                        recorded_time = ''
                
                recording_obj = {
                    'id': meeting_id,
                    'recording_id': rec_file.get('id', ''),
                    'uuid': meeting_uuid,
                    'topic': meeting_topic,
                    'start_time': meeting_start,
                    'duration': meeting_duration,
                    'recording_start': rec_file.get('recording_start', ''),
                    'recording_end': rec_file.get('recording_end', ''),
                    'file_type': file_type,
                    'file_size': rec_file.get('file_size', 0),
                    'file_size_mb': round(rec_file.get('file_size', 0) / (1024 * 1024), 2),
                    'file_extension': rec_file.get('file_extension', ''),
                    'play_url': play_url or share_url or download_url,
                    'share_url': share_url,
                    'download_url': download_url,
                    'recording_type': rec_file.get('recording_type', 'shared_screen_with_speaker_view'),
                    'status': rec_file.get('status', 'completed'),
                    'host_email': host_email,
                    'host_id': host_id,
                    'recorded_date': recorded_date,
                    'recorded_time': recorded_time,
                    # Similarity matching fields
                    'similarity_score': int(similarity_score),
                    'match_reasons': match_reasons,
                }
                
                formatted_recordings.append(recording_obj)
        
        # Sort by similarity score (highest first) if topic provided
        if topic:
            formatted_recordings.sort(key=lambda x: x['similarity_score'], reverse=True)
            logger.info(f"✅ Found {len(formatted_recordings)} matching recordings (scores >= {min_score})")
        else:
            logger.info(f"✅ Found {len(formatted_recordings)} cloud recordings")
        
        return Response({
            'success': True,
            'count': len(formatted_recordings),
            'recordings': formatted_recordings,
            'total_meetings': recordings_data.get('total_records', 0),
            'from_date': from_date,
            'to_date': to_date,
            'filtered_by_topic': bool(topic),
            'search_topic': topic if topic else None
        })
        
    except Exception as e:
        logger.error(f"❌ Unexpected error listing recordings: {str(e)}")
        logger.exception("Full traceback:")
        return Response({
            'success': False,
            'error': f'Internal server error: {str(e)}',
            'recordings': []
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['POST'])
@permission_classes([permissions.IsAuthenticated])
def link_recording_to_webinar(request):
    """
    Link a Zoom cloud recording to a webinar
    """
    try:
        webinar_id = request.data.get('webinar_id')
        recording_id = request.data.get('recording_id')
        recording_url = request.data.get('recording_url')  # play_url or share_url
        meeting_id = request.data.get('meeting_id')
        topic = request.data.get('topic', '')
        duration = request.data.get('duration', 0)
        
        logger.info(f"🔗 Linking recording {recording_id} to webinar {webinar_id}")
        
        if not all([webinar_id, recording_url]):
            return Response({
                'success': False,
                'error': 'Missing required fields: webinar_id, recording_url'
            }, status=status.HTTP_400_BAD_REQUEST)
        
        # Get webinar
        from apps.webinars.models import Webinar
        webinar = get_object_or_404(Webinar, id=webinar_id)
        
        # Check webinar type
        if webinar.webinar_type != 'recorded':
            return Response({
                'success': False,
                'error': f'Can only link recordings to recorded webinars, not {webinar.webinar_type} webinars'
            }, status=status.HTTP_400_BAD_REQUEST)
        
        # Check permissions
        if not check_webinar_permissions(request.user, webinar):
            return Response({
                'success': False,
                'error': 'Permission denied'
            }, status=status.HTTP_403_FORBIDDEN)
        
        # Update webinar with recording details
        webinar.zoom_url = recording_url
        webinar.zoom_recording_id = recording_id
        
        # Update duration if provided and webinar doesn't have one
        if duration and not webinar.duration:
            webinar.duration = duration
        
        webinar.save(update_fields=['zoom_url', 'zoom_recording_id', 'duration'])
        
        logger.info(f"✅ Successfully linked recording to webinar {webinar.webinar_id}")
        
        # Create ZoomRecording entry for tracking
        from .models import ZoomRecording
        recording, created = ZoomRecording.objects.get_or_create(
            recording_id=recording_id,
            defaults={
                'meeting_id': meeting_id,
                'topic': topic or webinar.title,
                'status': 'completed',
                'play_url': recording_url,
            }
        )
        
        return Response({
            'success': True,
            'message': 'Recording linked successfully',
            'webinar': {
                'id': webinar.id,
                'webinar_id': webinar.webinar_id,
                'title': webinar.title,
                'zoom_url': webinar.zoom_url,
                'zoom_recording_id': webinar.zoom_recording_id
            }
        })
        
    except Exception as e:
        logger.error(f"❌ Error linking recording: {str(e)}")
        logger.exception("Full traceback:")
        return Response({
            'success': False,
            'error': str(e)
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

# @api_view(['GET'])
# @permission_classes([permissions.IsAuthenticated])
# def search_zoom_meetings(request):
#     """
#     Search for existing Zoom meetings/webinars matching criteria
    
#     Query Parameters:
#         - start_date: ISO format datetime (required) - scheduled date to search around
#         - topic: Topic/title to match (optional)
#         - duration: Duration in minutes (optional)
#         - days_range: Number of days before/after to search (default: 3)
    
#     Returns:
#         List of matching meetings with match scores
#     """
#     try:
#         # Get query parameters
#         start_date = request.query_params.get('start_date')
#         topic = request.query_params.get('topic', '')
#         duration = request.query_params.get('duration')
#         days_range = int(request.query_params.get('days_range', 3))
        
#         # Validate required parameters
#         if not start_date:
#             return Response({
#                 'success': False,
#                 'error': 'start_date is required',
#                 'message': 'Please provide a start_date parameter',
#                 'meetings': []
#             }, status=status.HTTP_400_BAD_REQUEST)
        
#         # Convert duration to int if provided
#         if duration:
#             try:
#                 duration = int(duration)
#             except ValueError:
#                 duration = None
        
#         logger.info(f"🔍 Search request from {request.user.username}:")
#         logger.info(f"   - Start date: {start_date}")
#         logger.info(f"   - Topic: {topic}")
#         logger.info(f"   - Duration: {duration}")
#         logger.info(f"   - Days range: {days_range}")
        
#         # Initialize Zoom API service
#         zoom_api = ZoomAPIService()
        
#         # Search for matching meetings
#         matching_meetings = zoom_api.search_meetings(
#             scheduled_date=start_date,
#             topic=topic,
#             duration=duration,
#             days_range=days_range
#         )
        
#         # Format response with enriched data
#         formatted_meetings = []
#         for meeting in matching_meetings:
#             formatted_meetings.append({
#                 'id': meeting['id'],
#                 'topic': meeting['topic'],
#                 'start_time': meeting['start_time'],
#                 'duration': meeting['duration'],
#                 'timezone': meeting.get('timezone', 'UTC'),
#                 'join_url': meeting['join_url'],
#                 'start_url': meeting.get('start_url', ''),
#                 'host_email': meeting.get('host_email', ''),
#                 'host_name': meeting.get('host_email', '').split('@')[0] if meeting.get('host_email') else '',
#                 'type': meeting['type'],
#                 'match_score': meeting.get('match_score', 0),
#                 'match_reasons': meeting.get('match_reasons', []),
#                 'time_diff_hours': meeting.get('time_diff_hours', 0),
#                 'agenda': meeting.get('agenda', ''),
#                 'scheduled_date_formatted': meeting.get('scheduled_date_formatted', '')
#             })
        
#         logger.info(f"✅ Search completed: {len(formatted_meetings)} meetings found")
        
#         return Response({
#             'success': True,
#             'count': len(formatted_meetings),
#             'meetings': formatted_meetings,
#             'search_criteria': {
#                 'start_date': start_date,
#                 'topic': topic,
#                 'duration': duration,
#                 'days_range': days_range
#             }
#         })
        
#     except ValidationError as e:
#         logger.error(f"❌ Validation error in meeting search: {str(e)}")
#         return Response({
#             'success': False,
#             'error': 'Validation error',
#             'message': str(e),
#             'meetings': []
#         }, status=status.HTTP_400_BAD_REQUEST)
    
#     except Exception as e:
#         logger.error(f"❌ Error searching Zoom meetings: {str(e)}")
#         logger.exception("Full traceback:")
#         return Response({
#             'success': False,
#             'error': 'Search failed',
#             'message': str(e),
#             'meetings': []
#         }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

# apps/integrations/views.py

@api_view(['GET'])
@permission_classes([permissions.IsAuthenticated])
def search_zoom_meetings(request):
    """
    Search for existing Zoom meetings matching criteria
    Uses simple direct API approach that actually works
    """
    try:
        # Get query parameters
        start_date = request.query_params.get('start_date')
        topic = request.query_params.get('topic', '')
        duration = request.query_params.get('duration')
        days_range = int(request.query_params.get('days_range', 3))
        
        # Validate required parameters
        if not start_date:
            return Response({
                'success': False,
                'error': 'start_date is required',
                'message': 'Please provide a start_date parameter',
                'meetings': []
            }, status=status.HTTP_400_BAD_REQUEST)
        
        # Convert duration to int if provided
        if duration:
            try:
                duration = int(duration)
            except ValueError:
                duration = None
        
        logger.info(f"🔍 Search request:")
        logger.info(f"   - Start date: {start_date}")
        logger.info(f"   - Topic: {topic}")
        logger.info(f"   - Duration: {duration}")
        logger.info(f"   - Days range: {days_range}")
        
        # Get credentials from database
        from .models import ZoomCredentials
        credentials = ZoomCredentials.objects.filter(is_active=True).first()
        
        if not credentials:
            return Response({
                'success': False,
                'error': 'No active Zoom credentials found',
                'meetings': []
            }, status=status.HTTP_400_BAD_REQUEST)
        
        # Step 1: Get access token (working method)
        logger.info("🔐 Getting access token...")
        token_url = f"https://zoom.us/oauth/token?grant_type=account_credentials&account_id={credentials.account_id}"
        auth_value = base64.b64encode(
            f"{credentials.client_id}:{credentials.client_secret}".encode()
        ).decode()
        
        token_headers = {
            "Authorization": f"Basic {auth_value}",
            "Content-Type": "application/x-www-form-urlencoded",
        }
        
        token_response = requests.post(token_url, headers=token_headers, timeout=30)
        token_response.raise_for_status()
        access_token = token_response.json()["access_token"]
        
        logger.info(f"✅ Got access token")
        
        # Step 2: List ALL meetings (no date filter - Zoom doesn't support it well)
        logger.info("📋 Listing all meetings...")
        meetings_url = "https://api.zoom.us/v2/users/me/meetings"
        meetings_headers = {"Authorization": f"Bearer {access_token}"}
        meetings_params = {"page_size": 300}
        
        meetings_response = requests.get(
            meetings_url, 
            headers=meetings_headers, 
            params=meetings_params,
            timeout=30
        )
        meetings_response.raise_for_status()
        
        meetings_data = meetings_response.json()
        all_meetings = meetings_data.get("meetings", [])
        
        logger.info(f"✅ Found {len(all_meetings)} total meetings")
        
        # Step 3: Filter and score meetings based on search criteria
        from datetime import datetime, timedelta
        
        # Parse target date
        if isinstance(start_date, str):
            target_date = datetime.fromisoformat(start_date.replace('Z', '+00:00'))
        else:
            target_date = start_date
        
        # Remove timezone for comparison
        if hasattr(target_date, 'tzinfo') and target_date.tzinfo:
            target_date = target_date.replace(tzinfo=None)
        
        logger.info(f"🎯 Target date: {target_date}")
        
        # Score and filter meetings
        matching_meetings = []
        
        for meeting in all_meetings:
            try:
                # Parse meeting start time
                meeting_start_str = meeting.get('start_time')
                if not meeting_start_str:
                    continue
                
                meeting_start = datetime.fromisoformat(meeting_start_str.replace('Z', '+00:00'))
                if hasattr(meeting_start, 'tzinfo') and meeting_start.tzinfo:
                    meeting_start = meeting_start.replace(tzinfo=None)
                
                # Calculate time difference in hours
                time_diff_hours = abs((meeting_start - target_date).total_seconds() / 3600)
                time_diff_days = time_diff_hours / 24
                
                # Skip if outside date range
                if time_diff_days > days_range:
                    continue
                
                # Calculate match score
                match_score = 0
                reasons = []
                
                # Score: Topic match
                meeting_topic = meeting.get('topic', '').lower()
                if topic and len(topic) > 3:
                    topic_lower = topic.lower()
                    
                    if topic_lower == meeting_topic:
                        match_score += 100
                        reasons.append('exact_topic_match')
                    elif topic_lower in meeting_topic or meeting_topic in topic_lower:
                        match_score += 60
                        reasons.append('topic_match')
                    else:
                        # Word overlap
                        topic_words = set(topic_lower.split())
                        meeting_words = set(meeting_topic.split())
                        common_words = topic_words & meeting_words
                        if len(common_words) >= 2:
                            match_score += 40
                            reasons.append('topic_word_match')
                
                # Score: Time match
                if time_diff_hours <= 1:
                    match_score += 50
                    reasons.append('exact_time_match')
                elif time_diff_hours <= 3:
                    match_score += 30
                    reasons.append('close_time_match')
                elif time_diff_hours <= 6:
                    match_score += 15
                    reasons.append('same_day_match')
                
                # Score: Duration match
                meeting_duration = meeting.get('duration', 0)
                if duration and meeting_duration:
                    duration_diff = abs(meeting_duration - duration)
                    if duration_diff == 0:
                        match_score += 20
                        reasons.append('exact_duration_match')
                    elif duration_diff <= 15:
                        match_score += 10
                        reasons.append('similar_duration')
                
                # Score: Same date bonus
                if meeting_start.date() == target_date.date():
                    match_score += 10
                    reasons.append('same_date')
                
                # Only include if has some relevance (minimum score of 10)
                if match_score >= 10:
                    matching_meetings.append({
                        'id': str(meeting.get('id')),
                        'topic': meeting.get('topic'),
                        'start_time': meeting.get('start_time'),
                        'duration': meeting.get('duration'),
                        'timezone': meeting.get('timezone'),
                        'join_url': meeting.get('join_url'),
                        'start_url': meeting.get('start_url', ''),
                        'host_email': meeting.get('host_email', ''),
                        'host_name': meeting.get('host_email', '').split('@')[0] if meeting.get('host_email') else '',
                        'type': 'meeting',
                        'match_score': match_score,
                        'match_reasons': reasons,
                        'time_diff_hours': round(time_diff_hours, 2),
                        'agenda': meeting.get('agenda', ''),
                        'scheduled_date_formatted': meeting_start.strftime('%Y-%m-%d %H:%M')
                    })
                
            except Exception as e:
                logger.warning(f"⚠️ Error processing meeting {meeting.get('id')}: {e}")
                continue
        
        # Sort by match score (highest first)
        matching_meetings.sort(key=lambda x: x['match_score'], reverse=True)
        
        logger.info(f"✅ Found {len(matching_meetings)} matching meetings")
        
        # Log top matches
        for i, meeting in enumerate(matching_meetings[:3], 1):
            logger.info(f"   {i}. {meeting['topic']} (score: {meeting['match_score']}, reasons: {meeting['match_reasons']})")
        
        return Response({
            'success': True,
            'count': len(matching_meetings),
            'meetings': matching_meetings,
            'search_criteria': {
                'start_date': start_date,
                'topic': topic,
                'duration': duration,
                'days_range': days_range
            }
        })
        
    except requests.exceptions.HTTPError as e:
        error_msg = f"HTTP Error: {str(e)}"
        error_details = ""
        
        if hasattr(e, 'response') and e.response is not None:
            try:
                error_data = e.response.json()
                error_details = f"Code: {error_data.get('code')}, Message: {error_data.get('message')}"
            except:
                error_details = e.response.text
        
        logger.error(f"❌ {error_msg}")
        logger.error(f"❌ Details: {error_details}")
        
        return Response({
            'success': False,
            'error': error_msg,
            'message': error_details,
            'meetings': []
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
        
    except Exception as e:
        logger.error(f"❌ Error searching Zoom meetings: {str(e)}")
        logger.exception("Full traceback:")
        
        return Response({
            'success': False,
            'error': 'Search failed',
            'message': str(e),
            'meetings': []
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

@api_view(['GET'])
@permission_classes([permissions.IsAuthenticated])
def test_list_all_zoom_meetings(request):
    """
    Test endpoint using your exact working code pattern
    Lists all Zoom meetings directly without complicated logic
    """
    try:
        logger.info("🧪 Testing Zoom API with simple method")
        
        # Get credentials from database
        from .models import ZoomCredentials
        credentials = ZoomCredentials.objects.filter(is_active=True).first()
        
        if not credentials:
            return Response({
                'success': False,
                'error': 'No active Zoom credentials found',
                'meetings': []
            }, status=status.HTTP_400_BAD_REQUEST)
        
        # Step 1: Get access token (your working method)
        logger.info("🔐 Getting access token...")
        token_url = f"https://zoom.us/oauth/token?grant_type=account_credentials&account_id={credentials.account_id}"
        auth_value = base64.b64encode(
            f"{credentials.client_id}:{credentials.client_secret}".encode()
        ).decode()
        
        token_headers = {
            "Authorization": f"Basic {auth_value}",
            "Content-Type": "application/x-www-form-urlencoded",
        }
        
        token_response = requests.post(token_url, headers=token_headers, timeout=30)
        token_response.raise_for_status()
        access_token = token_response.json()["access_token"]
        
        logger.info(f"✅ Got access token: {access_token[:20]}...")
        
        # Step 2: List all meetings (your working method)
        logger.info("📋 Listing meetings...")
        meetings_url = "https://api.zoom.us/v2/users/me/meetings"
        meetings_headers = {"Authorization": f"Bearer {access_token}"}
        meetings_params = {"page_size": 300}
        
        meetings_response = requests.get(
            meetings_url, 
            headers=meetings_headers, 
            params=meetings_params,
            timeout=30
        )
        meetings_response.raise_for_status()
        
        meetings_data = meetings_response.json()
        meetings = meetings_data.get("meetings", [])
        
        logger.info(f"✅ Found {len(meetings)} meetings")
        
        # Format response
        formatted_meetings = []
        for meeting in meetings:
            formatted_meetings.append({
                'id': str(meeting.get('id')),
                'topic': meeting.get('topic'),
                'type': 'meeting',
                'start_time': meeting.get('start_time'),
                'duration': meeting.get('duration'),
                'timezone': meeting.get('timezone'),
                'join_url': meeting.get('join_url'),
                'host_email': meeting.get('host_email', ''),
                'status': meeting.get('status', ''),
                'created_at': meeting.get('created_at', '')
            })
            
            # Log each meeting
            logger.info(f"   - {meeting.get('topic')} | {meeting.get('start_time')}")
        
        return Response({
            'success': True,
            'message': f'Found {len(meetings)} meetings in your Zoom account',
            'count': len(meetings),
            'meetings': formatted_meetings
        })
        
    except requests.exceptions.HTTPError as e:
        error_msg = f"HTTP Error: {str(e)}"
        error_details = ""
        
        if hasattr(e, 'response') and e.response is not None:
            try:
                error_data = e.response.json()
                error_details = f"Code: {error_data.get('code')}, Message: {error_data.get('message')}"
            except:
                error_details = e.response.text
        
        logger.error(f"❌ {error_msg}")
        logger.error(f"❌ Details: {error_details}")
        
        return Response({
            'success': False,
            'error': error_msg,
            'details': error_details,
            'meetings': []
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
        
    except Exception as e:
        logger.error(f"❌ Unexpected error: {str(e)}")
        logger.exception("Full traceback:")
        
        return Response({
            'success': False,
            'error': str(e),
            'meetings': []
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
# NEW: Link existing Zoom meeting to webinar
@api_view(['POST'])
@permission_classes([permissions.IsAuthenticated])
def link_existing_zoom_meeting(request):
    """
    Link an existing Zoom meeting to a webinar
    
    Request Body:
        - webinar_id: ID of the webinar
        - zoom_meeting_id: ID of existing Zoom meeting to link
        - zoom_join_url: Join URL of the Zoom meeting
        - zoom_start_url: Start URL of the Zoom meeting (optional)
    """
    try:
        webinar_id = request.data.get('webinar_id')
        zoom_meeting_id = request.data.get('zoom_meeting_id')
        zoom_join_url = request.data.get('zoom_join_url')
        zoom_start_url = request.data.get('zoom_start_url', '')
        
        # Validate required fields
        if not all([webinar_id, zoom_meeting_id, zoom_join_url]):
            return Response({
                'error': 'webinar_id, zoom_meeting_id, and zoom_join_url are required'
            }, status=status.HTTP_400_BAD_REQUEST)
        
        # Get webinar
        webinar = get_object_or_404(Webinar, id=webinar_id)
        
        # Check webinar type
        if webinar.webinar_type != 'live':
            return Response({
                'error': f'Can only link Zoom meetings to live webinars, not {webinar.webinar_type} webinars'
            }, status=status.HTTP_400_BAD_REQUEST)
        
        # Check permissions
        if not _check_webinar_permissions(request.user, webinar):
            return Response({
                'error': 'Only the instructor, admin, or webinar owner can link Zoom meetings'
            }, status=status.HTTP_403_FORBIDDEN)
        
        # Check if webinar already has a Zoom meeting
        if _webinar_has_zoom_meeting(webinar):
            return Response({
                'error': 'Webinar already has a Zoom meeting linked. Please delete it first.'
            }, status=status.HTTP_400_BAD_REQUEST)
        
        # Get meeting details from Zoom API
        zoom_api = ZoomAPIService()
        meeting_details = zoom_api.get_meeting(zoom_meeting_id)
        
        if not meeting_details:
            return Response({
                'error': 'Could not retrieve meeting details from Zoom'
            }, status=status.HTTP_400_BAD_REQUEST)
        
        # Create ZoomMeeting record for existing meeting
        zoom_meeting = ZoomMeeting.objects.create(
            webinar=webinar,
            zoom_meeting_id=str(zoom_meeting_id),
            uuid=meeting_details.get('uuid', ''),
            host_id=meeting_details.get('host_id', ''),
            topic=meeting_details.get('topic', webinar.title),
            agenda=meeting_details.get('agenda', ''),
            meeting_type=meeting_details.get('type', 2),
            start_time=webinar.scheduled_date,
            duration=webinar.duration,
            timezone=webinar.timezone or "Asia/Kolkata",
            password=meeting_details.get('password', ''),
            join_url=zoom_join_url,
            start_url=zoom_start_url or meeting_details.get('start_url', ''),
            
            # Get settings from existing meeting
            waiting_room=meeting_details.get('settings', {}).get('waiting_room', True),
            join_before_host=meeting_details.get('settings', {}).get('join_before_host', False),
            mute_upon_entry=meeting_details.get('settings', {}).get('mute_upon_entry', True),
            auto_recording=meeting_details.get('settings', {}).get('auto_recording', 'none'),
            
            # Mark as linked to existing meeting
            is_linked_existing=True,
            created_by=request.user
        )
        
        logger.info(f"✅ Linked existing Zoom meeting {zoom_meeting_id} to webinar {webinar.webinar_id}")
        
        # Serialize response
        response_serializer = ZoomMeetingSerializer(zoom_meeting)
        
        return Response({
            'message': 'Successfully linked existing Zoom meeting',
            'linked': True,
            'data': response_serializer.data
        }, status=status.HTTP_201_CREATED)
        
    except Exception as e:
        logger.error(f"❌ Error linking existing Zoom meeting: {str(e)}")
        logger.exception("Full traceback:")
        return Response({
            'error': 'Failed to link existing meeting',
            'details': str(e)
        }, status=status.HTTP_400_BAD_REQUEST)


# NEW: Get webinar's existing Zoom meeting suggestions
@api_view(['GET'])
@permission_classes([permissions.IsAuthenticated])
def get_webinar_meeting_suggestions(request, webinar_id):
    """
    Get existing Zoom meeting suggestions for a specific webinar
    
    Automatically searches for meetings matching the webinar's:
    - Scheduled date (±3 days)
    - Title/topic
    - Duration
    """
    try:
        webinar = get_object_or_404(Webinar, id=webinar_id)
        
        # Check webinar type
        if webinar.webinar_type != 'live':
            return Response({
                'success': False,
                'error': f'Meeting suggestions only available for live webinars',
                'suggestions': []
            })
        
        # Check permissions
        if not _check_webinar_permissions(request.user, webinar):
            return Response({
                'error': 'Permission denied'
            }, status=status.HTTP_403_FORBIDDEN)
        
        # Check if webinar already has a Zoom meeting
        if _webinar_has_zoom_meeting(webinar):
            return Response({
                'success': True,
                'has_existing': True,
                'message': 'Webinar already has a Zoom meeting linked',
                'suggestions': []
            })
        
        # Search for matching meetings
        zoom_service = ZoomWebinarService()
        suggestions = zoom_service.search_existing_meetings(webinar, days_range=3)
        
        logger.info(f"📋 Found {len(suggestions)} meeting suggestions for webinar {webinar.webinar_id}")
        
        return Response({
            'success': True,
            'has_existing': False,
            'count': len(suggestions),
            'suggestions': suggestions,
            'webinar': {
                'id': webinar.id,
                'webinar_id': webinar.webinar_id,
                'title': webinar.title,
                'scheduled_date': webinar.scheduled_date,
                'duration': webinar.duration,
                'type': webinar.webinar_type
            }
        })
        
    except Exception as e:
        logger.error(f"❌ Error getting meeting suggestions for webinar {webinar_id}: {str(e)}")
        return Response({
            'success': False,
            'error': 'Failed to get suggestions',
            'details': str(e),
            'suggestions': []
        }, status=status.HTTP_400_BAD_REQUEST)

# FIXED: Meeting list views with proper user relationships
class ZoomMeetingListView(generics.ListAPIView):
    """List user's Zoom meetings (optimized for performance)"""
    
    serializer_class = ZoomMeetingListSerializer
    permission_classes = [permissions.IsAuthenticated]
    ordering = ['-start_time']
    
    def get_queryset(self):
        if self.request.user.is_staff:
            return ZoomMeeting.objects.select_related('webinar', 'created_by').all()
        
        # FIXED: Filter by meetings created by user OR for webinars they own
        return ZoomMeeting.objects.select_related('webinar', 'created_by').filter(
            models.Q(created_by=self.request.user) |
            models.Q(webinar__speaker__user=self.request.user)
        )

class ZoomWebinarListView(generics.ListAPIView):
    """List user's Zoom webinars (optimized for performance)"""
    
    serializer_class = ZoomWebinarListSerializer
    permission_classes = [permissions.IsAuthenticated]
    ordering = ['-start_time']
    
    def get_queryset(self):
        if self.request.user.is_staff:
            return ZoomWebinar.objects.select_related('webinar', 'created_by').all()
        
        # FIXED: Filter by webinars created by user OR for webinars they own
        return ZoomWebinar.objects.select_related('webinar', 'created_by').filter(
            models.Q(created_by=self.request.user) |
            models.Q(webinar__speaker__user=self.request.user)
        )

# FIXED: Recording list view with proper user relationships
class ZoomRecordingListView(generics.ListAPIView):
    """List Zoom recordings"""
    
    serializer_class = ZoomRecordingSerializer
    permission_classes = [permissions.IsAuthenticated]
    ordering = ['-recording_start']
    
    def get_queryset(self):
        if self.request.user.is_staff:
            return ZoomRecording.objects.select_related(
                'zoom_meeting', 'zoom_webinar'
            ).all()
        
        # FIXED: Get recordings for user's meetings/webinars using proper relationships
        user_meetings = ZoomMeeting.objects.filter(
            models.Q(created_by=self.request.user) |
            models.Q(webinar__speaker__user=self.request.user)
        )
        user_webinars = ZoomWebinar.objects.filter(
            models.Q(created_by=self.request.user) |
            models.Q(webinar__speaker__user=self.request.user)
        )
        
        return ZoomRecording.objects.select_related(
            'zoom_meeting', 'zoom_webinar'
        ).filter(
            models.Q(zoom_meeting__in=user_meetings) |
            models.Q(zoom_webinar__in=user_webinars)
        )

# ENHANCED: Recording sync with auto-conversion support
@api_view(['POST'])
@permission_classes([permissions.IsAuthenticated])
def sync_zoom_recordings(request, webinar_id):
    """Sync recordings for a specific live webinar with auto-conversion"""
    try:
        webinar = get_object_or_404(Webinar, id=webinar_id)
        
        # ADDED: Check webinar type
        if webinar.webinar_type != 'live':
            return Response({
                'error': f'Recording sync is only available for live webinars, not {webinar.webinar_type} webinars'
            }, status=status.HTTP_400_BAD_REQUEST)
        
        # FIXED: Check permissions with Speaker relationship
        if not _check_webinar_permissions(request.user, webinar):
            return Response({
                'error': 'Permission denied'
            }, status=status.HTTP_403_FORBIDDEN)
        
        zoom_service = ZoomWebinarService()
        recordings = zoom_service.sync_recordings(webinar)
        
        # ADDED: Auto-conversion support
        webinar_updated = False
        if recordings:
            webinar.has_recording = True
            
            # Auto-add recorded pricing if not exists
            if webinar.auto_convert_to_recorded and webinar.pricing_data:
                updated_pricing = False
                if not webinar.pricing_data.get('recorded_single_price') and webinar.pricing_data.get('live_single_price'):
                    webinar.pricing_data['recorded_single_price'] = webinar.pricing_data['live_single_price']
                    updated_pricing = True
                if not webinar.pricing_data.get('recorded_multi_price') and webinar.pricing_data.get('live_multi_price'):
                    webinar.pricing_data['recorded_multi_price'] = webinar.pricing_data['live_multi_price']
                    updated_pricing = True
                
                if updated_pricing:
                    logger.info(f"💰 Auto-added recorded pricing for webinar {webinar.webinar_id}")
            
            # Set zoom_url from primary recording
            if not webinar.zoom_url and recordings[0]:
                if hasattr(recordings[0], 'play_url') and recordings[0].play_url:
                    webinar.zoom_url = recordings[0].play_url
                elif hasattr(recordings[0], 'download_url') and recordings[0].download_url:
                    webinar.zoom_url = recordings[0].download_url
            
            webinar.save(update_fields=['has_recording', 'pricing_data', 'zoom_url'])
            webinar_updated = True
            
            logger.info(f"🎉 Auto-conversion completed for webinar {webinar.webinar_id}")
        
        serializer = ZoomRecordingSerializer(recordings, many=True)
        
        logger.info(f"Synced {len(recordings)} recordings for webinar {webinar_id}")
        
        return Response({
            'message': f'Successfully synced {len(recordings)} recordings',
            'count': len(recordings),
            'webinar_updated': webinar_updated,
            'auto_converted': webinar_updated and webinar.auto_convert_to_recorded,
            'recordings': serializer.data
        })
    
    except Exception as e:
        logger.error(f"Failed to sync recordings for webinar {webinar_id}: {str(e)}")
        return Response({
            'error': f'Failed to sync recordings: {str(e)}'
        }, status=status.HTTP_400_BAD_REQUEST)

# ADDED: Force recording check endpoint
@api_view(['POST'])
@permission_classes([permissions.IsAuthenticated])
def force_recording_check(request, webinar_id):
    """Force immediate recording check for completed live webinar"""
    try:
        webinar = get_object_or_404(Webinar, webinar_id=webinar_id)
        
        # Check webinar type and status
        if webinar.webinar_type != 'live':
            return Response({
                'error': f'Recording check is only available for live webinars'
            }, status=status.HTTP_400_BAD_REQUEST)
        
        if webinar.status != 'completed':
            return Response({
                'error': f'Recording check is only available for completed live webinars (current: {webinar.status})'
            }, status=status.HTTP_400_BAD_REQUEST)
        
        # FIXED: Check permissions
        if not _check_webinar_permissions(request.user, webinar):
            return Response({
                'error': 'Permission denied'
            }, status=status.HTTP_403_FORBIDDEN)
        
        # Force recording check
        zoom_service = ZoomWebinarService()
        recordings = zoom_service.force_recording_check(webinar)
        
        serializer = ZoomRecordingSerializer(recordings, many=True)
        
        return Response({
            'message': f'Force recording check completed - found {len(recordings)} recordings',
            'count': len(recordings),
            'webinar_updated': bool(recordings),
            'recordings': serializer.data
        })
    
    except Exception as e:
        logger.error(f"Error in force recording check for webinar {webinar_id}: {str(e)}")
        return Response({
            'error': f'Failed to check recordings: {str(e)}'
        }, status=status.HTTP_400_BAD_REQUEST)

# ADDED: Bulk recording sync for admins
@api_view(['POST'])
@permission_classes([permissions.IsAuthenticated, permissions.IsAdminUser])
def bulk_sync_recordings(request):
    """Bulk sync recordings for completed live webinars"""
    try:
        # Get completed live webinars that might have recordings
        webinars_to_sync = Webinar.objects.filter(
            webinar_type='live',
            status='completed',
            has_recording=False,
            auto_convert_to_recorded=True
        ).select_related('speaker__user')
        
        # Limit to prevent timeout
        limit = request.data.get('limit', 10)
        webinars_to_sync = webinars_to_sync[:limit]
        
        synced_count = 0
        recordings_found = 0
        webinars_updated = 0
        
        zoom_service = ZoomWebinarService()
        
        for webinar in webinars_to_sync:
            try:
                logger.info(f"🔍 Bulk syncing recordings for webinar {webinar.webinar_id}")
                recordings = zoom_service.force_recording_check(webinar)
                
                if recordings:
                    recordings_found += len(recordings)
                    webinars_updated += 1
                    logger.info(f"✅ Found {len(recordings)} recordings for {webinar.webinar_id}")
                
                synced_count += 1
                
            except Exception as e:
                logger.error(f"❌ Error syncing recordings for webinar {webinar.webinar_id}: {e}")
                continue
        
        return Response({
            'message': f'Bulk sync completed - processed {synced_count} webinars',
            'webinars_processed': synced_count,
            'webinars_updated': webinars_updated,
            'total_recordings_found': recordings_found,
            'remaining_webinars': max(0, webinars_to_sync.count() - synced_count)
        })
        
    except Exception as e:
        logger.error(f"❌ Error in bulk recording sync: {str(e)}")
        return Response({
            'error': 'Failed to perform bulk sync',
            'details': str(e)
        }, status=status.HTTP_400_BAD_REQUEST)

# ADDED: Get webinar status from Zoom
@api_view(['GET'])
@permission_classes([permissions.IsAuthenticated])
def get_webinar_zoom_status(request, webinar_id):
    """Get live webinar status from Zoom"""
    try:
        webinar = get_object_or_404(Webinar, webinar_id=webinar_id)
        
        if webinar.webinar_type != 'live':
            return Response({
                'error': f'Zoom status is only available for live webinars'
            }, status=status.HTTP_400_BAD_REQUEST)
        
        # Check permissions
        if not _check_webinar_permissions(request.user, webinar):
            return Response({
                'error': 'Permission denied'
            }, status=status.HTTP_403_FORBIDDEN)
        
        zoom_service = ZoomWebinarService()
        zoom_status = zoom_service.get_webinar_status(webinar)
        
        if zoom_status is None:
            return Response({
                'error': 'Unable to get Zoom status for this webinar'
            }, status=status.HTTP_404_NOT_FOUND)
        
        return Response({
            'webinar_id': webinar.webinar_id,
            'webinar_type': webinar.webinar_type,
            'local_status': webinar.status,
            'zoom_status': zoom_status,
            'has_zoom_meeting': bool(getattr(webinar, 'zoom_meeting_rel', None))
        })
        
    except Exception as e:
        logger.error(f"Error getting Zoom status for webinar {webinar_id}: {str(e)}")
        return Response({
            'error': f'Failed to get Zoom status: {str(e)}'
        }, status=status.HTTP_400_BAD_REQUEST)

# ENHANCED: Webhook handling with auto-conversion support
@csrf_exempt
@require_http_methods(["POST"])
def zoom_webhook(request):
    """Handle Zoom webhook events with auto-conversion support"""
    try:
        import json
        from django.utils import timezone
        
        # Parse request data
        try:
            event_data = json.loads(request.body.decode('utf-8'))
        except json.JSONDecodeError:
            logger.error("Invalid JSON in webhook request")
            return JsonResponse({'error': 'Invalid JSON'}, status=400)
        
        # Extract event information
        event_type = event_data.get('event', 'unknown')
        event_ts = event_data.get('event_ts', None)
        
        # Store webhook event for processing
        webhook_event = ZoomWebhookEvent.objects.create(
            event_type=event_type,
            event_ts=event_ts,
            event_data=event_data,
            source_ip=_get_client_ip(request),
            user_agent=request.META.get('HTTP_USER_AGENT', '')
        )
        
        logger.info(f"📨 Received Zoom webhook: {event_type} (ID: {webhook_event.id})")
        
        # Process webhook event
        try:
            _process_webhook_event(webhook_event)
        except Exception as processing_error:
            logger.error(f"❌ Error processing webhook {webhook_event.id}: {str(processing_error)}")
            webhook_event.processing_error = str(processing_error)
            webhook_event.processing_attempts += 1
            webhook_event.save()
        
        # Return quick response
        return JsonResponse({'status': 'received', 'event_id': webhook_event.id})
    
    except Exception as e:
        logger.error(f"❌ Unexpected error in webhook handler: {str(e)}")
        return JsonResponse({'error': 'Internal server error'}, status=500)

def _process_webhook_event(webhook_event: ZoomWebhookEvent):
    """Enhanced webhook event processing with auto-conversion"""
    try:
        event_type = webhook_event.event_type
        event_data = webhook_event.event_data
        
        if event_type == 'meeting.started':
            _handle_meeting_started(event_data)
        elif event_type == 'meeting.ended':
            _handle_meeting_ended(event_data)
        elif event_type == 'webinar.started':
            _handle_webinar_started(event_data)
        elif event_type == 'webinar.ended':
            _handle_webinar_ended(event_data)
        elif event_type == 'recording.completed':
            _handle_recording_completed(event_data)  # ENHANCED with auto-conversion
        else:
            logger.info(f"ℹ️ Unhandled webhook event type: {event_type}")
        
        # Mark as processed
        webhook_event.processed = True
        webhook_event.processed_at = timezone.now()
        webhook_event.save()
        
        logger.info(f"✅ Successfully processed webhook event {webhook_event.id}")
    
    except Exception as e:
        webhook_event.processing_error = str(e)
        webhook_event.processing_attempts += 1
        webhook_event.save()
        raise

def _handle_meeting_started(event_data: Dict[str, Any]):
    """Handle meeting started webhook"""
    meeting_data = event_data.get('payload', {}).get('object', {})
    meeting_id = str(meeting_data.get('id', ''))
    
    try:
        zoom_meeting = ZoomMeeting.objects.get(zoom_meeting_id=meeting_id)
        zoom_meeting.status = 'started'
        zoom_meeting.save()
        
        # Update webinar status
        if zoom_meeting.webinar:
            zoom_meeting.webinar.status = 'live'
            zoom_meeting.webinar.save(update_fields=['status'])
        
        logger.info(f"✅ Updated meeting {meeting_id} status to started")
    except ZoomMeeting.DoesNotExist:
        logger.warning(f"⚠️ Meeting {meeting_id} not found in database")

def _handle_meeting_ended(event_data: Dict[str, Any]):
    """Handle meeting ended webhook"""
    meeting_data = event_data.get('payload', {}).get('object', {})
    meeting_id = str(meeting_data.get('id', ''))
    
    try:
        zoom_meeting = ZoomMeeting.objects.get(zoom_meeting_id=meeting_id)
        zoom_meeting.status = 'ended'
        zoom_meeting.save()
        
        # Update webinar status (Bypassed: webinar completion controlled exclusively by 48-hour rule)
        # if zoom_meeting.webinar:
        #     zoom_meeting.webinar.status = 'completed'
        #     zoom_meeting.webinar.save(update_fields=['status'])
        #     
        #     # ADDED: Schedule recording check for auto-conversion
        #     if zoom_meeting.webinar.auto_convert_to_recorded:
        #         logger.info(f"📅 Scheduling auto-conversion check for webinar {zoom_meeting.webinar.webinar_id}")
        #         # Use the webinar's built-in recording check scheduling
        #         zoom_meeting.webinar._schedule_recording_check()
        
        logger.info(f"✅ Updated meeting {meeting_id} status to ended")
    except ZoomMeeting.DoesNotExist:
        logger.warning(f"⚠️ Meeting {meeting_id} not found in database")

def _handle_webinar_started(event_data: Dict[str, Any]):
    """Handle webinar started webhook"""
    webinar_data = event_data.get('payload', {}).get('object', {})
    webinar_id = str(webinar_data.get('id', ''))
    
    try:
        zoom_webinar = ZoomWebinar.objects.get(zoom_webinar_id=webinar_id)
        zoom_webinar.status = 'started'
        zoom_webinar.save()
        
        # Update webinar status
        if zoom_webinar.webinar:
            zoom_webinar.webinar.status = 'live'
            zoom_webinar.webinar.save(update_fields=['status'])
        
        logger.info(f"✅ Updated webinar {webinar_id} status to started")
    except ZoomWebinar.DoesNotExist:
        logger.warning(f"⚠️ Webinar {webinar_id} not found in database")

def _handle_webinar_ended(event_data: Dict[str, Any]):
    """Handle webinar ended webhook"""
    webinar_data = event_data.get('payload', {}).get('object', {})
    webinar_id = str(webinar_data.get('id', ''))
    
    try:
        zoom_webinar = ZoomWebinar.objects.get(zoom_webinar_id=webinar_id)
        zoom_webinar.status = 'ended'
        zoom_webinar.save()
        
        # Update webinar status (Bypassed: webinar completion controlled exclusively by 48-hour rule)
        # if zoom_webinar.webinar:
        #     zoom_webinar.webinar.status = 'completed'
        #     zoom_webinar.webinar.save(update_fields=['status'])
        #     
        #     # ADDED: Schedule recording check for auto-conversion
        #     if zoom_webinar.webinar.auto_convert_to_recorded:
        #         logger.info(f"📅 Scheduling auto-conversion check for webinar {zoom_webinar.webinar.webinar_id}")
        #         # Use the webinar's built-in recording check scheduling
        #         zoom_webinar.webinar._schedule_recording_check()
        
        logger.info(f"✅ Updated webinar {webinar_id} status to ended")
    except ZoomWebinar.DoesNotExist:
        logger.warning(f"⚠️ Webinar {webinar_id} not found in database")

def _handle_recording_completed(event_data: Dict[str, Any]):
    """ENHANCED: Handle recording completed webhook with auto-conversion"""
    recording_data = event_data.get('payload', {}).get('object', {})
    meeting_id = str(recording_data.get('id', ''))
    
    logger.info(f"📹 Processing recording completed webhook for meeting {meeting_id}")
    
    # Trigger recording sync for the meeting
    webinar = None
    try:
        zoom_meeting = ZoomMeeting.objects.get(zoom_meeting_id=meeting_id)
        webinar = zoom_meeting.webinar
    except ZoomMeeting.DoesNotExist:
        try:
            zoom_webinar = ZoomWebinar.objects.get(zoom_webinar_id=meeting_id)
            webinar = zoom_webinar.webinar
        except ZoomWebinar.DoesNotExist:
            logger.warning(f"⚠️ Meeting/Webinar {meeting_id} not found for recording sync")
            return
    
    if webinar and webinar.webinar_type == 'live':
        try:
            zoom_service = ZoomWebinarService()
            recordings = zoom_service.force_recording_check(webinar)
            
            logger.info(f"✅ Auto-conversion webhook processing: {len(recordings)} recordings found for {webinar.webinar_id}")
            
        except Exception as e:
            logger.error(f"❌ Error in webhook recording sync for {webinar.webinar_id}: {e}")
    else:
        logger.info(f"ℹ️ Skipping recording sync for non-live webinar")

class ZoomWebhookEventListView(generics.ListAPIView):
    """List Zoom webhook events (admin only)"""
    
    queryset = ZoomWebhookEvent.objects.all()
    serializer_class = ZoomWebhookEventSerializer
    permission_classes = [permissions.IsAuthenticated, permissions.IsAdminUser]
    ordering = ['-created_at']

class ZoomIntegrationLogListView(generics.ListAPIView):
    """List Zoom integration logs (admin only)"""
    
    queryset = ZoomIntegrationLog.objects.all()
    serializer_class = ZoomIntegrationLogSerializer
    permission_classes = [permissions.IsAuthenticated, permissions.IsAdminUser]
    ordering = ['-created_at']

# FIXED: Helper functions with proper Speaker relationships
def _check_webinar_permissions(user, webinar) -> bool:
    """Check if user has permission to manage webinar's Zoom integration"""
    return (
        user.is_staff or 
        user == webinar.speaker.user or  # FIXED: Use webinar.speaker.user instead of webinar.instructor
        user == getattr(webinar, 'created_by', None)
    )

def _webinar_has_zoom_meeting(webinar) -> bool:
    """Check if webinar already has a Zoom meeting/webinar"""
    return (
        hasattr(webinar, 'zoom_meeting_rel') and webinar.zoom_meeting_rel or
        hasattr(webinar, 'zoom_webinar_rel') and webinar.zoom_webinar_rel
    )

def _get_client_ip(request) -> str:
    """Get client IP address from request"""
    x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
    if x_forwarded_for:
        ip = x_forwarded_for.split(',')[0]
    else:
        ip = request.META.get('REMOTE_ADDR')
    return ip
