from django.core.management.base import BaseCommand
from django.utils import timezone
from datetime import timedelta
from apps.webinars.models import Webinar


class Command(BaseCommand):
    help = 'Complete all scheduled live webinars that are older than 24 hours'

    def add_arguments(self, parser):
        parser.add_argument(
            '--hours',
            type=int,
            default=24,
            help='Number of hours after webinar end to mark as completed (default: 24)'
        )
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Show what would be done without making changes'
        )

    def handle(self, *args, **options):
        hours = options['hours']
        dry_run = options['dry_run']

        self.stdout.write(self.style.NOTICE(
            f'🔄 Finding scheduled live webinars older than {hours} hours...\n'
        ))

        # Find webinars that should be completed
        now = timezone.now()
        deadline = now - timedelta(hours=hours)

        webinars = Webinar.objects.filter(
            webinar_type='live',
            status__in=['scheduled', 'live']  # Check both scheduled and live webinars
        ).select_related('speaker')

        completed_count = 0
        failed_count = 0
        skipped_count = 0

        for webinar in webinars:
            try:
                # Check if webinar has scheduled_date and duration
                if not webinar.scheduled_date:
                    self.stdout.write(
                        self.style.WARNING(
                            f'⏭️  {webinar.webinar_id}: No scheduled_date, skipping'
                        )
                    )
                    skipped_count += 1
                    continue

                if not webinar.duration:
                    self.stdout.write(
                        self.style.WARNING(
                            f'⏭️  {webinar.webinar_id}: No duration, skipping'
                        )
                    )
                    skipped_count += 1
                    continue

                # Calculate when webinar ended
                scheduled_end = webinar.scheduled_date + timedelta(minutes=webinar.duration)
                completion_deadline = scheduled_end + timedelta(hours=hours)

                # Check if it should be completed
                if now >= completion_deadline:
                    self.stdout.write(
                        self.style.SUCCESS(
                            f'✅ {webinar.webinar_id}: {webinar.title[:50]}'
                        )
                    )
                    self.stdout.write(f'   Ended: {scheduled_end}')
                    self.stdout.write(f'   Age: {now - scheduled_end}')

                    if not dry_run:
                        webinar.status = 'completed'
                        webinar.save(update_fields=['status', 'updated_at'])
                        self.stdout.write(
                            self.style.SUCCESS('   ✔ Marked as completed')
                        )
                    else:
                        self.stdout.write('   (dry-run: not saved)')

                    completed_count += 1
                else:
                    remaining = completion_deadline - now
                    self.stdout.write(
                        self.style.NOTICE(
                            f'⏳ {webinar.webinar_id}: {remaining.total_seconds() / 3600:.1f}h remaining'
                        )
                    )

            except Exception as e:
                self.stdout.write(
                    self.style.ERROR(f'❌ {webinar.webinar_id}: {e}')
                )
                failed_count += 1

        # Summary
        self.stdout.write('\n' + '='*60)
        self.stdout.write(self.style.SUCCESS(f'✅ Completed: {completed_count}'))
        self.stdout.write(self.style.NOTICE(f'⏳ Skipped (not ready): {skipped_count}'))
        if failed_count > 0:
            self.stdout.write(self.style.ERROR(f'❌ Errors: {failed_count}'))
        if dry_run:
            self.stdout.write(self.style.WARNING('(DRY RUN - No changes made)'))
        self.stdout.write('='*60 + '\n')
