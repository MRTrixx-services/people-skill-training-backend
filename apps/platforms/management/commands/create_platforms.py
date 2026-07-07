from django.core.management.base import BaseCommand
from apps.platforms.models import Platform
from django.utils import timezone


class Command(BaseCommand):
    help = 'Create initial platforms for multi-tenant setup with invoice prefixes'

    def handle(self, *args, **kwargs):
        platforms_data = [
            {
                'platform_id': 'peopleskilltraining',
                'name': 'People Skill Training',
                'domain': 'www.peopleskilltraining.com',
                'description': 'Professional skills training platform',
                'support_email': 'support@peopleskilltraining.com',
                'contact_phone': '+1 (555) 123-4567',
                'invoice_prefix': 'PSINV',  # ✅ Added
                'is_default': True,
                'primary_color': '#3B82F6',
                'secondary_color': '#8B5CF6',
                'accent_color': '#10B981',
                'allowed_origins': [
                    'http://localhost:3000',
                    'http://localhost:4028',
                    'https://www.peopleskilltraining.com',
                ],
                'features': {
                    'webinars': True,
                    'certifications': True,
                    'analytics': True,
                    'live_streaming': True,
                },
                'settings': {
                    'timezone': 'America/New_York',
                    'currency': 'USD',
                    'language': 'en',
                }
            },
            {
                'platform_id': 'compliancetrained',
                'name': 'Compliance Trained',
                'domain': 'compliancetrained.com',
                'description': 'Compliance and regulatory training platform',
                'support_email': 'support@compliancetrained.com',
                'contact_phone': '+1 (555) 234-5678',
                'invoice_prefix': 'CTINV',  # ✅ Added
                'is_default': False,
                'primary_color': '#DC2626',
                'secondary_color': '#F59E0B',
                'accent_color': '#059669',
                'allowed_origins': [
                    'http://localhost:3000',
                    'https://compliancetrained.com',
                ],
                'features': {
                    'webinars': True,
                    'certifications': True,
                    'compliance_tracking': True,
                    'audit_logs': True,
                },
                'settings': {
                    'timezone': 'America/New_York',
                    'currency': 'USD',
                    'language': 'en',
                }
            },
            {
                'platform_id': 'workforceskilled',
                'name': 'Workforce Skilled',
                'domain': 'workforceskilled.com',
                'description': 'Workforce development and skills training',
                'support_email': 'support@workforceskilled.com',
                'contact_phone': '+1 (555) 345-6789',
                'invoice_prefix': 'WSINV',  # ✅ Added
                'is_default': False,
                'primary_color': '#7C3AED',
                'secondary_color': '#EC4899',
                'accent_color': '#14B8A6',
                'allowed_origins': [
                    'http://localhost:3000',
                    'https://workforceskilled.com',
                ],
                'features': {
                    'webinars': True,
                    'skills_assessment': True,
                    'career_paths': True,
                    'mentorship': True,
                },
                'settings': {
                    'timezone': 'America/New_York',
                    'currency': 'USD',
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
                        f'   Invoice Prefix: {platform.invoice_prefix}'  # ✅ Added
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
                        f'   Invoice Prefix: {platform.invoice_prefix}'  # ✅ Added
                    )
                )

        self.stdout.write('\n' + '='*60)
        self.stdout.write(
            self.style.SUCCESS(
                f'✅ Summary: {created_count} created, {updated_count} updated'
            )
        )
        self.stdout.write('='*60 + '\n')
        
        # ✅ Display all API keys and invoice prefixes
        self.stdout.write(self.style.SUCCESS('📋 Platform Configuration:\n'))
        for platform in Platform.objects.filter(is_active=True).order_by('name'):
            self.stdout.write(self.style.SUCCESS(f'{platform.name}:'))
            self.stdout.write(f'  API Key:        {platform.api_key}')
            self.stdout.write(f'  Domain:         {platform.domain}')
            self.stdout.write(f'  Invoice Prefix: {platform.invoice_prefix}')  # ✅ Added
            self.stdout.write(f'  Support Email:  {platform.support_email}')
            self.stdout.write('')
        
        # ✅ Show example invoice numbers
        self.stdout.write(self.style.SUCCESS('📄 Example Invoice Numbers:\n'))
        for platform in Platform.objects.filter(is_active=True).order_by('name'):
            from django.utils import timezone
            now = timezone.now()
            example_invoice = f'{platform.invoice_prefix}-{now.year}{now.month:02d}-0001'
            self.stdout.write(f'  {platform.name}: {example_invoice}')
        self.stdout.write('')
