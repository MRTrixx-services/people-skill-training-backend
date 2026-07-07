# COMPLETE FINAL CODE - URL verification + DB update
# apps/integrations/management/commands/find_zoom_recordings.py

from django.core.management.base import BaseCommand
from apps.webinars.models import Webinar
from apps.integrations.models import ZoomCredentials
import requests
import base64
import re
from django.utils import timezone
from datetime import timedelta
from difflib import SequenceMatcher

class Command(BaseCommand):
    help = 'Match webinars to Zoom recordings + verify URLs + update DB'

    def add_arguments(self, parser):
        parser.add_argument('--days', type=int, default=90, help='Search last N days')
        parser.add_argument('--limit', type=int, default=50, help='Limit webinars')
        parser.add_argument('--threshold', type=float, default=0.4, help='Match threshold (0.3-0.8)')
        parser.add_argument('--update-db', action='store_true', help='UPDATE webinar.zoom_duration & zoom_play_url')
        parser.add_argument('--dry-run', action='store_true', help='Show what would be updated')

    def handle(self, *args, **options):
        days = options['days']
        limit = options['limit']
        threshold = options['threshold']
        update_db = options['update_db']
        dry_run = options['dry_run']
        
        if update_db and dry_run:
            self.stdout.write(self.style.WARNING('⚠️  Using --dry-run (no DB updates)'))
        
        self.stdout.write('🚀 Fetching ALL Zoom cloud recordings...')
        
        recordings = self._get_all_zoom_recordings(days)
        self.stdout.write(f'📹 {len(recordings)} MP4 recordings found')
        
        webinars = list(Webinar.objects.filter(
            webinar_type='recorded',
            zoom_url__isnull=False
        )[:limit])
        self.stdout.write(f'📊 {len(webinars)} webinars with zoom_url loaded')
        
        self._print_matches_with_url_comparison(webinars, recordings, threshold, update_db and not dry_run)

    def _get_all_zoom_recordings(self, days):
        """Get all MP4 recordings with full details"""
        credentials = ZoomCredentials.objects.filter(is_active=True).first()
        if not credentials:
            self.stdout.write(self.style.ERROR('❌ No Zoom credentials'))
            return []
            
        token = self._get_zoom_token(credentials)
        if not token:
            return []
            
        from_date = (timezone.now() - timedelta(days=days)).strftime('%Y-%m-%d')
        url = 'https://api.zoom.us/v2/users/me/recordings'
        headers = {'Authorization': f'Bearer {token}'}
        params = {'from': from_date, 'page_size': 300, 'trash_type': 'meeting_recordings'}
        
        try:
            resp = requests.get(url, headers=headers, params=params, timeout=30)
            if resp.status_code != 200:
                self.stdout.write(self.style.ERROR(f'❌ API failed: {resp.status_code}'))
                return []
                
            data = resp.json()
            meetings = data.get('meetings', [])
            
            recordings = []
            for meeting in meetings:
                for file in meeting.get('recording_files', []):
                    if file.get('file_type') == 'MP4':
                        recordings.append({
                            'topic': meeting.get('topic', ''),
                            'duration': meeting.get('duration', 0),
                            'meeting_id': str(meeting.get('id', '')),
                            'play_url': file.get('play_url', ''),
                            'download_url': file.get('download_url', ''),
                            'recording_id': file.get('id', ''),
                            'file_size_mb': round(file.get('file_size', 0) / (1024*1024), 1)
                        })
            return recordings
        except Exception as e:
            self.stdout.write(self.style.ERROR(f'❌ Error: {e}'))
            return []

    def _get_zoom_token(self, credentials):
        """Get Zoom server-to-server OAuth token"""
        try:
            token_url = f'https://zoom.us/oauth/token?grant_type=account_credentials&account_id={credentials.account_id}'
            auth_string = f'{credentials.client_id}:{credentials.client_secret}'
            auth_value = base64.b64encode(auth_string.encode()).decode()
            
            headers = {
                'Authorization': f'Basic {auth_value}',
                'Content-Type': 'application/x-www-form-urlencoded',
            }
            
            resp = requests.post(token_url, headers=headers, timeout=30)
            if resp.status_code == 200:
                return resp.json().get('access_token')
        except:
            pass
        return None

    def _print_matches_with_url_comparison(self, webinars, recordings, threshold, do_update=False):
        """🎯 Print matches + verify share/play URLs + update DB"""
        self.stdout.write('\n🔗 URL COMPARISON - Local Share vs Zoom Play:')
        self.stdout.write('=' * 130)
        
        matched_count = 0
        updated_count = 0
        strong_matches = 0
        
        for webinar in webinars:
            best_match = None
            best_score = 0
            
            # Find best title match
            for rec in recordings:
                title_score = SequenceMatcher(None, webinar.title.lower(), rec['topic'].lower()).ratio()
                webinar_words = set(webinar.title.lower().split())
                rec_words = set(rec['topic'].lower().split())
                word_overlap = len(webinar_words & rec_words) / max(len(webinar_words), 1)
                score = (title_score * 0.7) + (word_overlap * 0.3)
                
                if score > best_score and score > threshold:
                    best_score = score
                    best_match = rec.copy()
                    best_match['score'] = round(score * 100)
                    best_match['word_overlap'] = round(word_overlap * 100)
            
            # Print + verify URLs
            if best_match:
                matched_count += 1
                if best_match['score'] >= 60:
                    strong_matches += 1
                    emoji = '🔥'
                else:
                    emoji = '✅'
                
                # Verify if share/play URLs match same recording
                url_match, url_detail = self._verify_same_recording(webinar.zoom_url, best_match['play_url'])
                url_status = "✅ SAME" if url_match else "⚠️  DIFF"
                
                self.stdout.write(f"{emoji} {matched_count:2d}. [{best_match['score']}%" 
                                 f"] {webinar.webinar_id} {url_status}")
                self.stdout.write(f"   📺 {webinar.title[:50]}...")
                self.stdout.write(f"   ⏱️  {best_match['duration']}m | {best_match['file_size_mb']}MB")
                
                # URL comparison
                local_short = webinar.zoom_url[:65] + "..." if len(webinar.zoom_url) > 65 else webinar.zoom_url
                zoom_short = best_match['play_url'][:65] + "..." if len(best_match['play_url']) > 65 else best_match['play_url']
                self.stdout.write(f"   🏠 SHARE: {local_short}")
                self.stdout.write(f"   ☁️  PLAY:  {zoom_short}")
                self.stdout.write(f"   🔍 Match:  {url_detail}")
                
                # UPDATE DATABASE
                if do_update:
                    try:
                        # Store play_url (direct playable) + duration
                        webinar.zoom_play_url = best_match['play_url']  # Add this field to model
                        webinar.zoom_duration = best_match['duration']
                        webinar.zoom_match_score = best_match['score']
                        webinar.save(update_fields=['zoom_play_url', 'zoom_duration', 'zoom_match_score'])
                        updated_count += 1
                        self.stdout.write(f"   💾 UPDATED DB!")
                    except Exception as e:
                        self.stdout.write(f"   ❌ DB UPDATE FAILED: {e}")
                
                self.stdout.write('')
            else:
                self.stdout.write(f"❌ {webinar.webinar_id} - {webinar.title[:50]}...")
        
        # Final stats
        self.stdout.write(f'\n📊 FINAL RESULTS:')
        self.stdout.write(f"   🔥 Strong matches (60%+): {strong_matches}")
        self.stdout.write(f"   ✅ Total matches:        {matched_count}/{len(webinars)}")
        self.stdout.write(f"   💾 DB updated:          {updated_count}")
        self.stdout.write(f"   🔍 Searched:             {len(recordings)} recordings")

    def _verify_same_recording(self, share_url, play_url):
        """✅ Verify share/play URLs point to same recording"""
        try:
            # Extract tokens from URLs
            share_match = re.search(r'/rec/share/([a-zA-Z0-9_-]+)', share_url)
            play_match = re.search(r'/rec/play/([a-zA-Z0-9_-]+)', play_url)
            
            if share_match and play_match:
                share_token = share_match.group(1).split('.')[0][:11]
                play_token = play_match.group(1).split('.')[0][:11]
                match = share_token == play_token
                return match, f"{share_token} == {play_token}"
        except:
            pass
        return False, "Could not verify"

