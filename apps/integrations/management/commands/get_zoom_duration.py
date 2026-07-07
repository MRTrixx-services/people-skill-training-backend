# FINAL PERFECT CODE - Extract meeting_id from YOUR zoom_url → Get duration
# apps/integrations/management/commands/get_zoom_duration.py

from django.core.management.base import BaseCommand
from apps.webinars.models import Webinar
from apps.integrations.models import ZoomCredentials
import requests
import base64
import re
from django.utils import timezone
from django.db import transaction

class Command(BaseCommand):
    help = 'Extract meeting ID from zoom_url → Get duration DIRECTLY (NO title matching)'

    def add_arguments(self, parser):
        parser.add_argument('--limit', type=int, default=100, help='Limit webinars')
        parser.add_argument('--update-db', action='store_true', help='Update zoom_duration in DB')
        parser.add_argument('--dry-run', action='store_true', help='Show what WOULD be updated')

    def handle(self, *args, **options):
        limit = options['limit']
        update_db = options['update_db']
        dry_run = options['dry_run']
        
        if update_db and dry_run:
            self.stdout.write(self.style.WARNING('⚠️ DRY RUN - No DB updates'))
        
        self.stdout.write('🎯 Extracting durations from YOUR zoom_urls...')
        self.stdout.write('=' * 80)
        
        # Get webinars with zoom_url containing /rec/
        webinars = Webinar.objects.filter(
            webinar_type='recorded',
            zoom_url__isnull=False,
            zoom_url__icontains='/rec/'
        )[:limit]
        
        self.stdout.write(f'📊 Found {webinars.count()} webinars with zoom_url')
        
        success_count = 0
        fail_count = 0
        updated_count = 0
        
        credentials = ZoomCredentials.objects.filter(is_active=True).first()
        if not credentials:
            self.stdout.write(self.style.ERROR('❌ No Zoom credentials'))
            return
            
        token = self._get_zoom_token(credentials)
        if not token:
            self.stdout.write(self.style.ERROR('❌ No Zoom token'))
            return
        
        self.stdout.write(f'✅ Zoom API ready - Processing {len(webinars)} URLs...\n')
        
        for webinar in webinars:
            duration = self._get_duration_from_zoom_url(webinar.zoom_url, token)
            
            if duration:
                success_count += 1
                status = self.style.SUCCESS(f'✅ {webinar.webinar_id}')
                self.stdout.write(f'{status}: {duration}m')
                self.stdout.write(f'   📺 {webinar.title[:60]}...')
                self.stdout.write(f'   🔗 {webinar.zoom_url}...')
                
                if update_db and not dry_run:
                    try:
                        webinar.zoom_duration = duration
                        webinar.save(update_fields=['zoom_duration'])
                        updated_count += 1
                        self.stdout.write(f'   💾 DB UPDATED!')
                    except Exception as e:
                        self.stdout.write(f'   ❌ DB ERROR: {e}')
            else:
                fail_count += 1
                status = self.style.ERROR(f'❌ {webinar.webinar_id}')
                self.stdout.write(f'{status}: No duration')
                self.stdout.write(f'   🔗 {webinar.zoom_url}...')
            
            self.stdout.write('')
        
        # Final summary
        self.stdout.write('=' * 80)
        self.stdout.write(f'📊 SUMMARY:')
        self.stdout.write(f'   ✅ Success:     {success_count}/{len(webinars)}')
        self.stdout.write(f'   ❌ Failed:      {fail_count}')
        self.stdout.write(f'   💾 DB Updated: {updated_count}')

    def _get_duration_from_zoom_url(self, zoom_url, token):
        """🎯 1. Extract meeting_id → 2. API call → 3. Return duration"""
        meeting_id = self._extract_meeting_id(zoom_url)
        if not meeting_id:
            return None
        
        headers = {'Authorization': f'Bearer {token}'}
        
        # 1. Try recordings endpoint first
        url = f'https://api.zoom.us/v2/meetings/{meeting_id}/recordings'
        try:
            resp = requests.get(url, headers=headers, timeout=15)
            if resp.status_code == 200:
                data = resp.json()
                meetings = data.get('meetings', [])
                if meetings:
                    return meetings[0].get('duration', 0)
        except:
            pass
        
        # 2. Fallback: meeting details
        url = f'https://api.zoom.us/v2/meetings/{meeting_id}'
        try:
            resp = requests.get(url, headers=headers, timeout=15)
            if resp.status_code == 200:
                return resp.json().get('duration', 0)
        except:
            pass
        
        return None

    def _extract_meeting_id(self, zoom_url):
        """🔍 Extract meeting ID from ANY Zoom URL format"""
        # /rec/play/henSkr4_aFFotwd6a... → "henSkr4_aFFotwd6a"
        play_match = re.search(r'/rec/play/([a-zA-Z0-9_-]{10,})(\.[a-zA-Z0-9_-]+)?', zoom_url)
        if play_match:
            return play_match.group(1)
        
        # /rec/share/9KGtcAH4-yK... → "9KGtcAH4-yK"
        share_match = re.search(r'/rec/share/([a-zA-Z0-9_-]{10,})(\.[a-zA-Z0-9_-]+)?', zoom_url)
        if share_match:
            return share_match.group(1)
        
        # Legacy formats
        legacy_match = re.search(r'/j/(\d+)', zoom_url)
        if legacy_match:
            return legacy_match.group(1)
        
        return None

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
