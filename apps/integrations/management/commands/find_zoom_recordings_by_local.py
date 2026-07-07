# management/commands/find_zoom_recordings_by_local.py
import logging
import time
from django.core.management.base import BaseCommand
from apps.integrations.services import ZoomAPIService
from apps.webinars.models import Webinar
from apps.integrations.models import (
    ZoomMeeting,
    ZoomWebinar,
    ZoomRecording
)

logger = logging.getLogger(__name__)

class Command(BaseCommand):
    help = 'Search Zoom API using LOCAL webinar zoom_url links (REVERSE lookup)'

    def add_arguments(self, parser):
        parser.add_argument(
            '--webinar-id',
            type=str,
            help='Filter by specific webinar ID'
        )
        parser.add_argument(
            '--webinar-type',
            type=str,
            choices=['live', 'recorded', 'all'],
            default='all',
            help='Filter by webinar type'
        )

    def handle(self, *args, **options):
        self.stdout.write('🔍 REVERSE LOOKUP: Local → Zoom API...', self.style.SUCCESS)
        
        zoom_api = ZoomAPIService()
        webinar_id = options['webinar_id']
        webinar_type = options['webinar_type']

        try:
            # 1. Get ALL local webinars with zoom_url
            local_webinars = self.get_local_webinars_with_urls(webinar_id, webinar_type)
            
            self.stdout.write(
                self.style.SUCCESS(f'📊 Found {len(local_webinars)} webinars with zoom_url')
            )

            # 2. Fetch ALL Zoom recordings from API
            self.stdout.write('📡 Fetching ALL Zoom recordings...')
            all_zoom_recordings = self.fetch_all_zoom_recordings(zoom_api)
            
            self.stdout.write(
                self.style.SUCCESS(f'✅ Found {len(all_zoom_recordings)} Zoom recordings')
            )

            # 3. REVERSE MATCH: Search Zoom using local zoom_url
            matches = self.reverse_search_matches(local_webinars, all_zoom_recordings)
            
            # 4. Display results
            self.display_reverse_matches(matches)
            
        except Exception as e:
            self.stdout.write(
                self.style.ERROR(f'❌ Error: {str(e)}')
            )
            logger.error(f"Command failed: {str(e)}", exc_info=True)

    def get_local_webinars_with_urls(self, webinar_id, webinar_type):
        """Get local webinars with zoom_url - FIXED speaker field"""
        webinars = Webinar.objects.filter(
            zoom_url__isnull=False,
            zoom_url__regex=r'zoom\.us.*rec',  # Only Zoom recording URLs
            status__in=['completed', 'available']
        ).select_related('speaker')
        
        if webinar_id:
            webinars = webinars.filter(webinar_id=webinar_id)
        
        if webinar_type != 'all':
            webinars = webinars.filter(webinar_type=webinar_type)
        
        # ✅ FIXED: Use correct speaker fields (no full_name)
        return list(webinars.values(
            'webinar_id', 'title', 'status', 'webinar_type', 
            'zoom_url', 'speaker_id', 'created_at'
        ))

    def fetch_all_zoom_recordings(self, zoom_api):
        """Fetch ALL Zoom recordings"""
        all_recordings = []
        page_count = 0
        
        while True:
            self.stdout.write(f'📄 Zoom page {page_count + 1}...')
            recordings = zoom_api.list_recordings()
            
            if not recordings:
                break
                
            all_recordings.extend(recordings)
            page_count += 1
            time.sleep(1)
        
        return all_recordings

    def reverse_search_matches(self, local_webinars, zoom_recordings):
        """REVERSE: For each local zoom_url, find matching Zoom recording"""
        matches = []
        
        for webinar in local_webinars:
            zoom_url = webinar['zoom_url']
            webinar_id = webinar['webinar_id']
            
            matching_zoom_recordings = []
            
            # Search ALL Zoom recordings for this webinar's zoom_url
            for zoom_rec in zoom_recordings:
                recording_id = zoom_rec.get('id', '')
                
                # Match if zoom_url contains recording ID
                if recording_id in zoom_url:
                    matching_zoom_recordings.append({
                        'zoom_recording_id': recording_id,
                        'meeting_topic': zoom_rec.get('topic', ''),
                        'meeting_start': zoom_rec.get('start_time'),
                        'total_duration': zoom_rec.get('total_duration'),
                        'total_size_mb': round(zoom_rec.get('total_size', 0) / (1024 * 1024), 1),
                        'files': self.extract_zoom_files(zoom_rec)
                    })
            
            matches.append({
                'local_webinar': webinar,
                'zoom_matches': matching_zoom_recordings,
                'match_count': len(matching_zoom_recordings)
            })
        
        return matches

    def extract_zoom_files(self, zoom_rec):
        """Extract all playable files from Zoom recording"""
        files = []
        meetings = zoom_rec.get('meetings', [])
        
        for meeting in meetings:
            rec_files = meeting.get('recording_files', [])
            for file_obj in rec_files:
                if file_obj.get('play_url'):
                    files.append({
                        'file_type': file_obj.get('file_type'),
                        'play_url': file_obj.get('play_url'),
                        'download_url': file_obj.get('download_url'),
                        'duration': file_obj.get('duration'),
                        'file_size_mb': round(file_obj.get('file_size', 0) / (1024 * 1024), 1)
                    })
        return files

    def display_reverse_matches(self, matches):
        """Display REVERSE lookup results"""
        self.stdout.write('\n' + '=' * 120)
        self.stdout.write(self.style.SUCCESS('🔍 REVERSE MATCH RESULTS: Local zoom_url → Zoom Recordings'))
        self.stdout.write('=' * 120)
        
        # Webinars WITH Zoom matches
        has_matches = [m for m in matches if m['match_count'] > 0]
        self.stdout.write(f'\n✅ {len(has_matches)} webinars FOUND in Zoom:')
        self.stdout.write(f"{'WEBINAR':<15} {'TITLE':<35} {'ZOOM URL':<45} {'MATCHED':<10}")
        self.stdout.write('=' * 120)
        
        for match in has_matches[:15]:
            webinar = match['local_webinar']
            url_preview = webinar['zoom_url'][:42] + '...' if len(webinar['zoom_url']) > 45 else webinar['zoom_url']
            
            self.stdout.write(f"{webinar['webinar_id']:<15} {webinar['title'][:32]:<35} "
                            f"{url_preview:<45} {match['match_count']:<10} recordings")
            
            # Show matched Zoom recordings
            for zoom_rec in match['zoom_matches'][:2]:
                self.stdout.write(f"  📹 {zoom_rec['meeting_topic'][:60]}")
                for file_obj in zoom_rec['files'][:1]:
                    self.stdout.write(f"    🔗 {file_obj['play_url'][:70]}...")
        
        # Webinars WITHOUT Zoom matches (MISSING!)
        missing_matches = [m for m in matches if m['match_count'] == 0]
        self.stdout.write(f'\n❌ {len(missing_matches)} webinars NOT FOUND in Zoom:')
        self.stdout.write(f"{'WEBINAR':<15} {'TITLE':<35} {'ZOOM URL':<45}")
        self.stdout.write('=' * 120)
        
        for match in missing_matches[:10]:
            webinar = match['local_webinar']
            url_preview = webinar['zoom_url'][:42] + '...' if len(webinar['zoom_url']) > 45 else webinar['zoom_url']
            self.stdout.write(f"{webinar['webinar_id']:<15} {webinar['title'][:32]:<35} {url_preview:<45}")
        
        # SUMMARY
        total_webinars = len(matches)
        found_count = len(has_matches)
        missing_count = len(missing_matches)
        
        self.stdout.write('\n' + '=' * 120)
        self.stdout.write(self.style.SUCCESS(f'''
📊 REVERSE LOOKUP SUMMARY:
   📋 Total Local Webinars w/ zoom_url: {total_webinars}
   ✅ FOUND in Zoom API: {found_count}
   ❌ MISSING from Zoom: {missing_count}
   🔗 Total Playable Links Found: {sum(m['match_count'] for m in matches)}
        '''))
