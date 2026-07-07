from django.core.management.base import BaseCommand
from apps.platforms.models import Platform
from django.utils import timezone


class Command(BaseCommand):
    help = 'Create initial platform for DailyRespond with invoice prefix'

    def handle(self, *args, **kwargs):
        platforms_data = [
            {
                'platform_id': 'dailyrespond',
                'name': 'Daily Respond',
                'domain': 'dailyrespond.com',
                'description': 'Daily customer response and engagement platform',
                'support_email': 'support@dailyrespond.com',
                'contact_phone': '+1 (555) 456-7890',
                'invoice_prefix': 'DRINV',
                'is_default': True,
                'primary_color': '#1E40AF',
                'secondary_color': '#7C3AED',
                'accent_color': '#059669',
                'allowed_origins': [
                    'http://localhost:3000',
                    'http://localhost:4028',
                    'https://dailyrespond.com',
                    'https://www.dailyrespond.com',
                ],
                'features': {
                    'customer_engagement': True,
                    'analytics': True,
                    'automation': True,
                    'reporting': True,
                },
                'settings': {
                    'timezone': 'Asia/Kolkata',
                    'currency': 'INR',
                    'language': 'en',
                }
            },
        ]

        created_count = 0
        updated_count = 0

        for platform_data in platforms_data:
            platform_id = platform_data.pop('platform_id')
            
            platform, created = Platform.objects.update_or_create(
                platform_id=platform_id,
                defaults=platform_data
            )
            
            if created:
                created_count += 1
                self.stdout.write(
                    self.style.SUCCESS(
                        f'✅ Created platform: {platform.name}'
                    )
                )
                self.stdout.write(
                    self.style.WARNING(
                        f'   API Key: {platform.api_key}'
                    )
                )
                self.stdout.write(
                    self.style.WARNING(
                        f'   Domain: {platform.domain}'
                    )
                )
                self.stdout.write(
                    self.style.WARNING(
                        f'   Invoice Prefix: {platform.invoice_prefix}'
                    )
                )
            else:
                updated_count += 1
                self.stdout.write(
                    self.style.WARNING(
                        f'⚠️  Updated platform: {platform.name}'
                    )
                )
                self.stdout.write(
                    self.style.WARNING(
                        f'   API Key: {platform.api_key} (unchanged)'
                    )
                )
                self.stdout.write(
                    self.style.WARNING(
                        f'   Invoice Prefix: {platform.invoice_prefix}'
                    )
                )

        self.stdout.write('\n' + '='*60)
        self.stdout.write(
            self.style.SUCCESS(
                f'✅ Summary: {created_count} created, {updated_count} updated'
            )
        )
        self.stdout.write('='*60 + '\n')
        
        # Display all API keys and invoice prefixes
        self.stdout.write(self.style.SUCCESS('📋 Platform Configuration:\n'))
        for platform in Platform.objects.filter(is_active=True).order_by('name'):
            self.stdout.write(self.style.SUCCESS(f'{platform.name}:'))
            self.stdout.write(f'  API Key:        {platform.api_key}')
            self.stdout.write(f'  Domain:         {platform.domain}')
            self.stdout.write(f'  Invoice Prefix: {platform.invoice_prefix}')
            self.stdout.write(f'  Support Email:  {platform.support_email}')
            self.stdout.write('')
        
        # Show example invoice numbers
        self.stdout.write(self.style.SUCCESS('📄 Example Invoice Numbers:\n'))
        for platform in Platform.objects.filter(is_active=True).order_by('name'):
            now = timezone.now()
            example_invoice = f'{platform.invoice_prefix}-{now.year}{now.month:02d}-0001'
            self.stdout.write(f'  {platform.name}: {example_invoice}')
        self.stdout.write('')
