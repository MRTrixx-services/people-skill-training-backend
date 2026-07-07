import json
import logging
import sys
from datetime import datetime, timedelta
from django.core.management.base import BaseCommand, CommandError
# Adjust this import based on your project structure
from apps.integrations.services import ZoomAPIService 

logger = logging.getLogger(__name__)

# Attempt to import your local model for context in --get-recordings
# This block assumes your ZoomMeeting model exists in the same app or is imported correctly
try:
    from apps.integrations.models import ZoomMeeting 
except ImportError:
    ZoomMeeting = None
    logger.warning("ZoomMeeting model not found for local lookup in command.")


class Command(BaseCommand):
    help = 'Comprehensive tool for managing Zoom meetings, webinars, and recordings via Zoom API.'

    def add_arguments(self, parser):
        # Action Arguments (Mutually Exclusive)
        action_group = parser.add_mutually_exclusive_group(required=True)
        action_group.add_argument(
            '--list-links', 
            action='store_true', 
            help='List all scheduled meetings and webinars with join/start/recording links.'
        )
        action_group.add_argument(
            '--search-topic', 
            type=str, 
            help='Search for scheduled events by topic (Topic string required).'
        )
        action_group.add_argument(
            '--get-recordings', 
            type=str, 
            dest='meeting_id',
            help='Get recording files for a specific Zoom Meeting ID (ID required).'
        )
        action_group.add_argument(
            '--test-connection', 
            action='store_true', 
            help='Test connection and fetch authenticated user details.'
        )
        action_group.add_argument(
            '--list-recordings', 
            action='store_true', 
            help='List all cloud recordings for the account (default: last 90 days).'
        )
        
        # Optional Filtering/Detail Arguments
        parser.add_argument(
            '--from-date', 
            type=str, 
            default=None,
            help='Start date for --list-links in YYYY-MM-DD format (e.g., 2025-01-01).'
        )
        parser.add_argument(
            '--to-date', 
            type=str, 
            default=None,
            help='End date for --list-links in YYYY-MM-DD format (e.g., 2025-12-31).'
        )
        parser.add_argument(
            '--days-range', 
            type=int, 
            default=3,
            help='Date range in days for --search-topic (default: 3 days around current date/time).'
        )

    def handle(self, *args, **options):
        self.stdout.write(self.style.MIGRATE_HEADING("🚀 Initializing Zoom API Service..."))
        try:
            api_service = ZoomAPIService()
        except Exception as e:
            raise CommandError(f"❌ Failed to initialize Zoom API Service: {e}")

        if options['test_connection']:
            self._handle_test_connection(api_service)
        elif options['list_links']:
            self._handle_list_links(api_service, options)
        elif options['search_topic']:
            self._handle_search_topic(api_service, options)
        elif options['get_recordings']:
            self._handle_get_recordings(api_service, options)
        elif options['list_recordings']:
            self._handle_list_all_recordings(api_service)

        self.stdout.write(self.style.SUCCESS("\nProcess finished successfully."))


    def _handle_test_connection(self, api_service):
        self.stdout.write(self.style.MIGRATE_HEADING("\n🌐 Running API Connection Test..."))
        result = api_service.test_connection()
        if result['success']:
            self.stdout.write(self.style.SUCCESS(f"✅ Connection successful!"))
            self.stdout.write(f" - User Email: {result['user_email']}")
            self.stdout.write(f" - Account ID: {result['account_id']}")
            self.stdout.write(f" - User Type: {result['user_type']}")
        else:
            self.stdout.write(self.style.ERROR(f"❌ Connection test failed: {result['error']}"))

    def _handle_list_links(self, api_service, options):
        self.stdout.write(self.style.MIGRATE_HEADING("\n📋 Listing All Scheduled Meetings and Webinars..."))
        from_date = options['from_date']
        to_date = options['to_date']
        
        if not from_date and not to_date:
             today = datetime.now()
             from_date = (today - timedelta(days=30)).strftime('%Y-%m-%d')
             to_date = (today + timedelta(days=30)).strftime('%Y-%m-%d')
             self.stdout.write(self.style.NOTICE(f"Note: No dates specified. Defaulting to range: {from_date} to {to_date}"))

        # --- STEP 1: Get Recording Map for Lookup ---
        self.stdout.write(self.style.MIGRATE_HEADING("\n📹 Fetching All Available Recording Data..."))
        recording_map = api_service.get_recording_map() # Requires the new service method
        
        # --- STEP 2: Get Meetings/Webinars ---
        meetings = api_service.list_meetings(from_date=from_date, to_date=to_date)
        webinars = api_service.list_webinars(from_date=from_date, to_date=to_date)
        
        all_events = []
        
        # Helper function to process and merge data
        def process_event(event, event_type):
            event_id = str(event.get('id', 'N/A'))
            recording_link = "N/A (No Recording Found)"
            
            # Check the recording map using the event ID
            if event_id in recording_map:
                files = recording_map[event_id]
                # Try to find the primary recording file link (MP4)
                for f in files:
                    # Look for play_url first for viewing ease
                    if f.get('file_type') == 'MP4' and f.get('play_url'):
                        recording_link = f.get('play_url')
                        break
                # Fallback to the first available play/download link if MP4 not found
                if recording_link == "N/A (No Recording Found)" and files:
                    recording_link = files[0].get('play_url') or files[0].get('download_url', 'N/A (Link Missing)')

            return {
                "Type": event_type,
                "Topic": event.get('topic', 'N/A'),
                "ID": event_id,
                "Start Time": event.get('start_time', 'N/A'),
                "Join Link": event.get('join_url', 'N/A'),
                "Start Link": event.get('start_url', 'N/A'),
                "Recording Link": recording_link
            }

        # Process Meetings and Webinars
        for m in meetings:
            all_events.append(process_event(m, "MEETING"))
            
        for w in webinars:
            all_events.append(process_event(w, "WEBINAR"))

        self.stdout.write(f"Total Events Found: {len(all_events)}")
        
        # --- STEP 3: Print Output with Recording Link ---
        for item in all_events:
            self.stdout.write(f"\n--- {item['Type']} - ID: {item['ID']} ---")
            self.stdout.write(self.style.NOTICE(f"Topic: {item['Topic']}"))
            self.stdout.write(f"Start Time: {item['Start Time']}")
            self.stdout.write(f"Join URL: {self.style.SUCCESS(item['Join Link'])}")
            self.stdout.write(f"Start URL: {self.style.WARNING(item['Start Link'])}")
            
            # Print Recording Link with appropriate color
            if item['Recording Link'].startswith('http'):
                self.stdout.write(self.style.SUCCESS(f"Recording URL: {item['Recording Link']}"))
            else:
                self.stdout.write(f"Recording URL: {item['Recording Link']}")

    def _handle_search_topic(self, api_service, options):
        topic = options['search_topic']
        days_range = options['days_range']
        
        # Use current time as the target date for searching
        target_date = datetime.now()
        
        self.stdout.write(self.style.MIGRATE_HEADING(f"\n🔍 Searching for Topic: '{topic}'"))
        self.stdout.write(f"Searching {days_range} days around {target_date.strftime('%Y-%m-%d %H:%M')}")
        
        matching_items = api_service.search_meetings(
            scheduled_date=target_date, 
            topic=topic, 
            days_range=days_range
        )
        
        if matching_items:
            self.stdout.write(self.style.SUCCESS(f"✅ Found {len(matching_items)} potential match(es):"))
            for i, item in enumerate(matching_items[:5], 1):
                self.stdout.write(f"\n--- MATCH #{i} ({item['type'].upper()}) - ID: {item['id']} ---")
                self.stdout.write(self.style.NOTICE(f"Topic: {item['topic']}")) 
                self.stdout.write(f"Score: {item['match_score']} (Reasons: {', '.join(item['match_reasons'])})")
                self.stdout.write(f"Scheduled Time: {item['scheduled_date_formatted']} ({item['timezone']})")
                self.stdout.write(f"Join URL: {item['join_url']}")
        else:
            self.stdout.write(self.style.WARNING(f"⚠️ No matching events found for topic '{topic}'."))


    def _handle_get_recordings(self, api_service, options):
        meeting_id = options['meeting_id']
        self.stdout.write(self.style.MIGRATE_HEADING(f"\n📹 Fetching Recording Files for Meeting ID: {meeting_id}"))
        
        try:
            recording_files = api_service.get_meeting_recordings(meeting_id)
            
            if recording_files:
                self.stdout.write(self.style.SUCCESS(f"✅ Found {len(recording_files)} recording file(s):"))
                
                # Check for existing local meeting object (only if model was successfully imported)
                if ZoomMeeting:
                    try:
                        local_meeting = ZoomMeeting.objects.get(zoom_meeting_id=meeting_id)
                        self.stdout.write(self.style.NOTICE(f"Local Meeting Topic: {local_meeting.topic}"))
                    except ZoomMeeting.DoesNotExist:
                        self.stdout.write(self.style.WARNING(f"Warning: No local DB record (ZoomMeeting) found for ID {meeting_id}."))

                
                for i, file in enumerate(recording_files, 1):
                    self.stdout.write(f"\n  File #{i}: {file.get('recording_type')}")
                    self.stdout.write(f"  - File ID: {file.get('id')}")
                    self.stdout.write(f"  - File Type: {file.get('file_type')} ({file.get('file_extension')})")
                    self.stdout.write(f"  - Size: {round(file.get('file_size', 0) / (1024 * 1024), 2)} MB")
                    self.stdout.write(f"  - Download URL: {self.style.SUCCESS(file.get('download_url', 'N/A'))}")
            else:
                self.stdout.write(self.style.WARNING(f"⚠️ No recording files found for Meeting ID {meeting_id}."))

        except Exception as e:
            self.stdout.write(self.style.ERROR(f"❌ Error fetching recordings: {e}"))
            raise CommandError(f"Error fetching recordings: {e}")

    def _handle_list_all_recordings(self, api_service):
        """Helper to list all available cloud recordings."""
        self.stdout.write(self.style.MIGRATE_HEADING("\n📹 Listing All Cloud Recordings (Last 90 Days)..."))
        
        try:
            all_recordings = api_service.list_recordings()
            
            if not all_recordings:
                self.stdout.write(self.style.WARNING("⚠️ No cloud recordings found in the last 90 days."))
                return

            self.stdout.write(self.style.SUCCESS(f"✅ Found {len(all_recordings)} total recordings."))
            
            for i, meeting_data in enumerate(all_recordings, 1):
                self.stdout.write(f"\n--- RECORDING #{i} - MEETING ID: {meeting_data.get('id', 'N/A')} ---")
                self.stdout.write(self.style.NOTICE(f"Topic: {meeting_data.get('topic', 'N/A')}"))
                self.stdout.write(f"Start Time: {meeting_data.get('start_time', 'N/A')}")
                
                recording_files = meeting_data.get('recording_files', [])
                self.stdout.write(f"Files Found: {len(recording_files)}")
                
                for j, file in enumerate(recording_files, 1):
                    file_size_bytes = file.get('file_size', 0)
                    file_size_mb = round(file_size_bytes / (1024 * 1024), 2)
                    
                    self.stdout.write(f"  - File {j}: {file.get('recording_type', 'Unknown')} ({file.get('file_type')})")
                    self.stdout.write(f"    Size: {file_size_mb} MB")
                    self.stdout.write(f"    Download URL: {self.style.SUCCESS(file.get('download_url', 'N/A'))}")
                    self.stdout.write(f"    Play URL: {file.get('play_url', 'N/A')}")
            
        except Exception as e:
            self.stdout.write(self.style.ERROR(f"❌ Error listing all recordings: {e}"))
            raise CommandError(f"Error listing all recordings: {e}")