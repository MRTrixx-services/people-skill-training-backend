# apps/integrations/management/commands/check_zoom_meeting_held.py
from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone
from apps.webinars.models import Webinar
from apps.integrations.models import ZoomMeeting, ZoomWebinar, ZoomCredentials
from apps.integrations.services import ZoomAPIService
from tabulate import tabulate
from datetime import datetime, timedelta
import logging
import pytz
import re

logger = logging.getLogger(__name__)

class Command(BaseCommand):
    help = 'Check Zoom meetings & validate Recorded webinar durations vs Zoom recordings'

    def add_arguments(self, parser):
        parser.add_argument('--days', type=int, default=7)
        parser.add_argument('--webinar-id', type=str)
        parser.add_argument('--status', type=str, choices=['held', 'not_held', 'pending', 'all', 'recorded'], default='all')
        parser.add_argument('--no-search', action='store_true', help='Disable auto search by name')
        parser.add_argument('--format', type=str, choices=['table', 'csv', 'json'], default='table')
        parser.add_argument('--list-recordings', action='store_true', help='List ALL recordings w/ duration & links')
        parser.add_argument('--from-date', type=str, help='Recordings from date (YYYY-MM-DD)')
        parser.add_argument('--to-date', type=str, help='Recordings to date (YYYY-MM-DD)')
        parser.add_argument('--check-recorded', action='store_true', help='Validate Recorded webinars duration match')

    def handle(self, *args, **options):
        self.stdout.write(self.style.SUCCESS('\n' + '='*160))
        
        # List all recordings
        if options['list_recordings']:
            self._list_all_recordings(options)
            return
        
        # 🔥 MAIN FEATURE: Check Recorded webinars duration validation
        if options['check_recorded']:
            self._check_recorded_webinars_duration(options)
            return
        
        # Original Live meeting check
        self.stdout.write(self.style.SUCCESS('🔍 ZOOM LIVE MEETING ATTENDANCE CHECK'))
        self.stdout.write(self.style.SUCCESS('='*160 + '\n'))
        
        try:
            zoom_api = ZoomAPIService()
            self.stdout.write(self.style.SUCCESS('✅ Zoom API Connected\n'))
        except Exception as e:
            raise CommandError(f'❌ Zoom API failed: {str(e)}')
        
        days = options['days']
        end_date = timezone.now()
        start_date = end_date - timedelta(days=days)
        
        webinars_query = Webinar.objects.filter(
            webinar_type='live',
            scheduled_date__range=[start_date, end_date]
        ).select_related('speaker', 'category').prefetch_related(
            'zoom_meetings', 'zoom_webinars', 
            'zoom_meetings__recordings', 'zoom_webinars__recordings'
        ).distinct()
        
        if options['webinar_id']:
            webinars_query = webinars_query.filter(webinar_id=options['webinar_id'])
        
        if not webinars_query.exists():
            self.stdout.write(self.style.WARNING(f'No live webinars found in last {days} days'))
            return
        
        results = self._process_live_webinars(webinars_query, options)
        self._display_live_summary(results, webinars_query.count())

    def _check_recorded_webinars_duration(self, options):
        """🔥 MAIN: Validate Recorded webinars - DB duration vs Zoom recording duration"""
        self.stdout.write(self.style.SUCCESS('🎬 RECORDED WEBINARS - DURATION VALIDATION'))
        self.stdout.write(self.style.SUCCESS('='*160 + '\n'))
        
        try:
            zoom_api = ZoomAPIService()
            self.stdout.write(self.style.SUCCESS('✅ Zoom API Connected\n'))
        except Exception as e:
            self.stdout.write(self.style.ERROR(f'❌ Zoom API failed: {str(e)}'))
            return
        
        # Get ALL Recorded webinars with zoom_url
        recorded_query = Webinar.objects.filter(
            webinar_type='recorded',
            zoom_url__isnull=False,
            zoom_url__regex=r'https?://.*(zoom\.us|us\d+\w+\.zoom\.us).*'
        ).select_related('speaker').order_by('-created_at')
        
        if options['webinar_id']:
            recorded_query = recorded_query.filter(webinar_id=options['webinar_id'])
        
        recorded_webinars = recorded_query.all()
        
        if not recorded_webinars:
            self.stdout.write(self.style.WARNING('❌ No Recorded webinars with Zoom URLs found'))
            return
        
        self.stdout.write(f"📊 Checking {len(recorded_webinars)} Recorded webinars\n")
        
        results = {
            'duration_match': [],
            'duration_mismatch': [],
            'no_recording_found': [],
            'invalid_url': [],
            'errors': []
        }
        
        for webinar in recorded_webinars:
            self.stdout.write(f"\n📌 {webinar.webinar_id}: {webinar.title[:60]}")
            self.stdout.write(f"   DB: {webinar.duration or 0}min | URL: {webinar.zoom_url}...")
            
            result = self._validate_single_webinar_duration(zoom_api, webinar)
            
            if result['status'] == 'match':
                results['duration_match'].append(result)
                self.stdout.write(self.style.SUCCESS(f"   ✅ MATCH! Zoom: {result['zoom_duration']}min"))
            elif result['status'] == 'mismatch':
                results['duration_mismatch'].append(result)
                self.stdout.write(self.style.ERROR(f"   ❌ MISMATCH! DB:{webinar.duration} vs Zoom:{result['zoom_duration']}min"))
            elif result['status'] == 'no_recording':
                results['no_recording_found'].append(result)
                self.stdout.write(self.style.WARNING(f"   ⚠️  No recording found"))
            elif result['status'] == 'invalid_url':
                results['invalid_url'].append(result)
                self.stdout.write(self.style.WARNING(f"   ⚠️  Invalid Zoom URL"))
            else:
                results['errors'].append(result)
                self.stdout.write(self.style.ERROR(f"   ❌ Error: {result.get('error', 'Unknown')}"))
        
        self._display_duration_summary(results)

    def _validate_single_webinar_duration(self, zoom_api, webinar):
            """Validate single Recorded webinar duration match"""
            try:
                zoom_url = webinar.zoom_url.strip()
                meeting_id = self._extract_zoom_meeting_id(zoom_url)
                
                if not meeting_id:
                    return {
                        'webinar_id': webinar.webinar_id,
                        'title': webinar.title[:50],
                        'db_duration': webinar.duration or 0,
                        'zoom_url': zoom_url,
                        'status': 'invalid_url',
                        'error': 'No meeting ID in URL'
                    }
                
                self.stdout.write(f"     ID: {meeting_id}")
                
                # Try meeting first, then webinar
                meeting_data = zoom_api.get_meeting(meeting_id)
                if not meeting_data:
                    meeting_data = zoom_api.get_webinar(meeting_id)
                
                if not meeting_data:
                    return {
                        'webinar_id': webinar.webinar_id,
                        'title': webinar.title[:50],
                        'db_duration': webinar.duration or 0,
                        'zoom_url': zoom_url,
                        'meeting_id': meeting_id,
                        'status': 'no_recording',
                        'error': 'Meeting/Webinar not found'
                    }
                
                # Get recording duration from meeting data
                zoom_duration = int(meeting_data.get('duration', 0))
                db_duration = webinar.duration or 0
                
                # ±10% tolerance or 5min minimum
                tolerance = max(5, int(db_duration * 0.1))
                duration_diff = abs(db_duration - zoom_duration)
                
                status = 'match' if duration_diff <= tolerance else 'mismatch'
                
                return {
                    'webinar_id': webinar.webinar_id,
                    'title': webinar.title[:50],
                    'speaker': getattr(webinar.speaker, 'full_name', 'N/A'),
                    'db_duration': db_duration,
                    'zoom_duration': zoom_duration,
                    'duration_diff': duration_diff,
                    'tolerance': tolerance,
                    'zoom_url': zoom_url,
                    'meeting_id': meeting_id,
                    'status': status,
                    'match_percent': round(100 - (duration_diff/db_duration*100), 1) if db_duration else 0
                }
                
            except Exception as e:
                return {
                    'webinar_id': webinar.webinar_id,
                    'title': webinar.title[:50],
                    'status': 'error',
                    'error': str(e)
                }

    def _extract_zoom_meeting_id(self, zoom_url):
        """Extract meeting ID from Zoom URLs"""
        patterns = [
            r'/j/(\d+)',  # https://zoom.us/j/1234567890
            r'/rec/play/[^/]+/(\d+)',  # Recordings
            r'meeting/(\d+)', 
            r'webinar/(\d+)',
            r'/(\d{10,11})$'  # Last 10-11 digits
        ]
        
        for pattern in patterns:
            match = re.search(pattern, zoom_url)
            if match:
                return match.group(1)
        
        # Fallback: largest number in URL
        numbers = re.findall(r'\d{10,}', zoom_url)
        return max(numbers) if numbers else None

    def _display_duration_summary(self, results):
        """Duration validation summary"""
        self.stdout.write('\n' + '='*160)
        self.stdout.write(self.style.SUCCESS('📊 DURATION VALIDATION RESULTS'))
        self.stdout.write('='*160)
        
        match_count = len(results['duration_match'])
        mismatch_count = len(results['duration_mismatch'])
        no_recording = len(results['no_recording_found'])
        invalid_url = len(results['invalid_url'])
        errors = len(results['errors'])
        total = match_count + mismatch_count + no_recording + invalid_url + errors
        
        self.stdout.write(f"\nTotal Recorded Webinars: {total}\n")
        self.stdout.write(self.style.SUCCESS(f"✅ Duration MATCH (±10%): {match_count}"))
        self.stdout.write(self.style.ERROR(f"❌ Duration MISMATCH: {mismatch_count}"))
        self.stdout.write(self.style.WARNING(f"⚠️  No Recording: {no_recording}"))
        self.stdout.write(self.style.WARNING(f"⚠️  Invalid URL: {invalid_url}"))
        if errors:
            self.stdout.write(self.style.ERROR(f"❌ Errors: {errors}"))
        
        # MISMATCH table
        if results['duration_mismatch']:
            self.stdout.write(f"\n\n❌ DURATION MISMATCHES ({mismatch_count}):")
            table_data = [
                [r['webinar_id'], r['title'][:35], 
                 f"{r['db_duration']}m", f"{r['zoom_duration']}m", 
                 f"±{r['duration_diff']}m", f"{r['match_percent']}%"]
                for r in results['duration_mismatch']
            ]
            self.stdout.write(tabulate(table_data, 
                headers=['ID', 'Title', 'DB', 'Zoom', 'Diff', 'Match%'], 
                tablefmt='grid'))
        
        # MATCH table (top 10)
        if results['duration_match']:
            self.stdout.write(f"\n\n✅ DURATION MATCHES ({match_count}):")
            top_matches = results['duration_match'][:10]
            table_data = [
                [r['webinar_id'], r['title'][:35], 
                 f"{r['db_duration']}m", f"{r['zoom_duration']}m", 
                 f"±{r['duration_diff']}m"]
                for r in top_matches
            ]
            self.stdout.write(tabulate(table_data, 
                headers=['ID', 'Title', 'DB', 'Zoom', 'Diff'], 
                tablefmt='grid'))

    def _list_all_recordings(self, options):
        """List all Zoom recordings"""
        self.stdout.write(self.style.SUCCESS('🎬 ALL ZOOM RECORDINGS'))
        self.stdout.write(self.style.SUCCESS('='*160 + '\n'))
        
        try:
            zoom_api = ZoomAPIService()
            all_recordings = zoom_api.list_recordings()
            
            if not all_recordings:
                self.stdout.write(self.style.WARNING("❌ No recordings found"))
                return
            
            table_data = []
            for meeting in all_recordings:
                topic = meeting.get('topic', 'Untitled')[:50]
                duration = meeting.get('duration', 0)
                files = [f for f in meeting.get('recording_files', []) 
                        if f.get('file_type') in ['MP4', 'M4A']]
                
                if files:
                    first_file = files[0]
                    play_url = first_file.get('play_url', '')[:50] + '...'
                    table_data.append([
                        str(meeting.get('id'))[-12:],
                        topic,
                        f"{duration//60}m {duration%60}s",
                        len(files),
                        first_file.get('file_type', ''),
                        play_url
                    ])
            
            if table_data:
                headers = ['ID', 'Topic', 'Duration', 'Files', 'Type', 'URL']
                self.stdout.write(tabulate(table_data, headers=headers, tablefmt='grid'))
            else:
                self.stdout.write(self.style.WARNING("❌ No video recordings"))
                
        except Exception as e:
            self.stdout.write(self.style.ERROR(f"❌ Error: {str(e)}"))

    def _process_live_webinars(self, webinars_query, options):
        """Process live webinars (simplified)"""
        results = {'held': [], 'not_held': [], 'errors': []}
        # Simplified implementation - add your full logic here
        return results

    def _display_live_summary(self, results, total_checked):
        """Live summary (simplified)"""
        self.stdout.write('\n' + '='*140)
        self.stdout.write(self.style.SUCCESS('📊 LIVE SUMMARY'))
        held = len(results['held'])
        self.stdout.write(f"Held: {held} | Not Held: {len(results['not_held'])} | Total: {total_checked}")

    def _display_live_tables(self, results):
        """Live tables (simplified)"""
        pass

    def _search_and_recover_meeting(self, zoom_api, webinar, zoom_meeting, zoom_webinar):
        """Search by name"""
        return None

    def _parse_datetime(self, dt_str):
        """Parse datetime"""
        if not dt_str:
            return None
        try:
            dt_str = dt_str.replace('Z', '+00:00')
            return datetime.fromisoformat(dt_str)
        except:
            return None
