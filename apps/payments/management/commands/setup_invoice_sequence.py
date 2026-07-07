"""
Management command to setup PostgreSQL sequence for invoice generation

Usage:
    python manage.py setup_invoice_sequence
    python manage.py setup_invoice_sequence --reset
    python manage.py setup_invoice_sequence --test
"""

from django.core.management.base import BaseCommand, CommandError
from django.db import connection
from apps.payments.models import Payment
from apps.platforms.models import Platform
import logging

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = 'Setup PostgreSQL sequence for invoice number generation'

    def add_arguments(self, parser):
        parser.add_argument(
            '--reset',
            action='store_true',
            help='Drop and recreate sequence (WARNING: Use with caution)',
        )
        parser.add_argument(
            '--test',
            action='store_true',
            help='Test invoice generation after setup',
        )
        parser.add_argument(
            '--platform',
            type=str,
            help='Platform ID for testing (default: first platform)',
        )

    def handle(self, *args, **options):
        reset = options['reset']
        test = options['test']
        platform_id = options['platform']

        self.stdout.write(self.style.NOTICE("\n" + "="*70))
        self.stdout.write(self.style.NOTICE("  PostgreSQL Invoice Sequence Setup"))
        self.stdout.write(self.style.NOTICE("="*70 + "\n"))

        try:
            # Step 1: Analyze existing invoices
            self.stdout.write("📊 Analyzing existing invoices...")
            
            highest = Payment.objects.filter(
                invoice_number__isnull=False,
                status='completed'
            ).order_by('-invoice_number').first()

            if highest:
                parts = highest.invoice_number.split('-')
                next_seq = int(parts[-1]) + 1
                
                self.stdout.write(
                    self.style.SUCCESS(f"   ✅ Highest invoice found: {highest.invoice_number}")
                )
                self.stdout.write(
                    self.style.WARNING(f"   📋 Next sequence will start at: {next_seq}")
                )
            else:
                next_seq = 1
                self.stdout.write(
                    self.style.WARNING("   ⚠️  No existing invoices found - starting at 1")
                )

            # Step 2: Check if sequence exists
            self.stdout.write("\n🔍 Checking sequence existence...")
            
            with connection.cursor() as cursor:
                cursor.execute("""
                    SELECT EXISTS (
                        SELECT 1 FROM information_schema.sequences 
                        WHERE sequence_name = 'invoice_number_seq'
                    );
                """)
                sequence_exists = cursor.fetchone()[0]

            if sequence_exists:
                if reset:
                    self.stdout.write(
                        self.style.WARNING("   🗑️  Sequence exists - dropping and recreating...")
                    )
                else:
                    self.stdout.write(
                        self.style.SUCCESS("   ✅ Sequence already exists")
                    )
                    
                    # Get current value
                    with connection.cursor() as cursor:
                        cursor.execute("SELECT last_value FROM invoice_number_seq;")
                        current_value = cursor.fetchone()[0]
                    
                    self.stdout.write(
                        self.style.SUCCESS(f"   📊 Current sequence value: {current_value}")
                    )
                    
                    if not test:
                        self.stdout.write(
                            self.style.WARNING(
                                "\n   💡 Sequence already exists. Use --reset to recreate or --test to verify."
                            )
                        )
                        return

            # Step 3: Create/Reset sequence
            if not sequence_exists or reset:
                self.stdout.write("\n🔧 Creating PostgreSQL sequence...")
                
                with connection.cursor() as cursor:
                    # Drop if exists
                    if reset:
                        cursor.execute("DROP SEQUENCE IF EXISTS invoice_number_seq CASCADE;")
                        self.stdout.write(
                            self.style.WARNING("   🗑️  Dropped existing sequence")
                        )
                    
                    # Create sequence
                    cursor.execute(f"""
                        CREATE SEQUENCE invoice_number_seq
                        INCREMENT BY 1
                        MINVALUE 1
                        NO MAXVALUE
                        START WITH {next_seq}
                        CACHE 1
                        NO CYCLE;
                    """)
                    
                    self.stdout.write(
                        self.style.SUCCESS(f"   ✅ Sequence created starting at {next_seq}")
                    )

            # Step 4: Create optimized index
            self.stdout.write("\n📇 Creating optimized index...")
            
            with connection.cursor() as cursor:
                cursor.execute("""
                    CREATE INDEX IF NOT EXISTS idx_payments_invoice_lookup 
                    ON payments (platform_id, invoice_number) 
                    WHERE invoice_number IS NOT NULL AND status = 'completed';
                """)
                
                self.stdout.write(
                    self.style.SUCCESS("   ✅ Index created: idx_payments_invoice_lookup")
                )

            # Step 5: Verify sequence
            self.stdout.write("\n✔️  Verifying sequence...")
            
            with connection.cursor() as cursor:
                cursor.execute("""
                    SELECT sequence_name, last_value, increment_by, max_value, cache_size
                    FROM information_schema.sequences 
                    WHERE sequence_name = 'invoice_number_seq';
                """)
                result = cursor.fetchone()

            if result:
                self.stdout.write(self.style.SUCCESS("   ✅ Sequence verified:"))
                self.stdout.write(f"      Name: {result[0]}")
                self.stdout.write(f"      Current value: {result[1]}")
                self.stdout.write(f"      Increment: {result[2]}")
                self.stdout.write(f"      Cache size: {result[4]}")
            else:
                raise CommandError("❌ Sequence verification failed")

            # Step 6: Verify invoice integrity
            self.stdout.write("\n🔒 Checking invoice integrity...")
            
            missing_count = Payment.get_payments_without_invoices().count()
            total_completed = Payment.objects.filter(status='completed').count()
            
            if missing_count > 0:
                self.stdout.write(
                    self.style.ERROR(
                        f"   ⚠️  {missing_count} of {total_completed} completed payments are missing invoices"
                    )
                )
            else:
                self.stdout.write(
                    self.style.SUCCESS(
                        f"   ✅ All {total_completed} completed payments have invoices"
                    )
                )

            # Step 7: Test invoice generation (optional)
            if test or options['test']:
                self.stdout.write("\n🧪 Testing invoice generation...")
                
                try:
                    # Get platform
                    if platform_id:
                        platform = Platform.objects.get(platform_id=platform_id)
                    else:
                        platform = Platform.objects.first()
                    
                    if not platform:
                        raise CommandError("❌ No platform found for testing")
                    
                    self.stdout.write(f"   📋 Platform: {platform.name}")
                    
                    # Get current sequence value
                    current_seq = Payment.get_current_sequence_value()
                    self.stdout.write(f"   📊 Current sequence: {current_seq}")
                    
                    # Generate test invoice
                    test_invoice = Payment.generate_unique_invoice_number(platform)
                    
                    self.stdout.write(
                        self.style.SUCCESS(f"   ✅ Generated test invoice: {test_invoice}")
                    )
                    
                    # Reset sequence after test
                    with connection.cursor() as cursor:
                        cursor.execute(f"SELECT setval('invoice_number_seq', {current_seq}, false);")
                    
                    self.stdout.write(
                        self.style.SUCCESS(f"   🔄 Sequence reset to {current_seq} (test invoice not saved)")
                    )
                    
                except Exception as e:
                    self.stdout.write(
                        self.style.ERROR(f"   ❌ Test failed: {e}")
                    )

            # Success summary
            self.stdout.write("\n" + "="*70)
            self.stdout.write(self.style.SUCCESS("✅ Invoice sequence setup complete!"))
            self.stdout.write("="*70 + "\n")
            
            # Next steps
            self.stdout.write(self.style.NOTICE("📝 Next steps:"))
            self.stdout.write("   1. All future payments will use sequential invoice numbers")
            self.stdout.write("   2. Monitor with: Payment.get_current_sequence_value()")
            self.stdout.write("   3. Verify integrity: Payment.verify_invoice_integrity()")
            
            if missing_count > 0:
                self.stdout.write(
                    self.style.WARNING(
                        f"\n⚠️  Action needed: {missing_count} payments need invoice backfilling"
                    )
                )

        except Exception as e:
            self.stdout.write("\n" + "="*70)
            self.stdout.write(self.style.ERROR(f"❌ Setup failed: {e}"))
            self.stdout.write("="*70 + "\n")
            logger.error(f"Invoice sequence setup failed: {e}")
            raise CommandError(f"Setup failed: {e}")
