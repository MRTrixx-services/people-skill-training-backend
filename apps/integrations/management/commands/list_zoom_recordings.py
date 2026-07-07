# management/commands/list_zoom_recordings.py
import logging
import time
from django.core.management.base import BaseCommand
from apps.integrations.services import ZoomAPIService
from apps.webinars.models import Webinar
from apps.integrations.models import (
    ZoomCredentials,
    ZoomMeeting,
    ZoomWebinar,
    ZoomRecording,
    ZoomWebhookEvent,
    ZoomIntegrationLog
)

logger = logging.getLogger(__name__)

class Command(BaseCommand):
    help = 'List ALL Zoom recordings from API + local database data with links (NO time limit)'

    def add_arguments(self, parser):
        parser.add_argument(
            '--webinar-id',
            type=str,
            help='Filter by specific webinar ID'
        )
        parser.add_argument(
            '--meeting-id',
            type=str,
            help='Filter by Zoom meeting ID'
        )

    def handle(self, *args, **options):
        self.stdout.write('🚀 Fetching ALL Zoom Recordings...', self.style.SUCCESS)
        
        zoom_api = ZoomAPIService()
        webinar_id = options['webinar_id']
        meeting_id = options['meeting_id']

        try:
            # 1. Fetch ALL Zoom recordings (NO time limit)
            self.stdout.write('📡 Fetching ALL recordings from Zoom API...')
            all_recordings = self.fetch_all_recordings(zoom_api)
            
            self.stdout.write(
                self.style.SUCCESS(f'✅ Found {len(all_recordings)} TOTAL recordings from Zoom API')
            )

            # 2. Get ALL webinar data (live + recorded)
            all_webinars = self.get_all_webinars(webinar_id)
            self.stdout.write(
                self.style.SUCCESS(f'📊 Found {all_webinars.count()} total webinars (live + recorded)')
            )

            # 3. Show recorded webinars with zoom_url
            self.show_recorded_webinars(all_webinars)

            # 4. Match recordings with local data + extract links
            matched_recordings = self.match_recordings(all_recordings, all_webinars, meeting_id)
            
            # 5. Get local ZoomRecording model data
            local_recordings = self.get_local_recordings(webinar_id)
            
            # 6. Display results
            self.display_results(matched_recordings, local_recordings)
            
        except Exception as e:
            self.stdout.write(
                self.style.ERROR(f'❌ Error: {str(e)}')
            )
            logger.error(f"Command failed: {str(e)}", exc_info=True)

    def fetch_all_recordings(self, zoom_api):
        """Fetch ALL recordings using your existing ZoomAPIService method"""
        all_recordings = []
        page_count = 0
        
        while True:
            self.stdout.write(f'📄 Fetching page {page_count + 1}...')
            
            # ✅ Use your existing method WITHOUT params
            recordings = zoom_api.list_recordings()
            
            if not recordings or len(recordings) == 0:
                self.stdout.write(self.style.SUCCESS('✅ No more pages'))
                break
                
            all_recordings.extend(recordings)
            page_count += 1
            
            self.stdout.write(f'   📈 Page {page_count}: {len(recordings)} recordings')
            
            # Small delay to avoid rate limiting
            time.sleep(1)
        
        return all_recordings

    def get_all_webinars(self, webinar_id):
        """Get ALL webinars (live + recorded with zoom_url)"""
        webinars = Webinar.objects.filter(
            status__in=['completed', 'available']
        )
        
        if webinar_id:
            webinars = webinars.filter(webinar_id=webinar_id)
        
        return webinars

    def show_recorded_webinars(self, webinars):
        """Display recorded webinars with zoom_url"""
        recorded_webinars = webinars.filter(webinar_type='recorded')
        live_with_recording = webinars.filter(webinar_type='live', has_recording=True)
        
        self.stdout.write(f'\n📹 RECORDED WEBINARS (zoom_url): {recorded_webinars.count()}')
        self.stdout.write(f'🎬 LIVE w/ Recordings: {live_with_recording.count()}')
        self.stdout.write('=' * 120)
        self.stdout.write(f"{'WEBINAR ID':<15} {'TITLE':<40} {'STATUS':<12} {'ZOOM URL':<50}")
        self.stdout.write('=' * 120)
        
        all_relevant_webinars = list(recorded_webinars) + list(live_with_recording)
        for webinar in all_relevant_webinars[:20]:
            zoom_url = webinar.zoom_url or '❌ NONE'
            url_preview = (zoom_url[:47] + '...') if len(zoom_url) > 50 else zoom_url
            self.stdout.write(f"{webinar.webinar_id:<15} {webinar.title[:37]:<40} "
                            f"{webinar.status:<12} {url_preview:<50}")

    def match_recordings(self, api_recordings, webinars, meeting_id):
        """Match API recordings with local webinar data INCLUDING zoom_url"""
        matched_recordings = []
        
        for recording in api_recordings:
            recording_id = recording.get('id', '')
            meeting_topic = recording.get('topic', '')
            
            # 1. Meeting ID match
            matching_webinar = None
            match_type = 'none'
            if meeting_id and meeting_id in recording_id:
                matching_webinar = webinars.filter(
                    zoom_meeting__zoom_meeting_id__icontains=meeting_id
                ).first()
                match_type = 'meeting_id'
            
            # 2. Topic/title fuzzy match
            if not matching_webinar:
                for webinar in webinars:
                    if (webinar.title.lower() in meeting_topic.lower() or 
                        meeting_topic.lower() in webinar.title.lower() or
                        webinar.title.lower() == meeting_topic.lower()):
                        matching_webinar = webinar
                        match_type = 'topic'
                        break
            
            # 3. ✅ ZOOM_URL match (NEW!)
            if not matching_webinar:
                zoom_url_match = self.find_webinar_by_zoom_url(recording, webinars)
                if zoom_url_match:
                    matching_webinar = zoom_url_match
                    match_type = 'zoom_url'
            
            # Extract recording files
            recording_files = []
            meetings = recording.get('meetings', [])
            for meeting in meetings:
                files = meeting.get('recording_files', [])
                for file_obj in files:
                    recording_files.append({
                        'file_type': file_obj.get('file_type', 'unknown'),
                        'file_size_mb': round(file_obj.get('file_size', 0) / (1024 * 1024), 1) if file_obj.get('file_size') else 0,
                        'play_url': file_obj.get('play_url', ''),
                        'download_url': file_obj.get('download_url', ''),
                        'recording_start': file_obj.get('recording_start'),
                        'duration': file_obj.get('duration', 0)
                    })
            
            matched_recordings.append({
                'zoom_recording_id': recording_id,
                'meeting_topic': meeting_topic,
                'meeting_start': recording.get('start_time'),
                'total_size_mb': round(recording.get('total_size', 0) / (1024 * 1024), 1) if recording.get('total_size') else 0,
                'total_duration': recording.get('total_duration', 0),
                'file_count': len(recording_files),
                'recording_files': recording_files,
                'local_webinar': {
                    'webinar_id': getattr(matching_webinar, 'webinar_id', None),
                    'title': getattr(matching_webinar, 'title', None),
                    'status': getattr(matching_webinar, 'status', None),
                    'zoom_url': getattr(matching_webinar, 'zoom_url', None),
                    'match_type': match_type
                },
                'local_zoom_meetings': [],
                'local_zoom_webinars': []
            })
        
        # Add local Zoom meeting/webinar data
        self.enrich_with_local_data(matched_recordings)
        return matched_recordings

    def find_webinar_by_zoom_url(self, recording, webinars):
        """Match webinar by zoom_url containing recording IDs or URLs"""
        recording_id = recording.get('id', '')
        
        for webinar in webinars:
            zoom_url = getattr(webinar, 'zoom_url', '')
            if not zoom_url:
                continue
                
            # Match if zoom_url contains recording ID
            if recording_id in zoom_url:
                self.stdout.write(f"🔗 ZOOM_URL MATCH: {recording_id[:20]} -> {webinar.webinar_id}")
                return webinar
            
            # Match recording files in zoom_url
            meetings = recording.get('meetings', [])
            for meeting in meetings:
                files = meeting.get('recording_files', [])
                for file_obj in files:
                    play_url = file_obj.get('play_url', '')
                    download_url = file_obj.get('download_url', '')
                    
                    if play_url and play_url in zoom_url:
                        self.stdout.write(f"🎥 PLAY_URL MATCH: {webinar.webinar_id}")
                        return webinar
                    if download_url and download_url in zoom_url:
                        self.stdout.write(f"📥 DOWNLOAD_URL MATCH: {webinar.webinar_id}")
                        return webinar
        
        return None

    def enrich_with_local_data(self, matched_recordings):
        """Add local ZoomMeeting, ZoomWebinar, ZoomRecording data"""
        for rec in matched_recordings:
            recording_id = rec['zoom_recording_id']
            
            # Match with ZoomMeeting recordings
            zoom_meetings = ZoomMeeting.objects.filter(
                recordings__recording_id__icontains=recording_id[:10]
            ).distinct()
            
            # Match with ZoomWebinar recordings  
            zoom_webinars = ZoomWebinar.objects.filter(
                recordings__recording_id__icontains=recording_id[:10]
            ).distinct()
            
            rec['local_zoom_meetings'] = list(zoom_meetings.values(
                'zoom_meeting_id', 'topic', 'join_url', 'created_at'
            ))
            rec['local_zoom_webinars'] = list(zoom_webinars.values(
                'zoom_webinar_id', 'topic', 'join_url', 'created_at'
            ))

    def get_local_recordings(self, webinar_id):
        """Get local ZoomRecording model data"""
        local_recordings = ZoomRecording.objects.select_related('webinar')
        if webinar_id:
            local_recordings = local_recordings.filter(webinar__webinar_id=webinar_id)
        return local_recordings.order_by('-created_at')

    def display_results(self, api_recordings, local_recordings):
        """Display formatted results"""
        self.stdout.write(self.style.SUCCESS('\n📋 ALL ZOOM RECORDINGS REPORT'))
        self.stdout.write('=' * 120)
        
        # API Recordings Summary
        self.stdout.write('\n🎥 ZOOM API RECORDINGS (with PLAY links):')
        self.stdout.write(f"{'ID':<25} {'TOPIC':<35} {'FILES':<5} {'SIZE':<10} {'DUR':<8} {'WEBINAR':<15} {'MATCH':<10}")
        self.stdout.write('=' * 120)
        
        for rec in api_recordings[:30]:
            topic = (rec['meeting_topic'][:32] + '...') if len(rec['meeting_topic']) > 32 else rec['meeting_topic']
            webinar_id = rec['local_webinar']['webinar_id'] or '❌ NONE'
            match_type = rec['local_webinar'].get('match_type', 'none')
            
            self.stdout.write(f"{rec['zoom_recording_id'][:24]:<25} {topic:<35} "
                            f"{rec['file_count']:<5} {rec['total_size_mb']:<10.1f}MB "
                            f"{rec['total_duration'] or 0:<8}min {webinar_id:<15} {match_type:<10}")
            
            # Show PLAYABLE links only
            playable_files = [f for f in rec['recording_files'] if f.get('play_url')]
            for file_obj in playable_files[:2]:
                play_url = file_obj['play_url'][:65]
                self.stdout.write(f"  🔗 PLAY: {play_url}{'...' if len(file_obj['play_url']) > 65 else ''}")
                self.stdout.write(f"      📊 {file_obj['file_type']} | {file_obj['file_size_mb']}MB | {file_obj['duration']}s")
        
        # Local Database Data
        self.stdout.write('\n' + '=' * 120)
        self.stdout.write('\n💾 LOCAL DATABASE RECORDINGS:')
        self.stdout.write(f"{'ID':<8} {'WEBINAR':<18} {'TYPE':<12} {'STATUS':<10} {'PLAY URL':<55}")
        self.stdout.write('=' * 118)
        
        for rec in local_recordings[:20]:
            webinar_id = getattr(rec.webinar, 'webinar_id', 'N/A')[:15]
            play_url = (rec.play_url[:52] + '...') if rec.play_url else '❌ NO URL'
            
            self.stdout.write(f"{rec.id:<8} {webinar_id:<18} {rec.recording_type:<12} "
                            f"{rec.status:<10} {play_url:<55}")
        
        # SUMMARY
        matched_count = sum(1 for r in api_recordings if r['local_webinar']['webinar_id'])
        zoom_url_matches = sum(1 for r in api_recordings if r['local_webinar'].get('match_type') == 'zoom_url')
        playable_count = sum(len([f for f in r['recording_files'] if f.get('play_url')]) for r in api_recordings)
        
        self.stdout.write('\n' + '=' * 120)
        self.stdout.write(self.style.SUCCESS(f'''
📊 FINAL SUMMARY:
   🎥 TOTAL API Recordings: {len(api_recordings):,}
   💾 Local ZoomRecordings: {local_recordings.count()}
   ✅ TOTAL MATCHED: {matched_count}
   🔗 ZOOM_URL Matches: {zoom_url_matches}
   🎬 PLAYABLE Links: {playable_count}
   📁 Total Files: {sum(r["file_count"] for r in api_recordings)}
   💾 Total Size: {sum(r["total_size_mb"] for r in api_recordings):.1f}MB
        '''))
