from django.core.management.base import BaseCommand
from django.db import transaction
from apps.platforms.models import Platform
from apps.webinars.models import Webinar, WebinarPlatformPrice
from decimal import Decimal


class Command(BaseCommand):
    help = 'Setup platform-specific pricing for all webinars'

    # Platform pricing configuration (using platform_id)
    PLATFORM_PRICING = {
        'compliancetrained': {
            'name': 'Compliance Trained',
            'live_single_price': 147,
            'live_multi_price': 390,
            'recorded_single_price': 189,
            'recorded_multi_price': 350,
            'combo_single_price': 310,
            'combo_multi_price': 590,
        },
        'peopleskilltraining': {
            'name': 'People Skill Training',
             'live_single_price': 147,
            'live_multi_price': 390,
            'recorded_single_price': 189,
            'recorded_multi_price': 350,
            'combo_single_price': 310,
            'combo_multi_price': 590,
        },
        'workforceskilled': {
            'name': 'Workforce Skilled',
            'live_single_price': 147,
            'live_multi_price': 390,
            'recorded_single_price': 189,
            'recorded_multi_price': 350,
            'combo_single_price': 310,
            'combo_multi_price': 590,
        },
    }

    def add_arguments(self, parser):
        parser.add_argument(
            '--platform-id',
            type=str,
            help='Specific platform_id to update (e.g., compliancetrained)',
        )
        parser.add_argument(
            '--webinar-id',
            type=str,
            help='Specific webinar ID to update (optional)',
        )
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Show what would be updated without making changes',
        )
        parser.add_argument(
            '--update-existing',
            action='store_true',
            help='Update existing platform prices instead of skipping them',
        )
        parser.add_argument(
            '--clear-all',
            action='store_true',
            help='Clear all existing platform prices before creating new ones',
        )
        parser.add_argument(
            '--clear-platform',
            type=str,
            help='Clear all existing platform prices for specific platform_id',
        )
        parser.add_argument(
        '--delete-all',
        action='store_true',
        help='Delete all existing platform records (WebinarPlatformPrice)',
    )
        parser.add_argument(
            '--delete-platform',
            type=str,
            help='Delete platform records for specific platform_id',
        )
    def handle(self, *args, **options):
        platform_id = options.get('platform_id')
        webinar_id = options.get('webinar_id')
        dry_run = options.get('dry_run')
        update_existing = options.get('update_existing')
        clear_all = options.get('clear_all')

        self.stdout.write(self.style.SUCCESS('Starting platform price setup...'))
        
        if dry_run:
            self.stdout.write(self.style.WARNING('DRY RUN MODE - No changes will be made'))

        # Clear existing prices if requested
        
        if clear_all and not dry_run:
            deleted_count = WebinarPlatformPrice.objects.all().count()
            WebinarPlatformPrice.objects.all().delete()
            self.stdout.write(
                self.style.WARNING(f'🗑️  Cleared {deleted_count} existing platform prices (all platforms)')
            )
        elif options.get('clear_platform') and not dry_run:
            platform_to_clear = options['clear_platform']
            platform = Platform.objects.filter(platform_id=platform_to_clear).first()
            if not platform:
                self.stdout.write(self.style.ERROR(f'Platform not found: {platform_to_clear}'))
                return
            deleted_count = WebinarPlatformPrice.objects.filter(platform=platform).count()
            WebinarPlatformPrice.objects.filter(platform=platform).delete()
            self.stdout.write(
                self.style.WARNING(f'🗑️  Cleared {deleted_count} existing platform prices for platform {platform_to_clear}')
            )
        # Handle deletions
        if options.get('delete_all') and not options.get('dry_run'):
            count_deleted, _ = WebinarPlatformPrice.objects.all().delete()
            self.stdout.write(self.style.WARNING(f'🗑️  Deleted all {count_deleted} platform records'))
            return  # Exit after deletion to prevent further processing

        if options.get('delete_platform') and not options.get('dry_run'):
            platform_id_to_delete = options['delete_platform']
            platform = Platform.objects.filter(platform_id=platform_id_to_delete).first()
            if not platform:
                self.stdout.write(self.style.ERROR(f'Platform not found: {platform_id_to_delete}'))
                return
            count_deleted, _ = WebinarPlatformPrice.objects.filter(platform=platform).delete()
            self.stdout.write(self.style.WARNING(f'🗑️  Deleted {count_deleted} records for platform: {platform_id_to_delete}'))
            return  # Exit after deletion

        # Get platforms to process
        if platform_id:
            platforms = Platform.objects.filter(platform_id=platform_id, is_active=True)
            if not platforms.exists():
                self.stdout.write(self.style.ERROR(f'Platform not found: {platform_id}'))
                return
        else:
            platforms = Platform.objects.filter(is_active=True)

        # Get webinars to process
        if webinar_id:
            webinars = Webinar.objects.filter(webinar_id=webinar_id)
            if not webinars.exists():
                self.stdout.write(self.style.ERROR(f'Webinar not found: {webinar_id}'))
                return
        else:
            webinars = Webinar.objects.exclude(status='cancelled')

        total_webinars = webinars.count()
        total_platforms = platforms.count()
        
        self.stdout.write(f'Processing {total_webinars} webinars across {total_platforms} platforms...\n')

        created_count = 0
        updated_count = 0
        skipped_count = 0
        error_count = 0

        try:
            with transaction.atomic():
                for platform in platforms:
                    platform_config = self.PLATFORM_PRICING.get(platform.platform_id)
                    
                    if not platform_config:
                        self.stdout.write(
                            self.style.WARNING(
                                f'⚠️  No pricing config for platform: {platform.name} ({platform.platform_id})'
                            )
                        )
                        continue

                    self.stdout.write(f'\n📊 Processing platform: {platform.name}')
                    self.stdout.write(f'   Platform ID: {platform.platform_id}')
                    
                    platform_created = 0
                    platform_updated = 0
                    platform_skipped = 0
                    
                    for webinar in webinars:
                        try:
                            # Check if platform price already exists
                            platform_price, created = WebinarPlatformPrice.objects.get_or_create(
                                webinar=webinar,
                                platform=platform,
                                defaults={
                                    'pricing_data': self._get_pricing_data(platform_config, webinar),
                                    'is_active': True,
                                    'discount_percentage': 0,
                                }
                            )

                            if created:
                                platform_created += 1
                                created_count += 1
                                if not dry_run:
                                    self.stdout.write(
                                        self.style.SUCCESS(
                                            f'  ✅ Created: {webinar.webinar_id} - {webinar.title[:50]}'
                                        )
                                    )
                            elif update_existing:
                                # Update existing record
                                platform_price.pricing_data = self._get_pricing_data(platform_config, webinar)
                                platform_price.is_active = True
                                if not dry_run:
                                    platform_price.save()
                                platform_updated += 1
                                updated_count += 1
                                self.stdout.write(
                                    self.style.WARNING(
                                        f'  🔄 Updated: {webinar.webinar_id} - {webinar.title[:50]}'
                                    )
                                )
                            else:
                                platform_skipped += 1
                                skipped_count += 1
                                # Only show first few skipped to avoid clutter
                                if platform_skipped <= 3:
                                    self.stdout.write(
                                        f'  ⏭️  Skipped: {webinar.webinar_id} - {webinar.title[:50]}'
                                    )

                        except Exception as e:
                            error_count += 1
                            self.stdout.write(
                                self.style.ERROR(
                                    f'  ❌ Error for {webinar.webinar_id}: {str(e)}'
                                )
                            )
                    
                    # Platform summary
                    self.stdout.write(
                        f'\n   Platform Summary: '
                        f'✅ {platform_created} created, '
                        f'🔄 {platform_updated} updated, '
                        f'⏭️ {platform_skipped} skipped'
                    )

                if dry_run:
                    # Rollback transaction in dry run mode
                    transaction.set_rollback(True)
                    self.stdout.write(self.style.WARNING('\n🔄 DRY RUN - No changes saved'))

        except Exception as e:
            self.stdout.write(self.style.ERROR(f'\n❌ Fatal error: {str(e)}'))
            import traceback
            traceback.print_exc()
            return

        # Print detailed summary
        self.stdout.write('\n' + '='*70)
        self.stdout.write(self.style.SUCCESS('📊 FINAL SUMMARY'))
        self.stdout.write('='*70)
        self.stdout.write(f'Total webinars processed: {total_webinars}')
        self.stdout.write(f'Total platforms processed: {total_platforms}')
        self.stdout.write(self.style.SUCCESS(f'✅ Created: {created_count}'))
        if update_existing:
            self.stdout.write(self.style.WARNING(f'🔄 Updated: {updated_count}'))
        self.stdout.write(f'⏭️  Skipped: {skipped_count}')
        if error_count > 0:
            self.stdout.write(self.style.ERROR(f'❌ Errors: {error_count}'))
        self.stdout.write('='*70)

        if dry_run:
            self.stdout.write(
                self.style.WARNING(
                    '\n💡 This was a dry run. Use without --dry-run to apply changes.'
                )
            )
        else:
            self.stdout.write(
                self.style.SUCCESS(
                    '\n✅ Platform prices have been successfully configured!'
                )
            )
            
        # Show pricing examples for each platform
        if created_count > 0 or updated_count > 0:
            self.stdout.write('\n' + '='*70)
            self.stdout.write(self.style.SUCCESS('💰 PLATFORM PRICING EXAMPLES'))
            self.stdout.write('='*70)
            
            for platform in platforms:
                config = self.PLATFORM_PRICING.get(platform.platform_id)
                if config:
                    self.stdout.write(f'\n{platform.name} ({platform.platform_id}):')
                    self.stdout.write(f'  Live Single:    ${config.get("live_single_price")}')
                    self.stdout.write(f'  Live Multi:     ${config.get("live_multi_price")}')
                    self.stdout.write(f'  Recorded Single: ${config.get("recorded_single_price")}')
                    self.stdout.write(f'  Recorded Multi:  ${config.get("recorded_multi_price")}')
                    self.stdout.write(f'  Combo Single:   ${config.get("combo_single_price")}')
                    self.stdout.write(f'  Combo Multi:    ${config.get("combo_multi_price")}')
            
            self.stdout.write('\n' + '='*70)

    def _get_pricing_data(self, platform_config, webinar):
        """Build pricing data based on webinar type"""
        pricing_data = {}
        
        # Add prices based on webinar type
        if webinar.webinar_type == 'live':
            # Live webinars get all pricing options
            pricing_data = {
                'live_single_price': platform_config.get('live_single_price'),
                'live_multi_price': platform_config.get('live_multi_price'),
                'recorded_single_price': platform_config.get('recorded_single_price'),
                'recorded_multi_price': platform_config.get('recorded_multi_price'),
                'combo_single_price': platform_config.get('combo_single_price'),
                'combo_multi_price': platform_config.get('combo_multi_price'),
            }
        elif webinar.webinar_type == 'recorded':
            # Recorded webinars only get recorded pricing
            pricing_data = {
                'recorded_single_price': platform_config.get('recorded_single_price'),
                'recorded_multi_price': platform_config.get('recorded_multi_price'),
            }
        
        # Remove None values
        return {k: v for k, v in pricing_data.items() if v is not None}