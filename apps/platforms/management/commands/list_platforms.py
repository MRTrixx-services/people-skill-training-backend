from django.core.management.base import BaseCommand
from apps.platforms.models import Platform
from django.utils import timezone


class Command(BaseCommand):
    help = 'List all platforms and their email configuration status'

    def handle(self, *args, **options):
        platforms = Platform.objects.all()
        
        if not platforms.exists():
            self.stdout.write(self.style.WARNING('No platforms found'))
            return
        
        self.stdout.write('\n' + '='*80)
        self.stdout.write('📋 PLATFORMS OVERVIEW')
        self.stdout.write('='*80 + '\n')
        
        for platform in platforms:
            status = '✅ Active' if platform.is_active else '❌ Inactive'
            email_status = '✅ Configured' if platform.has_email_config else '❌ Not Configured'
            
            self.stdout.write(f'Platform: {platform.name} ({platform.platform_id})')
            self.stdout.write(f'  Status: {status}')
            self.stdout.write(f'  Email: {email_status}')
            self.stdout.write(f'  Support: {platform.support_email or "Not set"}')
            
            if platform.has_email_config:
                config = platform.get_email_config_summary()
                self.stdout.write(f'  SMTP: {config["smtp_host"]}:{config["smtp_port"]}')
                self.stdout.write(f'  Provider: {config["provider"]}')
            
            self.stdout.write('')  # blank line
        
        self.stdout.write('='*80 + '\n')
