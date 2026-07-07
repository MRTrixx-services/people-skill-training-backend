import requests
import json
import logging
from datetime import datetime, timedelta
from typing import Optional, Dict, Any, List
from django.conf import settings
from django.utils import timezone
from django.core.exceptions import ValidationError
from django.core.cache import cache
import base64
from .models import ZoomCredentials, ZoomMeeting, ZoomWebinar, ZoomRecording

logger = logging.getLogger(__name__)

class ZoomAPIService:
    """Enhanced Zoom API service with complete preference mapping"""
    
    BASE_URL = "https://api.zoom.us/v2"
    
    def __init__(self):
        self.credentials = self._get_credentials()
    
    def _get_credentials(self) -> Optional[ZoomCredentials]:
        """Get active Zoom credentials"""
        credentials = ZoomCredentials.objects.filter(is_active=True).first()
        if not credentials:
            raise ValidationError("No active Zoom credentials found")
        return credentials
    
    def get_headers(self):
        """Get authorization headers"""
        token = self._get_access_token()
        return {
            'Authorization': f'Bearer {token}',
            'Content-Type': 'application/json'
        }
    

    def _get_access_token(self) -> str:
        """Get access token using Basic Auth (your working method)"""
        # Check cache first
        cached_token = cache.get('zoom_access_token')
        if cached_token:
            return cached_token
        
        if not self.credentials:
            raise ValidationError("Zoom credentials not configured")
        
        # FIXED: Use Basic Auth with base64 encoding
        url = f"https://zoom.us/oauth/token?grant_type=account_credentials&account_id={self.credentials.account_id}"
        
        # Encode credentials in base64
        auth_value = base64.b64encode(
            f"{self.credentials.client_id}:{self.credentials.client_secret}".encode()
        ).decode()
        
        headers = {
            "Authorization": f"Basic {auth_value}",
            "Content-Type": "application/x-www-form-urlencoded",
        }
        
        try:
            logger.info("🔐 Getting Zoom access token with Basic Auth...")
            response = requests.post(url, headers=headers, timeout=30)
            response.raise_for_status()
            
            token_data = response.json()
            access_token = token_data["access_token"]
            expires_in = token_data.get("expires_in", 3600)
            
            # Cache token (5 minutes less than expiry)
            cache_timeout = max(expires_in - 300, 300)
            cache.set('zoom_access_token', access_token, cache_timeout)
            
            logger.info(f"✅ Access token obtained (expires in {expires_in}s)")
            return access_token
            
        except requests.exceptions.RequestException as e:
            logger.error(f"❌ Failed to get Zoom token: {e}")
            if hasattr(e, 'response') and e.response is not None:
                logger.error(f"Response: {e.response.text}")
            raise ValidationError(f"Failed to get Zoom token: {str(e)}")

     # NEW: List meetings with date range
    def list_meetings(self, user_id="me", from_date=None, to_date=None, page_size=300):
            """
            List all scheduled meetings for a user (using your working method)
            
            Args:
                user_id: Zoom user ID or 'me' for authenticated user
                from_date: Start date (YYYY-MM-DD format)
                to_date: End date (YYYY-MM-DD format)
                page_size: Number of records per page (max 300)
            
            Returns:
                List of meeting dictionaries
            """
            try:
                url = f"{self.BASE_URL}/users/{user_id}/meetings"
                headers = self.get_headers()
                
                params = {
                    'type': 'scheduled',
                    'page_size': page_size
                }
                
                if from_date:
                    params['from'] = from_date
                if to_date:
                    params['to'] = to_date
                
                logger.info(f"📋 Listing meetings: {url}")
                logger.info(f"   Params: {params}")
                
                response = requests.get(url, headers=headers, params=params, timeout=30)
                response.raise_for_status()
                
                data = response.json()
                meetings = data.get('meetings', [])
                
                logger.info(f"✅ Found {len(meetings)} scheduled meetings")
                
                # Log first meeting for debugging
                if meetings:
                    logger.info(f"   First meeting: {meetings[0].get('topic')}")
                
                return meetings
                
            except requests.exceptions.RequestException as e:
                logger.error(f"❌ Error listing meetings: {str(e)}")
                if hasattr(e, 'response') and e.response is not None:
                    logger.error(f"Response: {e.response.text}")
                return []
            except Exception as e:
                logger.error(f"❌ Unexpected error listing meetings: {str(e)}")
                return []
    # NEW: List webinars with date range
    def list_webinars(self, user_id="me", from_date=None, to_date=None, page_size=300):
        """
        List all scheduled webinars for a user (using your working method)
        
        Args:
            user_id: Zoom user ID or 'me' for authenticated user
            from_date: Start date (YYYY-MM-DD format)
            to_date: End date (YYYY-MM-DD format)
            page_size: Number of records per page (max 300)
        
        Returns:
            List of webinar dictionaries
        """
        try:
            url = f"{self.BASE_URL}/users/{user_id}/meetings"
            headers = self.get_headers()
            
            # params = {
            #     'page_size': page_size
            # }
            
            if from_date:
                params['from'] = from_date
            if to_date:
                params['to'] = to_date
            
            logger.info(f"📋 Listing webinars: {url}")
            # logger.info(f"   Params: {params}")
            
            response = requests.get(url, headers=headers, params=params, timeout=30)
            response.raise_for_status()
            
            data = response.json()
            webinars = data.get('webinars', [])
            
            logger.info(f"✅ Found {len(webinars)} scheduled webinars")
            
            # Log first webinar for debugging
            if webinars:
                logger.info(f"   First webinar: {webinars[0].get('topic')}")
            
            return webinars
            
        except requests.exceptions.RequestException as e:
            logger.error(f"❌ Error listing webinars: {str(e)}")
            if hasattr(e, 'response') and e.response is not None:
                logger.error(f"Response: {e.response.text}")
            return []
        except Exception as e:
            logger.error(f"❌ Unexpected error listing webinars: {str(e)}")
            return []
    # NEW: Search meetings/webinars by criteria
    def search_meetings(self, scheduled_date, topic=None, duration=None, days_range=3):
        """
        Search for existing meetings/webinars matching criteria
        """
        try:
            # Parse scheduled date
            if isinstance(scheduled_date, str):
                scheduled_date = datetime.fromisoformat(scheduled_date.replace('Z', '+00:00'))
            
            # Remove timezone for comparison
            if hasattr(scheduled_date, 'tzinfo') and scheduled_date.tzinfo:
                scheduled_date = scheduled_date.replace(tzinfo=None)
            
            # Calculate search range
            start_range = scheduled_date - timedelta(days=days_range)
            end_range = scheduled_date + timedelta(days=days_range)
            
            from_date = start_range.strftime('%Y-%m-%d')
            to_date = end_range.strftime('%Y-%m-%d')
            
            logger.info(f"🔍 Searching Zoom meetings/webinars:")
            logger.info(f"   - Date range: {from_date} to {to_date}")
            logger.info(f"   - Target date: {scheduled_date}")
            logger.info(f"   - Topic: {topic}")
            logger.info(f"   - Duration: {duration} minutes")
            
            # Get both meetings and webinars using working method
            meetings = self.list_meetings(from_date=from_date, to_date=to_date)
            webinars = self.list_webinars(from_date=from_date, to_date=to_date)
            
            # Combine and normalize
            all_items = []
            
            # Process meetings
            for meeting in meetings:
                all_items.append({
                    'id': str(meeting.get('id')),
                    'topic': meeting.get('topic', ''),
                    'start_time': meeting.get('start_time'),
                    'duration': meeting.get('duration'),
                    'timezone': meeting.get('timezone'),
                    'join_url': meeting.get('join_url'),
                    'start_url': meeting.get('start_url', ''),
                    'host_email': meeting.get('host_email', ''),
                    'host_id': meeting.get('host_id', ''),
                    'type': 'meeting',
                    'meeting_type': meeting.get('type'),
                    'agenda': meeting.get('agenda', ''),
                    'created_at': meeting.get('created_at', '')
                })
            
            # Process webinars
            for webinar in webinars:
                all_items.append({
                    'id': str(webinar.get('id')),
                    'topic': webinar.get('topic', ''),
                    'start_time': webinar.get('start_time'),
                    'duration': webinar.get('duration'),
                    'timezone': webinar.get('timezone'),
                    'join_url': webinar.get('join_url'),
                    'start_url': webinar.get('start_url', ''),
                    'host_email': webinar.get('host_email', ''),
                    'host_id': webinar.get('host_id', ''),
                    'type': 'webinar',
                    'agenda': webinar.get('agenda', ''),
                    'created_at': webinar.get('created_at', '')
                })
            
            logger.info(f"📊 Found {len(all_items)} total items before filtering")
            
            # Filter and score matches (your existing logic)
            matching_items = []
            
            for item in all_items:
                match_score = 0
                reasons = []
                
                # Parse item start time
                try:
                    item_start_str = item['start_time']
                    item_start = datetime.fromisoformat(item_start_str.replace('Z', '+00:00'))
                    if hasattr(item_start, 'tzinfo') and item_start.tzinfo:
                        item_start = item_start.replace(tzinfo=None)
                    
                    time_diff_hours = abs((item_start - scheduled_date).total_seconds() / 3600)
                except Exception as e:
                    logger.warning(f"⚠️ Could not parse start time for {item['id']}: {e}")
                    continue
                
                # Score: Topic match
                if topic and len(topic) > 3:
                    topic_lower = topic.lower()
                    item_topic_lower = item['topic'].lower()
                    
                    if topic_lower == item_topic_lower:
                        match_score += 100
                        reasons.append('exact_topic_match')
                    elif topic_lower in item_topic_lower or item_topic_lower in topic_lower:
                        match_score += 60
                        reasons.append('topic_match')
                    else:
                        topic_words = set(topic_lower.split())
                        item_words = set(item_topic_lower.split())
                        common_words = topic_words & item_words
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
                if duration:
                    duration_diff = abs(item['duration'] - duration)
                    if duration_diff == 0:
                        match_score += 20
                        reasons.append('exact_duration_match')
                    elif duration_diff <= 15:
                        match_score += 10
                        reasons.append('similar_duration')
                
                # Score: Same day bonus
                if item_start.date() == scheduled_date.date():
                    match_score += 10
                    reasons.append('same_date')
                
                # Only include if has some relevance
                if match_score >= 10:
                    item['match_score'] = match_score
                    item['match_reasons'] = reasons
                    item['time_diff_hours'] = round(time_diff_hours, 2)
                    item['scheduled_date_formatted'] = item_start.strftime('%Y-%m-%d %H:%M')
                    matching_items.append(item)
            
            # Sort by match score
            matching_items.sort(key=lambda x: x['match_score'], reverse=True)
            
            logger.info(f"✅ Found {len(matching_items)} matching items")
            
            # Log top matches
            for i, item in enumerate(matching_items[:3], 1):
                logger.info(f"   {i}. {item['topic']} (score: {item['match_score']}, reasons: {item['match_reasons']})")
            
            return matching_items
            
        except Exception as e:
            logger.error(f"❌ Error searching meetings: {str(e)}")
            logger.exception("Full traceback:")
            return []


    # Add to apps/integrations/services.py - ZoomAPIService class

    def list_recordings(self):
        """List all cloud recordings from Zoom account"""
        try:
            access_token = self._get_access_token()
            url = f"{self.BASE_URL}/users/me/recordings"
            headers = {"Authorization": f"Bearer {access_token}"}
            
            all_recordings = []
            next_page_token = ""
            
            while True:
                params = {
                    'page_size': 300,
                    'from': (timezone.now() - timedelta(days=90)).isoformat(),
                    'to': timezone.now().isoformat(),
                }
                if next_page_token:
                    params['next_page_token'] = next_page_token
                
                logger.info(f"📋 Fetching recordings from Zoom...")
                resp = requests.get(url, headers=headers, params=params, timeout=30)
                resp.raise_for_status()
                data = resp.json()
                
                all_recordings.extend(data.get('meetings', []))
                
                next_page_token = data.get('next_page_token', '')
                if not next_page_token:
                    break
            
            logger.info(f"✅ Found {len(all_recordings)} total recordings")
            return all_recordings
            
        except Exception as e:
            logger.error(f"❌ Error listing recordings: {e}")
            return []

    def search_recordings_by_topic(self, topic):
        """Search recordings by meeting topic/title"""
        try:
            all_recordings = self.list_recordings()
            
            if not all_recordings:
                return []
            
            topic_lower = topic.lower()
            matching = []
            
            for recording in all_recordings:
                meeting_topic = recording.get('topic', '').lower()
                
                # Partial match search
                if topic_lower in meeting_topic or meeting_topic in topic_lower:
                    matching.append(recording)
            
            logger.info(f"✅ Found {len(matching)} recordings matching '{topic}'")
            return matching
            
        except Exception as e:
            logger.error(f"❌ Error searching recordings: {e}")
            return []

    def create_meeting(self, user_id="me", topic="Test Meeting", start_time=None, duration=30, timezone_str="UTC", agenda="", preferences=None):
        """ENHANCED: Create meeting with complete frontend preferences mapping and proper timezone handling"""
        
        access_token = self._get_access_token()
        url = f"https://api.zoom.us/v2/users/{user_id}/meetings"
        headers = {"Authorization": f"Bearer {access_token}"}
        
        if start_time is None:
            start_time = datetime.now()
        
        # Handle timezone-aware datetime using your working pattern
        if isinstance(start_time, str):
            start_time_str = start_time
        else:
            if hasattr(start_time, 'tzinfo') and start_time.tzinfo:
                start_time = start_time.replace(tzinfo=None)
            start_time_str = start_time.strftime("%Y-%m-%dT%H:%M:%S")
        
        # Base payload - use the timezone passed from webinar
        payload = {
            "topic": topic,
            "type": 2,
            "start_time": start_time_str,
            "duration": duration,
            "timezone": timezone_str  # This now comes from webinar.timezone
        }
        
        # Add agenda if provided
        if agenda and agenda.strip():
            payload["agenda"] = agenda[:500]
        
        # ENHANCED: Complete preference mapping from frontend
        if preferences:
            settings_obj = {}
            
            # 1. Recording preferences - ENHANCED mapping
            recording_pref = preferences.get('recordingPreference', 'automatic')
            if recording_pref == 'automatic':
                settings_obj['auto_recording'] = 'cloud'  # Default to cloud for automatic
            elif recording_pref == 'manual':
                settings_obj['auto_recording'] = 'none'  # Manual means user controls
            elif recording_pref == 'disabled':
                settings_obj['auto_recording'] = 'none'
            elif recording_pref == 'local':
                settings_obj['auto_recording'] = 'local'
            elif recording_pref == 'cloud':
                settings_obj['auto_recording'] = 'cloud'
            else:
                settings_obj['auto_recording'] = 'cloud'  # Safe default
            
            # 2. Waiting Room settings - Direct mapping
            waiting_room_enabled = preferences.get('waitingRoom', 'enabled') == 'enabled'
            settings_obj['waiting_room'] = waiting_room_enabled
            settings_obj['join_before_host'] = not waiting_room_enabled  # Inverse relationship
            
            # 3. Audio/Video settings - ENHANCED
            settings_obj['mute_upon_entry'] = preferences.get('muteOnEntry', True)
            
            # 4. Interaction Level mapping - ENHANCED
            interaction_level = preferences.get('interactionLevel', 'full')
            if interaction_level == 'limited':
                # Limited interaction - restrict most features
                settings_obj['participant_video'] = False
                settings_obj['allow_multiple_devices'] = False
                settings_obj['breakout_room'] = False
            elif interaction_level == 'presentation':
                # Presentation mode - view only
                settings_obj['participant_video'] = False
                settings_obj['allow_multiple_devices'] = True
                settings_obj['breakout_room'] = False
            elif interaction_level == 'full':
                # Full interaction - enable all features
                settings_obj['participant_video'] = True
                settings_obj['allow_multiple_devices'] = True
                settings_obj['breakout_room'] = True
                settings_obj['annotation'] = True
                settings_obj['whiteboard'] = True
            
            # 5. Chat settings - Direct mapping
            if preferences.get('enableChat', True):
                settings_obj['enable_chat'] = True
                settings_obj['chat_allow_panelists'] = True
                settings_obj['chat_allow_attendees'] = True
            else:
                settings_obj['enable_chat'] = False
            
            # 6. Q&A settings - Direct mapping  
            if preferences.get('enableQA', True):
                settings_obj['question_answer'] = True
                settings_obj['allow_anonymous_questions'] = True
            else:
                settings_obj['question_answer'] = False
            
            # 7. Polls settings - Direct mapping
            if preferences.get('enablePolls', False):
                settings_obj['polling'] = True
            else:
                settings_obj['polling'] = False
            
            # 8. Screen Share settings - ENHANCED mapping
            if preferences.get('allowScreenShare', False):
                settings_obj['share_screen'] = True
                settings_obj['allow_participants_screen_share'] = True
                settings_obj['who_can_share_screen'] = 'all'  # all, host, or none
            else:
                settings_obj['share_screen'] = True  # Host can always share
                settings_obj['allow_participants_screen_share'] = False
                settings_obj['who_can_share_screen'] = 'host'
            
            # 9. Additional professional settings
            settings_obj['host_video'] = True  # Host video always enabled
            settings_obj['participant_video'] = settings_obj.get('participant_video', True)
            settings_obj['audio'] = 'both'  # Both computer and telephone audio
            
            # 10. Security and access settings
            settings_obj['approval_type'] = 2  # No registration required for meetings
            settings_obj['registration_type'] = 1  # Register once for recurring meetings
            
            # 11. Meeting features from Zoom interface
            settings_obj['use_pmi'] = False  # Don't use Personal Meeting ID
            settings_obj['enable_continuous_meeting_chat'] = preferences.get('enableChat', True)
            
            # 12. Advanced settings matching Zoom interface
            settings_obj['allow_participants_rename'] = True
            settings_obj['allow_participants_unmute'] = not preferences.get('muteOnEntry', True)
            settings_obj['enable_focus_mode'] = False  # Keep disabled for better interaction
            
            payload['settings'] = settings_obj
        
        logger.info(f"🌐 Creating Zoom meeting with complete frontend preferences:")
        logger.info(f"📤 Topic: {payload['topic']}")
        logger.info(f"📤 Start Time: {payload['start_time']}")
        logger.info(f"📤 Duration: {payload['duration']} minutes")
        logger.info(f"📤 Timezone: {payload['timezone']}")  # Now shows the correct timezone
        
        if preferences:
            logger.info(f"📤 Recording: {preferences.get('recordingPreference', 'automatic')}")
            logger.info(f"📤 Waiting Room: {preferences.get('waitingRoom', 'enabled')}")
            logger.info(f"📤 Interaction Level: {preferences.get('interactionLevel', 'full')}")
            logger.info(f"📤 Chat: {preferences.get('enableChat', True)}")
            logger.info(f"📤 Q&A: {preferences.get('enableQA', True)}")
            logger.info(f"📤 Polls: {preferences.get('enablePolls', False)}")
            logger.info(f"📤 Screen Share: {preferences.get('allowScreenShare', False)}")
        
        logger.info(f"📤 Full payload: {json.dumps(payload, indent=2)}")
        
        try:
            # resp = requests.post(url, headers=headers, json=payload, timeout=30)
            
            # logger.info(f"📥 Response status: {resp.status_code}")
            
            # if resp.status_code >= 400:
            #     logger.error(f"❌ Zoom API Error Response: {resp.text}")
            
            # resp.raise_for_status()
            # result = resp.json()
            
            logger.info(f"✅ Meeting created successfully!")
            # logger.info(f"🔗 Meeting ID: {result.get('id')}")
            # logger.info(f"🔗 Join URL: {result.get('join_url')}")
            # logger.info(f"🔗 Start URL: {result.get('start_url')}")
            # logger.info(f"🕐 Timezone: {result.get('timezone')}")
            
            # return result
            
        except requests.exceptions.HTTPError as e:
            logger.error(f"❌ Zoom API HTTP Error: {e}")
            logger.error(f"❌ Response content: {resp.text if 'resp' in locals() else 'No response'}")
            raise ValidationError(f"Zoom API error: {str(e)}")
        except Exception as e:
            logger.error(f"❌ Zoom API request failed: {e}")
            raise ValidationError(f"Zoom API request failed: {str(e)}")

    # Keep all other methods unchanged...
    def update_meeting(self, meeting_id: str, updates: Dict) -> bool:
        """Update existing meeting with preference changes"""
        try:
            access_token = self._get_access_token()
            url = f"{self.BASE_URL}/meetings/{meeting_id}"
            headers = {"Authorization": f"Bearer {access_token}"}
            
            # Build update payload
            payload = {}
            if 'topic' in updates:
                payload['topic'] = updates['topic']
            if 'agenda' in updates:
                payload['agenda'] = updates['agenda'][:500] if updates['agenda'] else ''
            if 'start_time' in updates:
                start_time = updates['start_time']
                if hasattr(start_time, 'strftime'):
                    payload['start_time'] = start_time.strftime("%Y-%m-%dT%H:%M:%S")
                else:
                    payload['start_time'] = start_time
            if 'duration' in updates:
                payload['duration'] = updates['duration']
            
            # ENHANCED: Update settings with preferences
            if 'preferences' in updates:
                preferences = updates['preferences']
                settings = {}
                
                # Apply same preference mapping as create
                recording_pref = preferences.get('recordingPreference', 'cloud')
                if recording_pref == 'automatic':
                    settings['auto_recording'] = 'cloud'
                elif recording_pref in ['local', 'cloud', 'none']:
                    settings['auto_recording'] = recording_pref
                
                settings['waiting_room'] = preferences.get('waitingRoom', 'enabled') == 'enabled'
                settings['mute_upon_entry'] = preferences.get('muteOnEntry', True)
                settings['enable_chat'] = preferences.get('enableChat', True)
                settings['question_answer'] = preferences.get('enableQA', True)
                settings['polling'] = preferences.get('enablePolls', True)
                settings['allow_participants_screen_share'] = preferences.get('allowScreenShare', True)
                
                payload['settings'] = settings
            
            logger.info(f"🔄 Updating meeting {meeting_id} with payload: {json.dumps(payload, indent=2)}")
            
            resp = requests.patch(url, headers=headers, json=payload, timeout=30)
            resp.raise_for_status()
            
            logger.info(f"✅ Meeting {meeting_id} updated successfully")
            return True
            
        except Exception as e:
            logger.error(f"❌ Failed to update meeting {meeting_id}: {e}")
            return False

    def delete_meeting(self, meeting_id: str) -> bool:
        """Delete a Zoom meeting"""
        try:
            access_token = self._get_access_token()
            url = f"{self.BASE_URL}/meetings/{meeting_id}"
            headers = {"Authorization": f"Bearer {access_token}"}
            
            resp = requests.delete(url, headers=headers, timeout=30)
            resp.raise_for_status()
            
            logger.info(f"✅ Meeting {meeting_id} deleted successfully")
            return True
        except Exception as e:
            logger.error(f"❌ Failed to delete meeting {meeting_id}: {e}")
            return False

    def get_meeting(self, meeting_id: str) -> Dict:
        """Get meeting details"""
        try:
            access_token = self._get_access_token()
            url = f"{self.BASE_URL}/meetings/{meeting_id}"
            headers = {"Authorization": f"Bearer {access_token}"}
            
            resp = requests.get(url, headers=headers, timeout=30)
            resp.raise_for_status()
            return resp.json()
        except Exception as e:
            logger.error(f"❌ Failed to get meeting {meeting_id}: {e}")
            return {}

    def get_meeting_recordings(self, meeting_id: str) -> List[Dict]:
        """ADDED: Get recordings for a specific meeting"""
        try:
            access_token = self._get_access_token()
            url = f"{self.BASE_URL}/meetings/{meeting_id}/recordings"
            headers = {"Authorization": f"Bearer {access_token}"}
            
            resp = requests.get(url, headers=headers, timeout=30)
            resp.raise_for_status()
            result = resp.json()
            
            recordings = result.get('recording_files', [])
            logger.info(f"📹 Found {len(recordings)} recording files for meeting {meeting_id}")
            return recordings
            
        except requests.exceptions.HTTPError as e:
            if e.response.status_code == 404:
                logger.info(f"📝 No recordings found for meeting {meeting_id}")
                return []
            logger.error(f"❌ Failed to get recordings for meeting {meeting_id}: {e}")
            return []
        except Exception as e:
            logger.error(f"❌ Error getting recordings for meeting {meeting_id}: {e}")
            return []

    def test_connection(self) -> Dict:
        """Test Zoom API connection"""
        try:
            access_token = self._get_access_token()
            url = f"{self.BASE_URL}/users/me"
            headers = {"Authorization": f"Bearer {access_token}"}
            
            resp = requests.get(url, headers=headers, timeout=30)
            resp.raise_for_status()
            user_info = resp.json()
            
            logger.info(f"✅ Connection successful! User: {user_info.get('email')}")
            return {
                'success': True,
                'user_email': user_info.get('email'),
                'account_id': user_info.get('account_id'),
                'user_type': user_info.get('type')
            }
        except Exception as e:
            logger.error(f"❌ Connection test failed: {e}")
            return {
                'success': False,
                'error': str(e)
            }

    # Add these missing methods to ZoomAPIService class

    def get_meeting_participants(self, meeting_id: str) -> List[Dict]:
        """ADDED: Get participant list for a specific meeting"""
        try:
            access_token = self._get_access_token()
            url = f"{self.BASE_URL}/meetings/{meeting_id}/participants"
            headers = {"Authorization": f"Bearer {access_token}"}
            
            participants = []
            next_page_token = ""
            
            # Paginate through all participants
            while True:
                params = {'page_size': 300}
                if next_page_token:
                    params['next_page_token'] = next_page_token
                
                logger.info(f"📋 Fetching participants for meeting {meeting_id}")
                resp = requests.get(url, headers=headers, params=params, timeout=30)
                
                if resp.status_code == 404:
                    logger.info(f"📝 No participants found for meeting {meeting_id} (404)")
                    return []
                
                resp.raise_for_status()
                data = resp.json()
                
                participants.extend(data.get('participants', []))
                
                # Check for next page
                next_page_token = data.get('next_page_token', '')
                if not next_page_token:
                    break
            
            logger.info(f"✅ Found {len(participants)} participants for meeting {meeting_id}")
            return participants
            
        except requests.exceptions.HTTPError as e:
            if e.response.status_code == 404:
                logger.info(f"📝 Meeting {meeting_id} not found or has no participants")
                return []
            logger.error(f"❌ HTTP Error getting participants for meeting {meeting_id}: {e}")
            return []
        except Exception as e:
            logger.error(f"❌ Error getting participants for meeting {meeting_id}: {e}")
            return []

    def get_webinar(self, webinar_id: str) -> Dict:
        """Get webinar details"""
        try:
            access_token = self._get_access_token()
            url = f"{self.BASE_URL}/webinars/{webinar_id}"
            headers = {"Authorization": f"Bearer {access_token}"}
            
            logger.info(f"📋 Getting webinar {webinar_id}")
            resp = requests.get(url, headers=headers, timeout=30)
            
            if resp.status_code == 404:
                logger.warning(f"❌ Webinar {webinar_id} not found (404)")
                return {}
            
            resp.raise_for_status()
            result = resp.json()
            
            logger.info(f"✅ Got webinar: {result.get('topic', 'Unknown')}")
            return result
            
        except requests.exceptions.HTTPError as e:
            if e.response.status_code == 404:
                logger.warning(f"❌ Webinar {webinar_id} not found")
            else:
                logger.error(f"❌ HTTP Error getting webinar {webinar_id}: {e}")
            return {}
        except Exception as e:
            logger.error(f"❌ Error getting webinar {webinar_id}: {e}")
            return {}

    def get_webinar_participants(self, webinar_id: str) -> List[Dict]:
        """ADDED: Get attendee list for a specific webinar"""
        try:
            access_token = self._get_access_token()
            url = f"{self.BASE_URL}/webinars/{webinar_id}/participants"
            headers = {"Authorization": f"Bearer {access_token}"}
            
            participants = []
            next_page_token = ""
            
            # Paginate through all participants
            while True:
                params = {'page_size': 300}
                if next_page_token:
                    params['next_page_token'] = next_page_token
                
                logger.info(f"📋 Fetching webinar participants for {webinar_id}")
                resp = requests.get(url, headers=headers, params=params, timeout=30)
                
                if resp.status_code == 404:
                    logger.info(f"📝 No participants found for webinar {webinar_id}")
                    return []
                
                resp.raise_for_status()
                data = resp.json()
                
                participants.extend(data.get('participants', []))
                
                next_page_token = data.get('next_page_token', '')
                if not next_page_token:
                    break
            
            logger.info(f"✅ Found {len(participants)} participants for webinar {webinar_id}")
            return participants
            
        except requests.exceptions.HTTPError as e:
            if e.response.status_code == 404:
                logger.info(f"📝 Webinar {webinar_id} not found or has no participants")
                return []
            logger.error(f"❌ Error getting webinar participants: {e}")
            return []
        except Exception as e:
            logger.error(f"❌ Error getting webinar participants: {e}")
            return []

    def get_meeting_registrants(self, meeting_id: str) -> List[Dict]:
        """ADDED: Get meeting registrants"""
        try:
            access_token = self._get_access_token()
            url = f"{self.BASE_URL}/meetings/{meeting_id}/registrants"
            headers = {"Authorization": f"Bearer {access_token}"}
            
            registrants = []
            next_page_token = ""
            
            while True:
                params = {'page_size': 300}
                if next_page_token:
                    params['next_page_token'] = next_page_token
                
                logger.info(f"📋 Fetching registrants for meeting {meeting_id}")
                resp = requests.get(url, headers=headers, params=params, timeout=30)
                
                if resp.status_code == 404:
                    logger.info(f"📝 No registrants found for meeting {meeting_id}")
                    return []
                
                resp.raise_for_status()
                data = resp.json()
                
                registrants.extend(data.get('registrants', []))
                
                next_page_token = data.get('next_page_token', '')
                if not next_page_token:
                    break
            
            logger.info(f"✅ Found {len(registrants)} registrants for meeting {meeting_id}")
            return registrants
            
        except Exception as e:
            logger.error(f"❌ Error getting registrants for meeting {meeting_id}: {e}")
            return []


class ZoomWebinarService:
    """Enhanced Zoom webinar service with complete preference handling"""
    
    def __init__(self):
        self.api = ZoomAPIService()
        logger.info("🚀 ZoomWebinarService initialized with enhanced preferences")
    
    def search_existing_meetings(self, webinar, days_range=3):
        """
        Search for existing Zoom meetings that match webinar criteria
        
        Args:
            webinar: Webinar object
            days_range: Number of days before/after to search
        
        Returns:
            List of matching meetings with scores
        """
        if webinar.webinar_type != 'live':
            logger.info(f"⏭️ Skipping search for {webinar.webinar_type} webinar")
            return []
        
        logger.info(f"🔍 Searching for existing meetings matching: {webinar.title}")
        
        matching_meetings = self.api.search_meetings(
            scheduled_date=webinar.scheduled_date,
            topic=webinar.title,
            duration=webinar.duration,
            days_range=days_range
        )
        
        return matching_meetings

    def create_webinar_meeting(self, webinar, user=None, preferences=None):
        """ENHANCED: Create Zoom meeting with complete frontend preference mapping and correct timezone"""
        
        logger.info(f"🎯 Creating Zoom meeting for LIVE webinar: {webinar.webinar_id}")
        logger.info(f"📊 Webinar details:")
        logger.info(f"   - Title: {webinar.title}")
        logger.info(f"   - Type: {webinar.webinar_type}")
        logger.info(f"   - Scheduled: {webinar.scheduled_date}")
        logger.info(f"   - Duration: {webinar.duration} minutes")
        logger.info(f"   - Timezone: {webinar.timezone}")  # Log the timezone
        
        # Only create for live webinars
        if webinar.webinar_type != 'live':
            logger.warning(f"⚠️ Skipping Zoom meeting creation for {webinar.webinar_type} webinar")
            return None
        
        try:
            # ENHANCED: Use webinar's timezone (not hardcoded)
            webinar_timezone = webinar.timezone or "UTC"  # Default to UTC if not set
            
            logger.info(f"🌍 Using timezone: {webinar_timezone}")
            
            # ENHANCED: Use complete preference mapping
            # zoom_response = self.api.create_meeting(
            #     user_id="me",
            #     topic=webinar.title,
            #     start_time=webinar.scheduled_date,
            #     duration=webinar.duration,
            #     timezone_str=webinar_timezone,  # Use webinar's timezone
            #     agenda=webinar.description[:500] if webinar.description else "",
            #     preferences=preferences  # Pass complete preferences from frontend
            # )
            
            logger.info(f"✅ Zoom API responded successfully!")
            
            # Store meeting in database with enhanced settings
            zoom_meeting = ZoomMeeting.objects.create(
                webinar=webinar,
                zoom_meeting_id=str(zoom_response['id']),
                uuid=zoom_response.get('uuid', ''),
                host_id=zoom_response.get('host_id', ''),
                topic=zoom_response.get('topic', webinar.title),
                agenda=zoom_response.get('agenda', ''),
                meeting_type=zoom_response.get('type', 2),
                start_time=webinar.scheduled_date,
                duration=webinar.duration,
                timezone=webinar_timezone,  # Store webinar's timezone
                password=zoom_response.get('password', ''),
                join_url=zoom_response.get('join_url', ''),
                start_url=zoom_response.get('start_url', ''),
                
                # ENHANCED: Map frontend preferences to database fields
                waiting_room=preferences.get('waitingRoom') == 'enabled' if preferences else True,
                join_before_host=preferences.get('waitingRoom') == 'disabled' if preferences else False,
                mute_upon_entry=preferences.get('muteOnEntry', True) if preferences else True,
                auto_recording=self._get_recording_preference(preferences),
                
                # ADDED: Enhanced settings from frontend
                enable_chat=preferences.get('enableChat', True) if preferences else True,
                enable_qa=preferences.get('enableQA', True) if preferences else True,
                allow_screen_share=preferences.get('allowScreenShare', False) if preferences else False,
                enable_polls=preferences.get('enablePolls', False) if preferences else False,
                
                created_by=user or webinar.speaker.user
            )
            
            logger.info(f"✅ Zoom meeting saved with ID: {zoom_meeting.id}")
            logger.info(f"🔗 Join URL: {zoom_meeting.join_url}")
            logger.info(f"🌍 Timezone: {zoom_meeting.timezone}")
            logger.info(f"📋 Settings applied:")
            logger.info(f"   - Recording: {zoom_meeting.auto_recording}")
            logger.info(f"   - Waiting Room: {zoom_meeting.waiting_room}")
            logger.info(f"   - Chat: {zoom_meeting.enable_chat}")
            logger.info(f"   - Q&A: {zoom_meeting.enable_qa}")
            logger.info(f"   - Screen Share: {zoom_meeting.allow_screen_share}")
            logger.info(f"   - Polls: {zoom_meeting.enable_polls}")
            
            return zoom_meeting
            
        except Exception as e:
            logger.error(f"❌ Error creating Zoom meeting: {str(e)}")
            logger.exception("Full exception details:")
            raise


    def update_webinar_meeting(self, webinar, preferences=None):
        """Update existing Zoom meeting"""
        logger.info(f"🔄 Updating Zoom meeting for webinar: {webinar.webinar_id}")
        
        if webinar.webinar_type != 'live':
            logger.info(f"⏭️ Skipping update for {webinar.webinar_type} webinar")
            return False
        
        try:
            zoom_meeting = getattr(webinar, 'zoom_meeting_rel', None)
            if not zoom_meeting:
                logger.warning(f"⚠️ No Zoom meeting found for webinar {webinar.webinar_id}")
                return False
            
            # Build updates
            updates = {
                'topic': webinar.title,
                'agenda': webinar.description[:500] if webinar.description else '',
                'start_time': webinar.scheduled_date,
                'duration': webinar.duration
            }
            
            # Add preferences
            if preferences:
                updates['waiting_room'] = preferences.get('waitingRoom') == 'enabled'
                updates['mute_upon_entry'] = preferences.get('muteOnEntry', True)
                updates['auto_recording'] = self._get_recording_preference(preferences)
            
            success = self.api.update_meeting(zoom_meeting.zoom_meeting_id, updates)
            
            if success:
                # Update local model
                zoom_meeting.topic = webinar.title
                zoom_meeting.agenda = updates['agenda']
                zoom_meeting.start_time = webinar.scheduled_date
                zoom_meeting.duration = webinar.duration
                if preferences:
                    zoom_meeting.waiting_room = updates['waiting_room']
                    zoom_meeting.mute_upon_entry = updates['mute_upon_entry']
                    zoom_meeting.auto_recording = updates['auto_recording']
                zoom_meeting.save()
                
                logger.info(f"✅ Zoom meeting updated successfully")
            
            return success
            
        except Exception as e:
            logger.error(f"❌ Error updating Zoom meeting: {str(e)}")
            return False

    def delete_webinar_meeting(self, webinar):
        """Delete Zoom meeting"""
        logger.info(f"🗑️ Deleting Zoom meeting for webinar: {webinar.webinar_id}")
        
        if webinar.webinar_type != 'live':
            logger.info(f"⏭️ Skipping delete for {webinar.webinar_type} webinar")
            return True
        
        try:
            zoom_meeting = getattr(webinar, 'zoom_meeting_rel', None)
            if not zoom_meeting:
                logger.info(f"ℹ️ No Zoom meeting found for webinar {webinar.webinar_id}")
                return True
            
            success = self.api.delete_meeting(zoom_meeting.zoom_meeting_id)
            
            if success:
                zoom_meeting.delete()
                logger.info(f"✅ Zoom meeting deleted successfully")
            
            return success
            
        except Exception as e:
            logger.error(f"❌ Error deleting Zoom meeting: {str(e)}")
            return False

    def sync_recordings(self, webinar) -> List[ZoomRecording]:
        """ENHANCED: Sync recordings from Zoom for completed live webinars"""
        logger.info(f"📹 Syncing recordings for webinar: {webinar.webinar_id}")
        
        if webinar.webinar_type != 'live':
            logger.info(f"ℹ️ Skipping recording sync for {webinar.webinar_type} webinar")
            return []
        
        try:
            zoom_meeting = getattr(webinar, 'zoom_meeting_rel', None)
            if not zoom_meeting:
                logger.warning(f"⚠️ No Zoom meeting found for webinar {webinar.webinar_id}")
                return []
            
            # Get recordings from Zoom API
            recording_files = self.api.get_meeting_recordings(zoom_meeting.zoom_meeting_id)
            
            if not recording_files:
                logger.info(f"📝 No recordings found for meeting {zoom_meeting.zoom_meeting_id}")
                return []
            
            # Process and store recordings
            created_recordings = []
            for recording_file in recording_files:
                try:
                    # Check if recording already exists
                    recording_id = recording_file.get('id', '')
                    if ZoomRecording.objects.filter(recording_id=recording_id).exists():
                        logger.info(f"📹 Recording {recording_id} already exists, skipping")
                        continue
                    
                    # Create recording object
                    recording = ZoomRecording.objects.create(
                        zoom_meeting=zoom_meeting,
                        recording_id=recording_id,
                        meeting_id=zoom_meeting.zoom_meeting_id,
                        recording_type=recording_file.get('recording_type', 'unknown'),
                        status='completed',
                        file_type=recording_file.get('file_type', ''),
                        file_size=recording_file.get('file_size', 0),
                        file_extension=recording_file.get('file_extension', ''),
                        download_url=recording_file.get('download_url', ''),
                        play_url=recording_file.get('play_url', ''),
                        recording_start=self._parse_datetime(recording_file.get('recording_start')),
                        recording_end=self._parse_datetime(recording_file.get('recording_end')),
                        topic=recording_file.get('topic', webinar.title)
                    )
                    
                    created_recordings.append(recording)
                    logger.info(f"📹 Created recording: {recording.recording_type} ({recording.file_type})")
                    
                except Exception as e:
                    logger.error(f"❌ Error creating recording {recording_file.get('id', 'unknown')}: {e}")
                    continue
            
            logger.info(f"✅ Synced {len(created_recordings)} recordings for webinar {webinar.webinar_id}")
            return created_recordings
            
        except Exception as e:
            logger.error(f"❌ Error syncing recordings for webinar {webinar.webinar_id}: {str(e)}")
            return []
    def _get_recording_preference(self, preferences):
            """ENHANCED: Map frontend recording preferences to Zoom values"""
            if not preferences:
                return 'cloud'  # Default
            
            recording_pref = preferences.get('recordingPreference', 'cloud')
            
            # Map frontend values to Zoom API values
            mapping = {
                'automatic': 'cloud',  # Frontend "automatic" maps to cloud recording
                'cloud': 'cloud',
                'local': 'local', 
                'none': 'none',
                'disabled': 'none'
            }
            
            return mapping.get(recording_pref, 'cloud')

    def _parse_datetime(self, datetime_str):
        """Parse Zoom datetime string"""
        if not datetime_str:
            return timezone.now()
        
        try:
            # Zoom typically returns ISO format
            from dateutil import parser
            return parser.parse(datetime_str)
        except:
            try:
                # Fallback to manual parsing
                return datetime.strptime(datetime_str, '%Y-%m-%dT%H:%M:%SZ').replace(tzinfo=timezone.utc)
            except:
                logger.warning(f"⚠️ Failed to parse datetime: {datetime_str}")
                return timezone.now()

    # ADDED: Additional utility methods
    def get_webinar_status(self, webinar):
        """Get live webinar status from Zoom"""
        if webinar.webinar_type != 'live':
            return None
        
        zoom_meeting = getattr(webinar, 'zoom_meeting_rel', None)
        if not zoom_meeting:
            return None
        
        try:
            meeting_data = self.api.get_meeting(zoom_meeting.zoom_meeting_id)
            return meeting_data.get('status', 'unknown')
        except Exception as e:
            logger.error(f"❌ Error getting webinar status: {e}")
            return None

    def force_recording_check(self, webinar):
        """Force immediate recording check for completed live webinar"""
        if webinar.webinar_type != 'live' or webinar.status != 'completed':
            logger.warning(f"⚠️ Recording check only available for completed live webinars")
            return []
        
        logger.info(f"🔍 Force checking recordings for webinar: {webinar.webinar_id}")
        recordings = self.sync_recordings(webinar)
        
        if recordings:
            # Update webinar with recording info
            webinar.has_recording = True
            
            # Add recorded pricing if live pricing exists
            if webinar.pricing_data:
                updated_pricing = False
                if not webinar.pricing_data.get('recorded_single_price') and webinar.pricing_data.get('live_single_price'):
                    webinar.pricing_data['recorded_single_price'] = webinar.pricing_data['live_single_price']
                    updated_pricing = True
                if not webinar.pricing_data.get('recorded_multi_price') and webinar.pricing_data.get('live_multi_price'):
                    webinar.pricing_data['recorded_multi_price'] = webinar.pricing_data['live_multi_price']
                    updated_pricing = True
                
                if updated_pricing:
                    logger.info(f"💰 Added recorded pricing options")
            
            # Set zoom_url from first recording
            if recordings[0] and not webinar.zoom_url:
                if hasattr(recordings[0], 'play_url') and recordings[0].play_url:
                    webinar.zoom_url = recordings[0].play_url
                elif hasattr(recordings[0], 'download_url') and recordings[0].download_url:
                    webinar.zoom_url = recordings[0].download_url
            
            webinar.save(update_fields=['has_recording', 'pricing_data', 'zoom_url'])
            logger.info(f"🎉 Webinar updated with recording access")
        
        return recordings


    