# apps/webinars/management/commands/check_zoom_timezone_mismatches.py
from django.core.management.base import BaseCommand
from django.utils import timezone
from apps.webinars.models import Webinar
from apps.integrations.models import ZoomMeeting
import pytz
from datetime import datetime
from tabulate import tabulate


class Command(BaseCommand):
    help = 'Check timezone mismatches between Webinars and Zoom Meetings (focus on Eastern Time)'

    def add_arguments(self, parser):
        parser.add_argument(
            '--fix',
            action='store_true',
            help='Automatically fix timezone mismatches to Eastern Time',
        )
        parser.add_argument(
            '--target-timezone',
            type=str,
            default='America/New_York',
            help='Target timezone to check/fix (default: America/New_York)',
        )
        parser.add_argument(
            '--show-matched',
            action='store_true',
            help='Also show webinars that are properly matched',
        )
        parser.add_argument(
            '--webinar-id',
            type=str,
            help='Check specific webinar ID only',
        )
        parser.add_argument(
            '--zoom-meeting-id',  # ← ADDED
            type=str,
            help='Check specific Zoom meeting ID only',
        )
        parser.add_argument(
            '--only-eastern-mismatches',
            action='store_true',
            help='Only show webinars that are NOT in Eastern Time',
        )

    def handle(self, *args, **options):
        target_tz = options['target_timezone']
        
        self.stdout.write(self.style.SUCCESS('\n' + '='*100))
        self.stdout.write(self.style.SUCCESS(f'🔍 ZOOM TIMEZONE MISMATCH ANALYSIS (Target: {target_tz})'))
        self.stdout.write(self.style.SUCCESS('='*100 + '\n'))
        
        # Query webinars with ZoomMeeting relationships
        webinars_query = Webinar.objects.filter(
            webinar_type='live',
            zoom_meetings__isnull=False
        ).select_related(
            'speaker', 'category'
        ).prefetch_related('zoom_meetings').distinct()
        
        # ← ADDED: Filter by Zoom meeting ID
        if options['zoom_meeting_id']:
            webinars_query = webinars_query.filter(
                zoom_meetings__zoom_meeting_id=options['zoom_meeting_id']
            )
            self.stdout.write(f"Filtering by Zoom Meeting ID: {options['zoom_meeting_id']}\n")
        
        if options['webinar_id']:
            webinars_query = webinars_query.filter(webinar_id=options['webinar_id'])
            self.stdout.write(f"Filtering by Webinar ID: {options['webinar_id']}\n")
        
        if not webinars_query.exists():
            self.stdout.write(self.style.WARNING('❌ No live webinars with Zoom integration found.'))
            return
        
        # Analysis results - ENHANCED categories
        not_in_eastern = []
        db_not_eastern = []
        zoom_not_eastern = []
        time_mismatches = []
        matched_correctly = []
        
        total_checked = 0
        
        for webinar in webinars_query:
            total_checked += 1
            
            # ← MODIFIED: If filtering by zoom_meeting_id, get that specific meeting
            if options['zoom_meeting_id']:
                zoom_meeting = webinar.zoom_meetings.filter(
                    zoom_meeting_id=options['zoom_meeting_id']
                ).first()
            else:
                zoom_meeting = webinar.zoom_meetings.first()
            
            if not zoom_meeting:
                continue
            
            # Extract timezone info
            webinar_tz = webinar.timezone or 'UTC'
            zoom_tz = zoom_meeting.timezone or 'UTC'
            
            # Extract time info
            webinar_time = webinar.scheduled_date
            zoom_time = zoom_meeting.start_time
            
            # **KEY CHECK**: Is each timezone Eastern Time?
            db_is_eastern = (webinar_tz == target_tz)
            zoom_is_eastern = (zoom_tz == target_tz)
            
            # Check time mismatch (convert both to UTC for comparison)
            has_time_mismatch = False
            time_diff_hours = 0
            time_diff_description = "Exact match"
            
            if webinar_time and zoom_time:
                # Make both timezone-aware
                if webinar_time.tzinfo is None:
                    webinar_tz_obj = pytz.timezone(webinar_tz)
                    webinar_time_aware = webinar_tz_obj.localize(webinar_time)
                else:
                    webinar_time_aware = webinar_time
                
                if zoom_time.tzinfo is None:
                    zoom_tz_obj = pytz.timezone(zoom_tz)
                    zoom_time_aware = zoom_tz_obj.localize(zoom_time)
                else:
                    zoom_time_aware = zoom_time
                
                # Convert both to UTC
                webinar_utc = webinar_time_aware.astimezone(pytz.UTC)
                zoom_utc = zoom_time_aware.astimezone(pytz.UTC)
                
                # Calculate difference
                time_delta_seconds = abs((webinar_utc - zoom_utc).total_seconds())
                time_diff_hours = round(time_delta_seconds / 3600, 2)
                
                # Consider it a mismatch if > 1 minute difference
                has_time_mismatch = time_delta_seconds > 60
                
                if has_time_mismatch:
                    if time_delta_seconds < 3600:
                        time_diff_description = f"{int(time_delta_seconds / 60)} minutes off"
                    else:
                        hours = int(time_delta_seconds / 3600)
                        minutes = int((time_delta_seconds % 3600) / 60)
                        time_diff_description = f"{hours}h {minutes}m off"
            
            # Get GMT offsets
            webinar_gmt = self.get_gmt_offset(webinar_tz, webinar_time)
            zoom_gmt = self.get_gmt_offset(zoom_tz, zoom_time)
            
            # Format display times
            webinar_time_display = webinar_time.strftime('%Y-%m-%d %I:%M %p') if webinar_time else 'Not set'
            zoom_time_display = zoom_time.strftime('%Y-%m-%d %I:%M %p') if zoom_time else 'Not set'
            
            # Build mismatch data
            mismatch_data = {
                'webinar_id': webinar.webinar_id,
                'title': webinar.title[:50] + '...' if len(webinar.title) > 50 else webinar.title,
                'zoom_meeting_id': zoom_meeting.zoom_meeting_id,
                'status': zoom_meeting.status,
                
                # Timezone info
                'webinar_tz': webinar_tz,
                'zoom_tz': zoom_tz,
                'webinar_gmt': webinar_gmt,
                'zoom_gmt': zoom_gmt,
                'db_is_eastern': db_is_eastern,
                'zoom_is_eastern': zoom_is_eastern,
                
                # Time info
                'webinar_time': webinar_time,
                'zoom_time': zoom_time,
                'webinar_time_display': webinar_time_display,
                'zoom_time_display': zoom_time_display,
                'time_diff_hours': time_diff_hours,
                'time_diff_description': time_diff_description,
                'time_match': not has_time_mismatch,
                
                # Objects for fixing
                'webinar_obj': webinar,
                'zoom_meeting_obj': zoom_meeting,
            }
            
            # **ENHANCED CATEGORIZATION** - Focus on Eastern Time
            if not db_is_eastern and not zoom_is_eastern:
                not_in_eastern.append(mismatch_data)
            elif not db_is_eastern and zoom_is_eastern:
                db_not_eastern.append(mismatch_data)
            elif db_is_eastern and not zoom_is_eastern:
                zoom_not_eastern.append(mismatch_data)
            elif db_is_eastern and zoom_is_eastern:
                if has_time_mismatch:
                    time_mismatches.append(mismatch_data)
                else:
                    matched_correctly.append(mismatch_data)
        
        # Display summary
        self.stdout.write(self.style.SUCCESS('\n📊 SUMMARY:\n'))
        self.stdout.write(f'Total Webinars Checked: {total_checked}')
        self.stdout.write(f'Target Timezone: {target_tz}')
        self.stdout.write('')
        self.stdout.write(self.style.SUCCESS(f'✅ Correctly in {target_tz}: {len(matched_correctly)}'))
        self.stdout.write(self.style.ERROR(f'❌ Neither in {target_tz}: {len(not_in_eastern)}'))
        self.stdout.write(self.style.WARNING(f'⚠️  DB NOT in {target_tz} (Zoom is): {len(db_not_eastern)}'))
        self.stdout.write(self.style.WARNING(f'⚠️  Zoom NOT in {target_tz} (DB is): {len(zoom_not_eastern)}'))
        self.stdout.write(self.style.WARNING(f'⚠️  Both in {target_tz} but Time Mismatch: {len(time_mismatches)}'))
        
        # Show critical mismatches
        if not_in_eastern:
            self.stdout.write(self.style.ERROR(f'\n\n🚨 CRITICAL: Neither DB nor Zoom is in {target_tz}:\n'))
            self.display_mismatch_table(not_in_eastern, target_tz)
        
        if db_not_eastern:
            self.stdout.write(self.style.WARNING(f'\n\n⚠️  Database NOT in {target_tz} (Zoom is correct):\n'))
            self.display_mismatch_table(db_not_eastern, target_tz)
        
        if zoom_not_eastern:
            self.stdout.write(self.style.WARNING(f'\n\n⚠️  Zoom NOT in {target_tz} (Database is correct):\n'))
            self.display_mismatch_table(zoom_not_eastern, target_tz)
        
        if time_mismatches:
            self.stdout.write(self.style.WARNING(f'\n\n⚠️  Both in {target_tz} but Time Mismatch:\n'))
            self.display_mismatch_table(time_mismatches, target_tz)
        
        if options['show_matched'] and matched_correctly:
            self.stdout.write(self.style.SUCCESS(f'\n\n✅ Correctly Matched in {target_tz}:\n'))
            self.display_mismatch_table(matched_correctly, target_tz)
        
        # Collect all mismatches
        all_mismatches = not_in_eastern + db_not_eastern + zoom_not_eastern + time_mismatches
        
        if all_mismatches:
            self.stdout.write(self.style.WARNING(f'\n\n📝 Total Mismatches: {len(all_mismatches)}'))
            
            if options['fix']:
                self.fix_mismatches(all_mismatches, target_tz)
            else:
                self.stdout.write(
                    self.style.NOTICE(
                        f"\n\n💡 To automatically fix ALL mismatches to {target_tz}, run:\n"
                        f"   python manage.py check_zoom_timezone_mismatches --fix --target-timezone={target_tz}\n"
                    )
                )
        else:
            self.stdout.write(
                self.style.SUCCESS(
                    f'\n\n🎉 Excellent! All {total_checked} webinars are in {target_tz} and synchronized!\n'
                )
            )
    
    def display_mismatch_table(self, mismatches, target_tz):
        """Display mismatches in a formatted table"""
        if not mismatches:
            return
        
        table_data = []
        for m in mismatches:
            db_tz_icon = '✅' if m['db_is_eastern'] else '❌'
            zoom_tz_icon = '✅' if m['zoom_is_eastern'] else '❌'
            time_icon = '✅' if m['time_match'] else '❌'
            
            row = [
                m['webinar_id'],
                m['title'][:35],
                f"{m['webinar_tz']}\n({m['webinar_gmt']})",
                db_tz_icon,
                f"{m['zoom_tz']}\n({m['zoom_gmt']})",
                zoom_tz_icon,
                m['webinar_time_display'],
                m['zoom_time_display'],
                m['time_diff_description'],
                time_icon,
                m['zoom_meeting_id'][:12],
            ]
            table_data.append(row)
        
        headers = [
            'Webinar ID',
            'Title',
            'DB Timezone',
            f'{target_tz}?',
            'Zoom TZ',
            f'{target_tz}?',
            'DB Time',
            'Zoom Time',
            'Time Diff',
            'Time✓',
            'Zoom ID'
        ]
        
        self.stdout.write(tabulate(table_data, headers=headers, tablefmt='grid'))
    
    def get_gmt_offset(self, timezone_str, dt=None):
        """Get GMT offset for a timezone"""
        try:
            tz = pytz.timezone(timezone_str)
            if dt is None or dt.tzinfo is None:
                dt = timezone.now()
            
            if dt.tzinfo is None:
                dt = tz.localize(dt)
            
            offset = tz.utcoffset(dt)
            if offset:
                total_seconds = int(offset.total_seconds())
                hours = total_seconds // 3600
                minutes = (total_seconds % 3600) // 60
                return f"GMT{hours:+03d}:{minutes:02d}"
            return "GMT+00:00"
        except Exception as e:
            return "Unknown"
    
    def fix_mismatches(self, mismatches, target_timezone):
        """Fix all mismatches by updating to target timezone"""
        self.stdout.write(self.style.WARNING(f'\n\n🔧 FIXING {len(mismatches)} MISMATCH(ES) to {target_timezone}...\n'))
        
        from apps.integrations.services import ZoomAPIService
        
        try:
            zoom_api = ZoomAPIService()
        except Exception as e:
            self.stdout.write(self.style.ERROR(f'❌ Failed to initialize Zoom API: {str(e)}'))
            return
        
        fixed_count = 0
        failed_count = 0
        skipped_count = 0
        
        for idx, m in enumerate(mismatches, 1):
            webinar = m['webinar_obj']
            zoom_meeting = m['zoom_meeting_obj']
            
            self.stdout.write(f"\n[{idx}/{len(mismatches)}] {m['webinar_id']} - {m['title'][:40]}")
            self.stdout.write(f"  Zoom Meeting ID: {zoom_meeting.zoom_meeting_id}")
            self.stdout.write(f"  Current: DB={m['webinar_tz']}, Zoom={m['zoom_tz']}")
            
            try:
                # Update webinar timezone in database
                old_tz = webinar.timezone
                webinar.timezone = target_timezone
                webinar.save(update_fields=['timezone'])
                
                self.stdout.write(f"  ✓ Database: {old_tz} → {target_timezone}")
                
                # Convert scheduled time to target timezone
                if webinar.scheduled_date:
                    target_tz = pytz.timezone(target_timezone)
                    
                    if webinar.scheduled_date.tzinfo is None:
                        scheduled_aware = target_tz.localize(webinar.scheduled_date)
                    else:
                        scheduled_aware = webinar.scheduled_date.astimezone(target_tz)
                else:
                    self.stdout.write(self.style.WARNING(f"  ⚠ No scheduled date, skipping Zoom update..."))
                    skipped_count += 1
                    continue
                
                # Update Zoom meeting via API
                updates = {
                    'timezone': target_timezone,
                    'start_time': scheduled_aware,
                }
                
                success = zoom_api.update_meeting(
                    meeting_id=zoom_meeting.zoom_meeting_id,
                    updates=updates
                )
                
                if success:
                    # Update local ZoomMeeting record
                    old_zoom_tz = zoom_meeting.timezone
                    zoom_meeting.timezone = target_timezone
                    zoom_meeting.start_time = scheduled_aware
                    zoom_meeting.save(update_fields=['timezone', 'start_time'])
                    
                    self.stdout.write(
                        self.style.SUCCESS(
                            f"  ✅ Zoom API: {old_zoom_tz} → {target_timezone}"
                        )
                    )
                    self.stdout.write(f"     Meeting time: {scheduled_aware.strftime('%Y-%m-%d %I:%M %p %Z')}")
                    
                    fixed_count += 1
                else:
                    self.stdout.write(self.style.ERROR(f"  ❌ Zoom API update failed"))
                    failed_count += 1
                    
            except Exception as e:
                self.stdout.write(self.style.ERROR(f"  ❌ Error: {str(e)}"))
                failed_count += 1
        
        # Final summary
        self.stdout.write('\n' + '='*100)
        self.stdout.write(self.style.SUCCESS(f'✅ Successfully Fixed to {target_timezone}: {fixed_count}'))
        if failed_count > 0:
            self.stdout.write(self.style.ERROR(f'❌ Failed: {failed_count}'))
        if skipped_count > 0:
            self.stdout.write(self.style.WARNING(f'⚠️  Skipped: {skipped_count}'))
        self.stdout.write('='*100 + '\n')
