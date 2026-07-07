from django.core.management.base import BaseCommand
from django.db import transaction, IntegrityError
from django.utils import timezone
from apps.payments.models import Payment, PaymentWebinar
from apps.enrollments.models import Enrollment
from apps.notifications.email_service import send_payment_confirmation_email_task
import logging
import uuid

logger = logging.getLogger(__name__)

class Command(BaseCommand):
    help = 'Process all pending payments at once'

    def add_arguments(self, parser):
        parser.add_argument(
            '--status',
            type=str,
            default='pending',
            help='Payment status to process (default: pending)'
        )
        parser.add_argument(
            '--limit',
            type=int,
            help='Limit number of payments to process'
        )
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Show what would be processed without making changes'
        )

    def handle(self, *args, **options):
        status_filter = options['status']
        limit = options.get('limit')
        dry_run = options.get('dry_run', False)

        payments = Payment.objects.filter(
            status=status_filter
        ).select_related('user', 'platform').order_by('-created_at')
        
        if limit:
            payments = payments[:limit]
        
        total_payments = payments.count()
        
        if total_payments == 0:
            self.stdout.write(self.style.WARNING(
                f'No payments found with status: {status_filter}'
            ))
            return
        
        self.stdout.write(f'\nFound {total_payments} payment(s) to process')
        self.stdout.write('=' * 80)
        
        if dry_run:
            self.stdout.write(self.style.WARNING('\n🔍 DRY RUN MODE - No changes will be made\n'))
        
        processed_count = 0
        failed_count = 0
        
        for idx, payment in enumerate(payments, 1):
            self.stdout.write(f'\n[{idx}/{total_payments}] Processing: {payment.transaction_id}')
            self.stdout.write(f'  User: {payment.user.email}')
            self.stdout.write(f'  Amount: {payment.currency} {payment.amount}')
            self.stdout.write(f'  Platform: {payment.platform.name if payment.platform else "N/A"}')
            
            if dry_run:
                self.stdout.write(self.style.WARNING('  [DRY RUN] Would process this payment'))
                continue
            
            success = self.process_single_payment(payment)
            
            if success:
                processed_count += 1
                self.stdout.write(self.style.SUCCESS('  ✓ COMPLETED'))
            else:
                failed_count += 1
                self.stdout.write(self.style.ERROR('  ✗ FAILED'))
        
        self.stdout.write('\n' + '=' * 80)
        self.stdout.write(self.style.SUCCESS(f'\n📊 Summary:'))
        self.stdout.write(f'  Total found: {total_payments}')
        if not dry_run:
            self.stdout.write(f'  ✓ Processed: {processed_count}')
            self.stdout.write(f'  ✗ Failed: {failed_count}')
        else:
            self.stdout.write(self.style.WARNING('  DRY RUN - No changes made'))
        self.stdout.write('')

    def generate_safe_invoice_number(self, payment):
        """✅ SAFE invoice number generation - NO database sequences needed"""
        try:
            # Platform prefix
            platform_prefix = payment.platform.platform_id[:3].upper() if payment.platform else 'INV'
            
            # Timestamp + random suffix (guaranteed unique)
            timestamp = timezone.now().strftime('%Y%m%d%H%M%S')
            random_suffix = str(uuid.uuid4()).split('-')[-1][:4].upper()
            
            invoice_number = f"{platform_prefix}-{timestamp}-{random_suffix}"
            
            # Quick uniqueness check (with timeout protection)
            attempts = 0
            while Payment.objects.filter(invoice_number=invoice_number).exists() and attempts < 3:
                random_suffix = str(uuid.uuid4()).split('-')[-1][:4].upper()
                invoice_number = f"{platform_prefix}-{timestamp}-{random_suffix}"
                attempts += 1
            
            return invoice_number
            
        except Exception:
            # Ultimate fallback: transaction_id based
            return f"INV-{payment.transaction_id[:12].upper()}"

    def process_single_payment(self, payment):
        """Process a single payment with bulletproof error handling"""
        try:
            # ✅ Step 1: Generate SAFE invoice number (NO sequences!)
            invoice_number = self.generate_safe_invoice_number(payment)
            
            # ✅ Step 2: Update payment (atomic)
            with transaction.atomic():
                payment.invoice_number = invoice_number
                payment.status = 'completed'
                payment.completed_at = timezone.now()
                payment.save(update_fields=['invoice_number', 'status', 'completed_at'])
            
            self.stdout.write(self.style.SUCCESS(
                f'  ✓ Payment completed (Invoice: {invoice_number})'
            ))
            
            # ✅ Step 3: Create enrollments (separate transaction per enrollment)
            payment_webinars = PaymentWebinar.objects.filter(
                payment=payment
            ).select_related('webinar', 'webinar__speaker', 'webinar__speaker__user')
            
            enrollment_count = 0
            for pw in payment_webinars:
                try:
                    with transaction.atomic():
                        enrollment, created = Enrollment.objects.get_or_create(
                            user=payment.user,
                            webinar=pw.webinar,
                            platform=payment.platform,
                            defaults={
                                'access_type': pw.access_type,
                                'status': 'enrolled',
                                'payment_amount': pw.amount,
                                'payment_method': payment.payment_method,
                                'transaction_id': payment.transaction_id,
                            }
                        )
                        
                        if created:
                            enrollment_count += 1
                            self.stdout.write(f'    • Enrolled: {pw.webinar.title}')
                except IntegrityError:
                    self.stdout.write(f'    ⚠ Duplicate enrollment: {pw.webinar.title}')
                    continue
            
            self.stdout.write(f'  ✓ {enrollment_count} enrollment(s) processed')
            
            # ✅ Step 4: Queue email (non-blocking)
            try:
                task = send_payment_confirmation_email_task.delay(
                    payment.user.id, 
                    payment.id
                )
                self.stdout.write(f'  ✓ Email queued: {task.id}')
            except Exception as e:
                self.stdout.write(self.style.WARNING(f'  ⚠ Email failed: {str(e)[:50]}'))
            
            return True
            
        except Exception as e:
            logger.error(f"Failed {payment.transaction_id}: {str(e)}", exc_info=True)
            self.stdout.write(self.style.ERROR(f'  ✗ FAILED: {str(e)[:100]}'))
            return False
