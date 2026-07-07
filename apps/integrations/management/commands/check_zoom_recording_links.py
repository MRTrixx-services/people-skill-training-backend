# apps/integrations/management/commands/check_zoom_recording_links.py
from django.core.management.base import BaseCommand, CommandError
from django.db.models import Q
from apps.webinars.models import Webinar
from apps.integrations.services import ZoomWebinarService, ZoomAPIService
from tabulate import tabulate
import logging
import json

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = 'Checks if local Webinar zoom_url (recorded links) are still available on Zoom cloud.'

    def add_arguments(self, parser):
        parser.add_argument(
            '--status',
            type=str,
            choices=['active', 'inactive', 'all'],
            default='all',
            help='Filter results by recording status (Active/Inactive).'
        )
        parser.add_argument(
            '--update',
            action='store_true',
            help='If a link is inactive, clear the zoom_url and set has_recording=False on the Webinar object.'
        )
        parser.add_argument('--webinar-id', type=str, help='Check a single specific webinar ID.')

    def handle(self, *args, **options):
        self.stdout.write(self.style.SUCCESS('\n' + '='*100))
        self.stdout.write(self.style.SUCCESS('🎬 ZOOM RECORDING LINK VERIFICATION'))
        self.stdout.write(self.style.SUCCESS('='*100 + '\n'))

        try:
            zoom_api = ZoomAPIService()
            # Test connection once
            zoom_api.test_connection()
            self.stdout.write(self.style.SUCCESS('✅ Zoom API Connection Verified\n'))
        except Exception as e:
            raise CommandError(f'❌ Failed to initialize Zoom API: {str(e)}')

        # 1. Filter Webinars to Check
        # Target: Recorded Webinars OR Completed Live Webinars that have a zoom_url set.
        webinars_query = Webinar.objects.filter(
            Q(webinar_type='recorded') | Q(webinar_type='live', status='completed')
        ).exclude(zoom_url__isnull=True).exclude(zoom_url='')

        if options['webinar_id']:
            webinars_query = webinars_query.filter(webinar_id=options['webinar_id'])

        if not webinars_query.exists():
            self.stdout.write(self.style.WARNING('❌ No recorded or completed live webinars with a zoom_url found.'))
            return

        self.stdout.write(f"Checking {webinars_query.count()} webinars...")
        
        results = {
            'active': [],
            'inactive': [],
            'errors': [],
            'updated': 0
        }
        
        # 2. Iterate and Verify
        for i, webinar in enumerate(webinars_query, 1):
            self.stdout.write(f"\n[{i}/{webinars_query.count()}] {webinar.webinar_id}: {webinar.title[:50]}...")
            self.stdout.write(f"   URL: {webinar.zoom_url}...")

            try:
                # Use the new API method to verify the URL existence
                is_active = zoom_api.check_recording_existence_by_url(webinar.zoom_url)

                result_data = {
                    'webinar_id': webinar.webinar_id,
                    'title': webinar.title[:50],
                    'type': webinar.get_webinar_type_display(),
                    'status': webinar.get_status_display(),
                    'zoom_url': webinar.zoom_url,
                    'is_active': is_active
                }

                if is_active:
                    results['active'].append(result_data)
                    self.stdout.write(self.style.SUCCESS('   ✅ STATUS: ACTIVE on Zoom Cloud.'))
                else:
                    results['inactive'].append(result_data)
                    self.stdout.write(self.style.ERROR('   ❌ STATUS: INACTIVE/NOT FOUND on Zoom Cloud.'))
                    
                    # 3. Apply Update Logic if specified
                    if options['update']:
                        self.stdout.write(self.style.WARNING('   ⚠️ Clearing local URL and recording flag...'))
                        webinar.zoom_url = ''
                        webinar.has_recording = False
                        webinar.save(update_fields=['zoom_url', 'has_recording', 'updated_at'])
                        results['updated'] += 1
                        
            except Exception as e:
                logger.error(f"Error checking {webinar.webinar_id}: {str(e)}")
                self.stdout.write(self.style.ERROR(f"   ❌ ERROR checking link: {str(e)}"))
                results['errors'].append({'webinar_id': webinar.webinar_id, 'title': webinar.title[:50], 'error': str(e)})

        # 4. Display Summary and Tables
        self._display_summary(results, webinars_query.count())
        self._display_tables(results, options)

    def _display_summary(self, results, total_checked):
        self.stdout.write('\n' + '='*100)
        self.stdout.write(self.style.SUCCESS('📊 VERIFICATION SUMMARY:'))
        self.stdout.write('='*100)
        
        active_count = len(results['active'])
        inactive_count = len(results['inactive'])
        error_count = len(results['errors'])
        updated_count = results['updated']
        
        self.stdout.write(f"\nTotal Webinars Checked: {total_checked}\n")
        self.stdout.write(self.style.SUCCESS(f"✅ ACTIVE Recordings Found: {active_count}"))
        self.stdout.write(self.style.ERROR(f"❌ INACTIVE/Not Found: {inactive_count}"))
        if updated_count > 0:
            self.stdout.write(self.style.WARNING(f"🔄 Webinars Updated (Links Cleared): {updated_count}"))
        if error_count > 0:
            self.stdout.write(self.style.ERROR(f"❌ Errors Encountered: {error_count}"))

    def _display_tables(self, results, options):
        # Determine which tables to show based on --status option
        status_filter = options['status']
        
        # Display Active Recordings
        if results['active'] and (status_filter == 'all' or status_filter == 'active'):
            self.stdout.write(self.style.SUCCESS(f"\n\n✅ ACTIVE RECORDINGS ({len(results['active'])}):\n"))
            table_data = [
                [item['webinar_id'], item['title'][:40], item['type'], item['zoom_url']]
                for item in results['active']
            ]
            headers = ['Webinar ID', 'Title', 'Type', 'Verified Zoom URL Snippet']
            self.stdout.write(tabulate(table_data, headers=headers, tablefmt='grid'))
            
        # Display Inactive Recordings
        if results['inactive'] and (status_filter == 'all' or status_filter == 'inactive'):
            self.stdout.write(self.style.ERROR(f"\n\n❌ INACTIVE RECORDINGS ({len(results['inactive'])}):\n"))
            table_data = [
                [item['webinar_id'], item['title'][:40], item['type'], item['zoom_url']]
                for item in results['inactive']
            ]
            headers = ['Webinar ID', 'Title', 'Type', 'Inactive Zoom URL Snippet']
            self.stdout.write(tabulate(table_data, headers=headers, tablefmt='grid'))
        
        # Display Errors
        if results['errors']:
            self.stdout.write(self.style.ERROR(f"\n\n❌ ERRORS ENCOUNTERED ({len(results['errors'])}):\n"))
            table_data = [
                [item['webinar_id'], item['title'][:35], item['error'][:50]]
                for item in results['errors']
            ]
            headers = ['Webinar ID', 'Title', 'Error Snippet']
            self.stdout.write(tabulate(table_data, headers=headers, tablefmt='grid'))