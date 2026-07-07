# your_app_name/management/commands/list_zoom_recordings.py
import json
from django.core.management.base import BaseCommand
from ...services import ZoomAPIService  # Adjust import based on your app structure
from django.core.exceptions import ValidationError

class Command(BaseCommand):
    help = 'Lists all cloud recordings from the configured Zoom account.'

    def handle(self, *args, **options):
        self.stdout.write(self.style.NOTICE("🔍 Initializing Zoom API Service..."))
        
        try:
            # Initialize the service
            zoom_service = ZoomAPIService()
            
            # Call the list_recordings method
            recordings = zoom_service.list_recordings()
            
            if not recordings:
                self.stdout.write(self.style.WARNING("⚠️ No cloud recordings found in the last 90 days."))
                return

            self.stdout.write(self.style.SUCCESS(f"\n✅ Found {len(recordings)} total cloud recordings:"))
            self.stdout.write("-" * 50)
            
            # Display detailed information for each recording
            for i, recording in enumerate(recordings, 1):
                # Safely parse and format relevant fields
                topic = recording.get('topic', 'N/A')
                start_time = recording.get('start_time', 'N/A')
                meeting_id = recording.get('id', 'N/A')
                
                # Get the recording files summary (e.g., mp4, audio_only)
                file_types = [
                    f['file_type'] for f in recording.get('recording_files', [])
                    if 'file_type' in f
                ]
                files_summary = ", ".join(set(file_types)) or "None"
                
                self.stdout.write(f"[{i}] Topic: **{topic}**")
                self.stdout.write(f"    - Meeting ID: {meeting_id}")
                self.stdout.write(f"    - Start Time: {start_time}")
                self.stdout.write(f"    - Files Available: {files_summary}")
                self.stdout.write("-" * 50)
                
            # Optional: Write the full list to a JSON file for inspection
            # self.stdout.write("\nWriting full recording data to recordings_output.json...")
            # with open('recordings_output.json', 'w') as f:
            #     json.dump(recordings, f, indent=4)
            # self.stdout.write(self.style.SUCCESS("✅ Full data written to recordings_output.json"))

        except ValidationError as e:
            self.stderr.write(self.style.ERROR(f"\n❌ Configuration Error: {e}"))
        except Exception as e:
            self.stderr.write(self.style.ERROR(f"\n❌ An unexpected error occurred: {e}"))