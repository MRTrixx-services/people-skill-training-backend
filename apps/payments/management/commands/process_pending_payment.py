from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone
from apps.payments.models import Payment, PaymentWebinar
from apps.enrollments.models import Enrollment
from apps.payments.gateway_manager import payment_gateway_manager
from apps.notifications.email_service import send_payment_confirmation_email_task
import logging
import uuid


logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = 'Process pending payments manually by transaction ID'

    def add_arguments(self, parser):
        parser.add_argument(
            'transaction_id',
            type=str,
            help='Transaction ID of the pending payment'
        )
        parser.add_argument(
            '--verify',
            action='store_true',
            help='Verify payment with gateway before processing'
        )
        parser.add_argument(
            '--force',
            action='store_true',
            help='Force process without gateway verification'
        )

    def handle(self, *args, **options):
        transaction_id = options['transaction_id']
        verify_gateway = options.get('verify', False)
        force = options.get('force', False)

        try:
            # Get payment
            payment = Payment.objects.select_related(
                'user', 'platform'
            ).get(transaction_id=transaction_id)
            
            self.stdout.write(f"Found payment: {payment.transaction_id}")
            self.stdout.write(f"Status: {payment.status}")
            self.stdout.write(f"Amount: {payment.currency} {payment.amount}")
            self.stdout.write(f"User: {payment.user.email}")
            self.stdout.write(f"Platform: {payment.platform.name if payment.platform else 'N/A'}")
            
            # Check current status
            if payment.status == 'completed':
                self.stdout.write(self.style.WARNING(
                    'Payment already completed. Use --force to reprocess.'
                ))
                if not force:
                    return
            
            # Verify with gateway if requested
            if verify_gateway and not force:
                gateway = payment_gateway_manager.get_gateway(payment.payment_method)
                if gateway:
                    self.stdout.write('Verifying with payment gateway...')
                    self.stdout.write(self.style.WARNING(
                        'Gateway verification requires additional payment data.'
                    ))
                    return
            
            # Process payment
            with transaction.atomic():
                # Generate invoice if missing
                if not payment.invoice_number:
                    payment.invoice_number = self.generate_safe_invoice_number(payment)
                
                # Update payment status
                payment.status = 'completed'
                payment.completed_at = timezone.now()
                payment.save(update_fields=[
                    'invoice_number', 'status', 'completed_at'
                ])
                
                self.stdout.write(self.style.SUCCESS(
                    f'✓ Payment marked as completed (Invoice: {payment.invoice_number})'
                ))
                
                # Create enrollments
                payment_webinars = PaymentWebinar.objects.filter(
                    payment=payment
                ).select_related('webinar', 'webinar__speaker', 'webinar__speaker__user')
                
                created_count = 0
                existing_count = 0
                
                for pw in payment_webinars:
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
                        created_count += 1
                        self.stdout.write(self.style.SUCCESS(
                            f'  ✓ Created enrollment: {pw.webinar.title}'
                        ))
                    else:
                        existing_count += 1
                        self.stdout.write(self.style.WARNING(
                            f'  • Enrollment already exists: {pw.webinar.title}'
                        ))
                
                self.stdout.write(f'\nEnrollments: {created_count} created, {existing_count} existing')
                
                # Send confirmation email
                try:
                    task = send_payment_confirmation_email_task.delay(
                        payment.user.id, 
                        payment.id
                    )
                    self.stdout.write(self.style.SUCCESS(
                        f'✓ Email queued (Task: {task.id})'
                    ))
                except Exception as e:
                    self.stdout.write(self.style.ERROR(
                        f'✗ Failed to queue email: {str(e)}'
                    ))
            
            self.stdout.write(self.style.SUCCESS(
                f'\n✓ Successfully processed payment {transaction_id}'
            ))
            
        except Payment.DoesNotExist:
            raise CommandError(f'Payment with transaction ID "{transaction_id}" not found')
        
        except Exception as e:
            logger.error(f"Error processing payment: {str(e)}", exc_info=True)
            raise CommandError(f'Error processing payment: {str(e)}')

    def generate_safe_invoice_number(self, payment):
        """
        Safe invoice number generation using platform's invoice_prefix
        Format: PREFIX-YYYYMMDDHHMMSS-XXXX
        Example: DRINV-20251206020000-A3F2
        """
        try:
            # ✅ Priority 1: Use platform's invoice_prefix field (configured in admin)
            if payment.platform and hasattr(payment.platform, 'invoice_prefix') and payment.platform.invoice_prefix:
                platform_prefix = payment.platform.invoice_prefix
            # ✅ Priority 2: Use platform_id (first 3 chars uppercase)
            elif payment.platform and hasattr(payment.platform, 'platform_id') and payment.platform.platform_id:
                platform_prefix = payment.platform.platform_id[:3].upper()
            # ✅ Priority 3: Generate from platform name
            elif payment.platform and payment.platform.name:
                words = payment.platform.name.replace('-', ' ').replace('_', ' ').split()
                platform_prefix = ''.join([word[0].upper() for word in words if word])[:3] or 'INV'
            # ✅ Priority 4: Default fallback
            else:
                platform_prefix = 'INV'
            
            # Timestamp + random suffix (ensures uniqueness)
            timestamp = timezone.now().strftime('%Y%m%d%H%M%S')
            random_suffix = str(uuid.uuid4()).split('-')[-1][:4].upper()
            invoice_number = f"{platform_prefix}-{timestamp}-{random_suffix}"
            
            # Collision check (extremely rare but safe)
            attempts = 0
            while Payment.objects.filter(invoice_number=invoice_number).exists() and attempts < 3:
                random_suffix = str(uuid.uuid4()).split('-')[-1][:4].upper()
                invoice_number = f"{platform_prefix}-{timestamp}-{random_suffix}"
                attempts += 1
            
            logger.info(f"Generated invoice: {invoice_number} for platform: {payment.platform.name if payment.platform else 'None'}")
            return invoice_number
            
        except Exception as e:
            # Ultimate fallback: transaction_id based
            logger.warning(f"Invoice generation fallback used: {str(e)}")
            return f"INV-{payment.transaction_id[:12].upper()}"
