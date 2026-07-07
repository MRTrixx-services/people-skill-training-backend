from django.core.management.base import BaseCommand
from apps.webinars.tasks import auto_manage_live_webinars


class Command(BaseCommand):
    help = 'Manually trigger auto-management of live webinars (scheduled → completed only)'

    def handle(self, *args, **options):
        self.stdout.write(self.style.NOTICE(
            '🔄 Starting webinar auto-management...\n'
        ))

        result = auto_manage_live_webinars()

        if not result or 'error' in result:
            self.stdout.write(
                self.style.ERROR(f"❌ Failed to run task: {result}")
            )
            return

        self.stdout.write('📊 RESULTS:')
        self.stdout.write(f'  🔍 Checked: {result.get("checked", 0)}')

        self.stdout.write(
            self.style.SUCCESS(
                f'  ⏱️ Forced Completed (24h): {result.get("forced_completed", 0)}'
            )
        )

        self.stdout.write(
            self.style.SUCCESS(
                f'  ✅ Zoom Completed: {result.get("zoom_completed", 0)}'
            )
        )

        self.stdout.write(
            self.style.SUCCESS(
                f'  🎬 Recordings Found: {result.get("recordings_found", 0)}'
            )
        )

        self.stdout.write(
            self.style.SUCCESS(
                f'  📹 Recorded Webinars Created: {result.get("recorded_created", 0)}'
            )
        )

        if result.get('errors', 0) > 0:
            self.stdout.write(
                self.style.ERROR(
                    f'  ⚠️ Errors: {result["errors"]}'
                )
            )

        self.stdout.write(
            self.style.SUCCESS('\n✅ Webinar auto-management completed successfully.\n')
        )
