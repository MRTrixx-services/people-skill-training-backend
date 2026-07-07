from django.core.management.base import BaseCommand
from django.db import transaction
from apps.webinars.models import Webinar
from decimal import Decimal


class Command(BaseCommand):
    help = 'Update default pricing_data for all webinars based on a base platform pricing'

    # Base pricing configuration (you can use any platform as base)
    BASE_PRICING = {
           'live_single_price': 147,
            'live_multi_price': 390,
            'recorded_single_price': 189,
            'recorded_multi_price': 350,
            'combo_single_price': 310,
            'combo_multi_price': 590,
    }

    def add_arguments(self, parser):
        parser.add_argument(
            '--webinar-id',
            type=str,
            help='Specific webinar ID to update (optional)',
        )
        parser.add_argument(
            '--webinar-type',
            type=str,
            choices=['live', 'recorded'],
            help='Only update webinars of specific type',
        )
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Show what would be updated without making changes',
        )
        parser.add_argument(
            '--update-existing',
            action='store_true',
            help='Update webinars that already have pricing data',
        )
        parser.add_argument(
            '--live-single',
            type=float,
            help='Live single price (default: 149)',
        )
        parser.add_argument(
            '--live-multi',
            type=float,
            help='Live multi price (default: 299)',
        )
        parser.add_argument(
            '--recorded-single',
            type=float,
            help='Recorded single price (default: 199)',
        )
        parser.add_argument(
            '--recorded-multi',
            type=float,
            help='Recorded multi price (default: 359)',
        )
        parser.add_argument(
            '--combo-single',
            type=float,
            help='Combo single price (default: 299)',
        )
        parser.add_argument(
            '--combo-multi',
            type=float,
            help='Combo multi price (default: 569)',
        )

    def handle(self, *args, **options):
        webinar_id = options.get('webinar_id')
        webinar_type = options.get('webinar_type')
        dry_run = options.get('dry_run')
        update_existing = options.get('update_existing')

        # Update base pricing from command line arguments
        base_pricing = self.BASE_PRICING.copy()
        if options.get('live_single'):
            base_pricing['live_single_price'] = options['live_single']
        if options.get('live_multi'):
            base_pricing['live_multi_price'] = options['live_multi']
        if options.get('recorded_single'):
            base_pricing['recorded_single_price'] = options['recorded_single']
        if options.get('recorded_multi'):
            base_pricing['recorded_multi_price'] = options['recorded_multi']
        if options.get('combo_single'):
            base_pricing['combo_single_price'] = options['combo_single']
        if options.get('combo_multi'):
            base_pricing['combo_multi_price'] = options['combo_multi']

        self.stdout.write(self.style.SUCCESS('Starting webinar default pricing update...'))
        
        if dry_run:
            self.stdout.write(self.style.WARNING('DRY RUN MODE - No changes will be made'))

        # Display pricing being applied
        self.stdout.write('\n📊 Base Pricing Configuration:')
        for key, value in base_pricing.items():
            self.stdout.write(f'  {key}: ${value}')

        # Get webinars to process
        webinars = Webinar.objects.exclude(status='cancelled')
        
        if webinar_id:
            webinars = webinars.filter(webinar_id=webinar_id)
            if not webinars.exists():
                self.stdout.write(self.style.ERROR(f'Webinar not found: {webinar_id}'))
                return
        
        if webinar_type:
            webinars = webinars.filter(webinar_type=webinar_type)

        total_webinars = webinars.count()
        self.stdout.write(f'\nProcessing {total_webinars} webinars...\n')

        updated_count = 0
        skipped_count = 0
        error_count = 0

        try:
            with transaction.atomic():
                for webinar in webinars:
                    try:
                        # Check if already has pricing
                        has_pricing = bool(webinar.pricing_data and any(
                            webinar.pricing_data.get(k) 
                            for k in ['live_single_price', 'live_multi_price', 
                                    'recorded_single_price', 'recorded_multi_price',
                                    'combo_single_price', 'combo_multi_price']
                        ))

                        if has_pricing and not update_existing:
                            skipped_count += 1
                            self.stdout.write(
                                f'⏭️  Skipped (has pricing): {webinar.webinar_id} - {webinar.title[:50]}'
                            )
                            continue


                        # Build pricing data based on webinar type
                        pricing_data = self._get_pricing_for_type(base_pricing, webinar.webinar_type)
                        
                        # Update webinar pricing
                        webinar.pricing_data = pricing_data
                        
                        if not dry_run:
                            webinar.save(update_fields=['pricing_data', 'updated_at'])
                        
                        updated_count += 1
                        
                        action = '🔄 Updated' if has_pricing else '✅ Created'
                        self.stdout.write(
                            self.style.SUCCESS(
                                f'{action}: {webinar.webinar_id} ({webinar.get_webinar_type_display()}) - {webinar.title[:50]}'
                            )
                        )
                        
                        # Show pricing details
                        if updated_count <= 5 or webinar_id:  # Show details for first 5 or specific webinar
                            self.stdout.write(f'  Pricing: {pricing_data}')

                    except Exception as e:
                        error_count += 1
                        self.stdout.write(
                            self.style.ERROR(
                                f'❌ Error for {webinar.webinar_id}: {str(e)}'
                            )
                        )

                if dry_run:
                    transaction.set_rollback(True)
                    self.stdout.write(self.style.WARNING('\n🔄 DRY RUN - No changes saved'))

        except Exception as e:
            self.stdout.write(self.style.ERROR(f'\n❌ Fatal error: {str(e)}'))
            import traceback
            traceback.print_exc()
            return

        # Print summary
        self.stdout.write('\n' + '='*70)
        self.stdout.write(self.style.SUCCESS('📊 SUMMARY'))
        self.stdout.write('='*70)
        self.stdout.write(f'Total webinars processed: {total_webinars}')
        self.stdout.write(self.style.SUCCESS(f'✅ Updated: {updated_count}'))
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
                    '\n✅ Webinar default pricing has been successfully updated!'
                )
            )

        # Show breakdown by type
        if not webinar_id:
            self.stdout.write('\n' + '='*70)
            self.stdout.write(self.style.SUCCESS('📈 BREAKDOWN BY TYPE'))
            self.stdout.write('='*70)
            
            live_count = Webinar.objects.filter(webinar_type='live').exclude(status='cancelled').count()
            recorded_count = Webinar.objects.filter(webinar_type='recorded').exclude(status='cancelled').count()
            
            self.stdout.write(f'Live webinars: {live_count}')
            self.stdout.write(f'Recorded webinars: {recorded_count}')
            self.stdout.write('='*70)

    def _get_pricing_for_type(self, base_pricing, webinar_type):
        """Build pricing data based on webinar type"""
        if webinar_type == 'live':
            # Live webinars get all pricing options
            return {
                'live_single_price': base_pricing['live_single_price'],
                'live_multi_price': base_pricing['live_multi_price'],
                'recorded_single_price': base_pricing['recorded_single_price'],
                'recorded_multi_price': base_pricing['recorded_multi_price'],
                'combo_single_price': base_pricing['combo_single_price'],
                'combo_multi_price': base_pricing['combo_multi_price'],
            }
        elif webinar_type == 'recorded':
            # Recorded webinars only get recorded pricing
            return {
                'recorded_single_price': base_pricing['recorded_single_price'],
                'recorded_multi_price': base_pricing['recorded_multi_price'],
            }
        
        return {}