from django.core.management.base import BaseCommand
from django.utils import timezone
from datetime import timedelta
from apps.webinars.models import Webinar


class Command(BaseCommand):
    help = 'FORCE: Mark all live webinars as completed if they ended 24+ hours ago (handles missing dates)'

    def add_arguments(self, parser):
        parser.add_argument(
            '--confirm',
            action='store_true',
            help='Confirm the action (required to prevent accidental runs)'
        )
        parser.add_argument(
            '--fallback-days',
            type=int,
            default=1,
            help='If scheduled_date missing, use created_at + N days (default: 1)'
        )

    def handle(self, *args, **options):
        confirm = options['confirm']
        fallback_days = options['fallback_days']

        if not confirm:
            self.stdout.write(self.style.WARNING(
                '⚠️  This will mark ALL scheduled live webinars as completed.\n'
                'Run with --confirm to proceed.\n'
            ))
            return

        self.stdout.write(self.style.NOTICE(
            '🚀 FORCE-COMPLETING all scheduled live webinars (24h+ old)...\n'
            f'Fallback duration: {fallback_days} day(s) for missing scheduled_date\n'
        ))

        now = timezone.now()
        webinars = Webinar.objects.filter(
            webinar_type='live',
            status__in=['scheduled', 'live']  # Check both scheduled and live webinars
        ).select_related('speaker')

        completed_count = 0
        fallback_count = 0
        no_date_count = 0
        error_count = 0

        for webinar in webinars:
            try:
                scheduled_end = None
                fallback_used = False

                # Priority 1: Use scheduled_date + duration
                if webinar.scheduled_date and webinar.duration:
                    scheduled_end = webinar.scheduled_date + timedelta(minutes=webinar.duration)
                
                # Priority 2: Use created_at + fallback_days
                elif webinar.created_at:
                    scheduled_end = webinar.created_at + timedelta(days=fallback_days)
                    fallback_used = True
                else:
                    # No date info available
                    self.stdout.write(
                        self.style.WARNING(
                            f'⏭️  {webinar.webinar_id}: No scheduled_date or created_at, skipping'
                        )
                    )
                    no_date_count += 1
                    continue

                deadline = scheduled_end + timedelta(hours=24)
                age_hours = (now - scheduled_end).total_seconds() / 3600

                if now >= deadline:
                    webinar.status = 'completed'
                    webinar.save(update_fields=['status', 'updated_at'])

                    tag = "🔄" if fallback_used else "✅"
                    fallback_msg = " [fallback]" if fallback_used else ""
                    
                    self.stdout.write(
                        self.style.SUCCESS(
                            f'{tag} {webinar.webinar_id}: {webinar.title[:50]}{fallback_msg} (age: {age_hours:.1f}h)'
                        )
                    )
                    completed_count += 1
                    if fallback_used:
                        fallback_count += 1
                else:
                    hours_left = (deadline - now).total_seconds() / 3600
                    self.stdout.write(
                        self.style.NOTICE(
                            f'⏳ {webinar.webinar_id}: {hours_left:.1f}h remaining'
                        )
                    )

            except Exception as e:
                self.stdout.write(
                    self.style.ERROR(f'❌ {webinar.webinar_id}: {str(e)}')
                )
                error_count += 1

        # Summary
        self.stdout.write('\n' + '='*70)
        self.stdout.write(self.style.SUCCESS(f'✅ Completed and saved: {completed_count}'))
        if fallback_count > 0:
            self.stdout.write(self.style.NOTICE(f'🔄 Used fallback dates: {fallback_count}'))
        if no_date_count > 0:
            self.stdout.write(self.style.WARNING(f'⏭️  No date info available: {no_date_count}'))
        if error_count > 0:
            self.stdout.write(self.style.ERROR(f'❌ Errors: {error_count}'))
        self.stdout.write('='*70 + '\n')
