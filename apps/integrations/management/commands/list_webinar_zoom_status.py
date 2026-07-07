# apps/integrations/management/commands/check_zoom_meeting_held.py
from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone
from apps.webinars.models import Webinar
from apps.integrations.models import ZoomMeeting, ZoomWebinar
from apps.integrations.services import ZoomAPIService
from tabulate import tabulate
from datetime import datetime, timedelta
import logging
import pytz


logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = 'Check if Zoom meetings were held & auto-search by name for meetings & recordings'

    def add_arguments(self, parser):
        parser.add_argument('--days', type=int, default=7)
        parser.add_argument('--webinar-id', type=str)
        parser.add_argument('--status', type=str, choices=['held', 'not_held', 'pending', 'all'], default='all')
        parser.add_argument('--no-search', action='store_true', help='Disable auto search by name')
        parser.add_argument('--format', type=str, choices=['table', 'csv', 'json'], default='table')

    def handle(self, *args, **options):
        self.stdout.write(self.style.SUCCESS('\n' + '='*140))
        self.stdout.write(self.style.SUCCESS('🔍 ZOOM MEETING ATTENDANCE CHECK - Was Meeting Held?'))
        self.stdout.write(self.style.SUCCESS('='*140 + '\n'))
        
        try:
            zoom_api = ZoomAPIService()
            self.stdout.write(self.style.SUCCESS('✅ Zoom API Connected\n'))
        except Exception as e:
            raise CommandError(f'❌ Failed to initialize Zoom API: {str(e)}')
        
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
            self.stdout.write(self.style.WARNING(f'❌ No webinars found in last {days} days'))
            return
        
        results = {
            'held': [],
            'not_held': [],
            'pending': [],
            'no_zoom': [],
            'errors': [],
            'recovered_by_name': [],
            'recordings_found': [],
        }
        
        total_checked = 0
        now = timezone.now()
        auto_search = not options.get('no_search', False)
        
        for webinar in webinars_query:
            total_checked += 1
            
            zoom_meeting = webinar.zoom_meetings.first()
            zoom_webinar = webinar.zoom_webinars.first()
            zoom_obj = zoom_meeting or zoom_webinar
            
            if not zoom_obj:
                results['no_zoom'].append({'webinar_id': webinar.webinar_id, 'title': webinar.title[:50]})
                continue
            
            zoom_id = zoom_obj.zoom_meeting_id if zoom_meeting else zoom_obj.zoom_webinar_id
            
            self.stdout.write(f"\n📌 [{total_checked}] {webinar.webinar_id}: {webinar.title[:50]}")
            self.stdout.write(f"   Scheduled: {webinar.scheduled_date.strftime('%Y-%m-%d %H:%M %Z')}")
            
            try:
                if zoom_meeting:
                    meeting_data = zoom_api.get_meeting(zoom_id)
                else:
                    meeting_data = zoom_api.get_webinar(zoom_id)
                
                recovered_zoom_id = zoom_id  # Track which ID we're using
                
                if not meeting_data:
                    self.stdout.write(self.style.WARNING(f"   ⚠️  Meeting not found by ID {zoom_id}"))
                    
                    # AUTO-SEARCH: Try searching by name if enabled
                    if auto_search:
                        self.stdout.write(f"   🔍 Auto-searching Zoom by title...")
                        recovery_result = self._search_and_recover_meeting(zoom_api, webinar, zoom_meeting, zoom_webinar)
                        
                        if recovery_result:
                            self.stdout.write(self.style.SUCCESS(f"   ✅ RECOVERED MEETING! Found as: {recovery_result['zoom_id']}"))
                            results['recovered_by_name'].append(recovery_result)
                            
                            # Use recovered ID
                            recovered_zoom_id = recovery_result['zoom_id']
                            
                            # Fetch the recovered meeting data
                            if zoom_meeting:
                                meeting_data = zoom_api.get_meeting(recovered_zoom_id)
                            else:
                                meeting_data = zoom_api.get_webinar(recovered_zoom_id)
                            
                            # If still no data, mark as recovered but no data
                            if not meeting_data:
                                results['not_held'].append({
                                    'webinar_id': webinar.webinar_id,
                                    'title': webinar.title[:50],
                                    'instructor': webinar.speaker.full_name if webinar.speaker else 'N/A',
                                    'scheduled_time': webinar.scheduled_date.strftime('%Y-%m-%d %H:%M'),
                                    'zoom_id': recovered_zoom_id,
                                    'status': 'recovered_but_no_data',
                                    'actual_start': '❌ No data',
                                    'participants': 0,
                                })
                                continue
                            # Fall through to process recovered meeting
                        else:
                            # Meeting not found, try searching for recording
                            self.stdout.write(f"   🎬 Meeting not found, auto-searching for recordings...")
                            recording_result = self._search_and_recover_recording(zoom_api, webinar)
                            
                            if recording_result:
                                self.stdout.write(self.style.SUCCESS(f"   ✅ RECOVERED RECORDING! Found {recording_result['recording_count']} files"))
                                results['recordings_found'].append(recording_result)
                                continue
                            
                            self.stdout.write(self.style.ERROR(f"   ❌ Not found in meetings or recordings"))
                            
                            # Add to not_held only if NOT recovered
                            results['not_held'].append({
                                'webinar_id': webinar.webinar_id,
                                'title': webinar.title[:50],
                                'instructor': webinar.speaker.full_name if webinar.speaker else 'N/A',
                                'scheduled_time': webinar.scheduled_date.strftime('%Y-%m-%d %H:%M'),
                                'zoom_id': zoom_id,
                                'status': 'not_found_in_zoom',
                                'actual_start': '❌ Not found',
                                'participants': 0,
                            })
                            continue
                    else:
                        # Auto-search disabled
                        results['not_held'].append({
                            'webinar_id': webinar.webinar_id,
                            'title': webinar.title[:50],
                            'instructor': webinar.speaker.full_name if webinar.speaker else 'N/A',
                            'scheduled_time': webinar.scheduled_date.strftime('%Y-%m-%d %H:%M'),
                            'zoom_id': zoom_id,
                            'status': 'not_found_in_zoom',
                            'actual_start': '❌ Not found',
                            'participants': 0,
                        })
                        continue
                
                # Successfully found meeting - process it
                try:
                    if zoom_meeting:
                        participants_data = zoom_api.get_meeting_participants(recovered_zoom_id)
                    else:
                        participants_data = zoom_api.get_webinar_participants(recovered_zoom_id)
                except (AttributeError, TypeError):
                    participants_data = []
                
                total_participants = len(participants_data) if participants_data else 0
                
                actual_start_str = meeting_data.get('start_time')
                actual_end_str = meeting_data.get('end_time')
                
                actual_start_dt = self._parse_datetime(actual_start_str)
                actual_end_dt = self._parse_datetime(actual_end_str)
                
                if actual_start_dt and actual_start_dt.tzinfo is None:
                    actual_start_dt = pytz.UTC.localize(actual_start_dt)
                
                if actual_end_dt and actual_end_dt.tzinfo is None:
                    actual_end_dt = pytz.UTC.localize(actual_end_dt)
                
                now_aware = now if now.tzinfo else pytz.UTC.localize(now)
                
                was_held = actual_start_dt is not None
                is_currently_active = False
                
                if was_held:
                    if actual_end_dt:
                        is_currently_active = False
                    else:
                        duration_min = webinar.duration or 60
                        expected_end = actual_start_dt + timedelta(minutes=duration_min)
                        is_currently_active = actual_start_dt <= now_aware <= expected_end
                
                recordings = zoom_meeting.recordings.all() if zoom_meeting else zoom_webinar.recordings.all()
                has_recording = recordings.exists()
                recording_count = recordings.count()
                found_recordings_by_name = False
                
                # AUTO-SEARCH: If no recordings linked, search by name
                if not has_recording and was_held:
                    self.stdout.write(f"   🎬 No recordings linked, auto-searching...")
                    recording_result = self._search_and_recover_recording(zoom_api, webinar)
                    
                    if recording_result:
                        found_recordings_by_name = True
                        has_recording = True
                        recording_count = recording_result['recording_count']
                        self.stdout.write(self.style.SUCCESS(f"   ✅ Found {recording_count} recordings by name!"))
                        results['recordings_found'].append(recording_result)
                
                result_data = {
                    'webinar_id': webinar.webinar_id,
                    'title': webinar.title[:50],
                    'instructor': webinar.speaker.full_name if webinar.speaker else 'N/A',
                    'scheduled_time': webinar.scheduled_date.strftime('%Y-%m-%d %H:%M'),
                    'zoom_id': recovered_zoom_id,  # Use recovered ID if applicable
                    'zoom_status': meeting_data.get('status', 'unknown'),
                    'was_held': was_held,
                    'actual_start': actual_start_dt.strftime('%Y-%m-%d %H:%M:%S') if actual_start_dt else '❌ Not started',
                    'actual_end': actual_end_dt.strftime('%Y-%m-%d %H:%M:%S') if actual_end_dt else ('🔴 Active' if is_currently_active else '❌ Not ended'),
                    'total_participants': total_participants,
                    'has_recording': has_recording,
                    'recording_count': recording_count,
                    'found_recordings_by_name': found_recordings_by_name,
                }
                
                if webinar.scheduled_date > now:
                    results['pending'].append(result_data)
                    self.stdout.write(self.style.WARNING(f"   ⏱️  PENDING"))
                elif was_held:
                    results['held'].append(result_data)
                    status_icon = '🔴 Active Now' if is_currently_active else '✅ Held'
                    self.stdout.write(self.style.SUCCESS(f"   {status_icon}"))
                    self.stdout.write(f"      Started: {actual_start_dt.strftime('%H:%M:%S')}")
                    self.stdout.write(f"      Participants: {total_participants}")
                    if has_recording:
                        rec_source = " (auto-found)" if found_recordings_by_name else ""
                        self.stdout.write(f"      Recordings: {recording_count} ✅{rec_source}")
                else:
                    results['not_held'].append(result_data)
                    self.stdout.write(self.style.ERROR(f"   ❌ NOT HELD"))
                
            except Exception as e:
                logger.error(f"Error checking {webinar.webinar_id}: {str(e)}")
                self.stdout.write(self.style.ERROR(f"   ❌ ERROR: {str(e)}"))
                results['errors'].append({
                    'webinar_id': webinar.webinar_id,
                    'title': webinar.title[:50],
                    'error': str(e),
                })
        
        self._display_summary(results, total_checked)
        self._display_tables(results, options)

    def _search_and_recover_meeting(self, zoom_api, webinar, zoom_meeting, zoom_webinar):
        """Search Zoom for meeting by title"""
        try:
            if zoom_meeting:
                all_meetings = zoom_api.list_meetings()
            else:
                all_meetings = zoom_api.list_webinars()
            
            if not all_meetings:
                return None
            
            webinar_title_lower = webinar.title.lower()
            
            for meeting in all_meetings:
                meeting_topic = meeting.get('topic', '').lower()
                
                if webinar_title_lower in meeting_topic or meeting_topic in webinar_title_lower:
                    self.stdout.write(f"      Found match: {meeting.get('topic')}")
                    
                    zoom_id = meeting.get('id')
                    if zoom_meeting:
                        meeting_data = zoom_api.get_meeting(zoom_id)
                    else:
                        meeting_data = zoom_api.get_webinar(zoom_id)
                    
                    if meeting_data:
                        try:
                            if zoom_meeting:
                                zoom_meeting.zoom_meeting_id = str(zoom_id)
                                zoom_meeting.save(update_fields=['zoom_meeting_id'])
                            else:
                                zoom_webinar.zoom_webinar_id = str(zoom_id)
                                zoom_webinar.save(update_fields=['zoom_webinar_id'])
                            
                            self.stdout.write(self.style.SUCCESS(f"      ✅ DB Updated: {zoom_id}"))
                        except Exception as e:
                            self.stdout.write(self.style.WARNING(f"      ⚠️  Found but DB update failed: {str(e)}"))
                        
                        return {
                            'webinar_id': webinar.webinar_id,
                            'title': webinar.title[:50],
                            'instructor': webinar.speaker.full_name if webinar.speaker else 'N/A',
                            'zoom_id': str(zoom_id),
                            'old_zoom_id': webinar.zoom_meetings.first().zoom_meeting_id if zoom_meeting else webinar.zoom_webinars.first().zoom_webinar_id,
                            'found_by': 'name_search',
                        }
            
            return None
        except Exception as e:
            logger.error(f"Error searching by name: {str(e)}")
            return None

    def _search_and_recover_recording(self, zoom_api, webinar):
        """Search Zoom for recording by meeting title"""
        try:
            recordings = zoom_api.search_recordings_by_topic(webinar.title)
            
            if not recordings:
                return None
            
            first_recording = recordings[0]
            
            self.stdout.write(self.style.SUCCESS(f"      Found {len(recordings)} recording(s)"))
            self.stdout.write(f"      Meeting: {first_recording.get('topic')}")
            
            return {
                'webinar_id': webinar.webinar_id,
                'title': webinar.title[:50],
                'meeting_id': first_recording.get('id'),
                'meeting_topic': first_recording.get('topic'),
                'start_time': first_recording.get('start_time'),
                'recording_count': len(first_recording.get('recording_files', [])),
                'all_recordings': recordings,
            }
        except Exception as e:
            logger.error(f"Error searching recordings: {str(e)}")
            return None

    def _parse_datetime(self, datetime_str):
        """Parse datetime string safely"""
        if not datetime_str:
            return None
        try:
            if isinstance(datetime_str, str):
                datetime_str_clean = datetime_str.replace('Z', '+00:00')
                dt = datetime.fromisoformat(datetime_str_clean)
                if dt.tzinfo is None:
                    dt = pytz.UTC.localize(dt)
                return dt
        except (ValueError, TypeError) as e:
            logger.warning(f"⚠️ Failed to parse datetime '{datetime_str}': {e}")
        return None

    def _display_summary(self, results, total_checked):
        """Display summary"""
        self.stdout.write('\n' + '='*140)
        self.stdout.write(self.style.SUCCESS('📊 SUMMARY:'))
        self.stdout.write('='*140)
        
        held_count = len(results['held'])
        not_held_count = len(results['not_held'])
        pending_count = len(results['pending'])
        no_zoom_count = len(results['no_zoom'])
        error_count = len(results['errors'])
        recovered_count = len(results['recovered_by_name'])
        recordings_found = len(results['recordings_found'])
        
        self.stdout.write(f"\nTotal Checked: {total_checked}\n")
        self.stdout.write(self.style.SUCCESS(f"✅ Meetings HELD: {held_count}"))
        self.stdout.write(self.style.ERROR(f"❌ Meetings NOT HELD: {not_held_count}"))
        self.stdout.write(self.style.WARNING(f"⏱️  Pending/Future: {pending_count}"))
        self.stdout.write(self.style.WARNING(f"⚠️  No Zoom Integration: {no_zoom_count}"))
        if recovered_count > 0:
            self.stdout.write(self.style.SUCCESS(f"🔍 Recovered Meetings by Name: {recovered_count}"))
        if recordings_found > 0:
            self.stdout.write(self.style.SUCCESS(f"🎬 Recovered Recordings by Name: {recordings_found}"))
        if error_count > 0:
            self.stdout.write(self.style.ERROR(f"❌ Errors: {error_count}"))

    def _display_tables(self, results, options):
        """Display tables"""
        if results['held']:
            self.stdout.write(self.style.SUCCESS(f"\n\n✅ MEETINGS HELD ({len(results['held'])}):\n"))
            self._display_held_table(results['held'])
        
        if results['recovered_by_name']:
            self.stdout.write(self.style.SUCCESS(f"\n\n🔍 RECOVERED MEETINGS BY NAME ({len(results['recovered_by_name'])}):\n"))
            self._display_recovered_table(results['recovered_by_name'])
        
        if results['recordings_found']:
            self.stdout.write(self.style.SUCCESS(f"\n\n🎬 RECOVERED RECORDINGS BY NAME ({len(results['recordings_found'])}):\n"))
            self._display_recordings_table(results['recordings_found'])
        
        if results['not_held']:
            self.stdout.write(self.style.ERROR(f"\n\n❌ NOT HELD / NOT FOUND ({len(results['not_held'])}):\n"))
            self._display_not_held_table(results['not_held'])
        
        if results['pending']:
            self.stdout.write(self.style.WARNING(f"\n\n⏱️  PENDING/FUTURE ({len(results['pending'])}):\n"))
            self._display_pending_table(results['pending'])
        
        if results['no_zoom']:
            self.stdout.write(self.style.WARNING(f"\n\n⚠️  NO ZOOM INTEGRATION ({len(results['no_zoom'])}):\n"))
            self._display_no_zoom_table(results['no_zoom'])
        
        if results['errors']:
            self.stdout.write(self.style.ERROR(f"\n\n❌ ERRORS ({len(results['errors'])}):\n"))
            self._display_errors_table(results['errors'])

    def _display_held_table(self, data):
        """Display meetings that were held"""
        table_data = [
            [item['webinar_id'], item['title'][:30], item['instructor'][:20], item['zoom_id'],
             item['actual_start'][:16], str(item['total_participants']), '✅' if item['has_recording'] else '❌']
            for item in data
        ]
        headers = ['Webinar ID', 'Title', 'Instructor', 'Zoom ID', 'Start Time', 'Participants', 'Recording']
        self.stdout.write(tabulate(table_data, headers=headers, tablefmt='grid'))

    def _display_recovered_table(self, data):
        """Display meetings recovered by name"""
        table_data = [
            [item['webinar_id'], item['title'][:35], item['instructor'][:20], item['old_zoom_id'],
             '→', item['zoom_id']]
            for item in data
        ]
        headers = ['Webinar ID', 'Title', 'Instructor', 'Old Zoom ID', '', 'New Zoom ID']
        self.stdout.write(tabulate(table_data, headers=headers, tablefmt='grid'))

    def _display_recordings_table(self, data):
        """Display recordings found by name"""
        table_data = [
            [item['webinar_id'], item['title'][:35], item['meeting_topic'][:35], item['recording_count'],
             item['start_time'][:16]]
            for item in data
        ]
        headers = ['Webinar ID', 'Webinar Title', 'Meeting Title', 'Files', 'Start Time']
        self.stdout.write(tabulate(table_data, headers=headers, tablefmt='grid'))

    def _display_not_held_table(self, data):
        """Display meetings NOT held"""
        table_data = [
            [item['webinar_id'], item['title'][:35], item['instructor'][:20], item['zoom_id'],
             item['scheduled_time'], item.get('status', 'Not started')]
            for item in data
        ]
        headers = ['Webinar ID', 'Title', 'Instructor', 'Zoom ID', 'Scheduled', 'Status']
        self.stdout.write(tabulate(table_data, headers=headers, tablefmt='grid'))

    def _display_pending_table(self, data):
        """Display pending meetings"""
        table_data = [
            [item['webinar_id'], item['title'][:35], item['instructor'][:20], item['zoom_id'],
             item['scheduled_time']]
            for item in data
        ]
        headers = ['Webinar ID', 'Title', 'Instructor', 'Zoom ID', 'Scheduled']
        self.stdout.write(tabulate(table_data, headers=headers, tablefmt='grid'))

    def _display_no_zoom_table(self, data):
        """Display webinars with no Zoom integration"""
        table_data = [[item['webinar_id'], item['title'][:40]] for item in data]
        headers = ['Webinar ID', 'Title']
        self.stdout.write(tabulate(table_data, headers=headers, tablefmt='grid'))

    def _display_errors_table(self, data):
        """Display errors"""
        table_data = [
            [item['webinar_id'], item['title'][:35], item['error'][:50]]
            for item in data
        ]
        headers = ['Webinar ID', 'Title', 'Error']
        self.stdout.write(tabulate(table_data, headers=headers, tablefmt='grid'))
