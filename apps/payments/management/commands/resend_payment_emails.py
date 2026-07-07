# apps/payments/management/commands/resend_payment_emails.py
from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone
from apps.payments.models import Payment, PaymentWebinar
from apps.enrollments.models import Enrollment
from apps.notifications.email_service import EmailService  # ✅ CORRECTED: apps.core not apps.notifications
import logging
import re

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = 'Resend payment confirmation emails for completed PayPal payments that failed Django verification'

    def add_arguments(self, parser):
        parser.add_argument(
            '--transaction-id',
            type=str,
            help='Specific transaction ID to process'
        )
        parser.add_argument(
            '--all-pending',
            action='store_true',
            help='Process all pending PayPal payments'
        )
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Show what would be done without actually doing it'
        )

    def generate_slug(self, title):
        """Generate URL-friendly slug from title"""
        slug = title.lower()
        slug = re.sub(r'[^a-z0-9\s-]', '', slug)
        slug = re.sub(r'\s+', '-', slug)
        slug = re.sub(r'-+', '-', slug)
        return slug.strip('-')

    def process_payment(self, payment, dry_run=False):
        """Process a single payment and send confirmation email"""
        try:
            user = payment.user
            platform = payment.platform
            
            self.stdout.write(f"\n{'[DRY RUN] ' if dry_run else ''}Processing: {payment.transaction_id}")
            self.stdout.write(f"  User: {user.email}")
            self.stdout.write(f"  Amount: ${payment.amount}")
            self.stdout.write(f"  Status: {payment.status}")
            
            # Get frontend URL
            frontend_url = f"https://{platform.domain}" if platform and platform.domain else 'https://peopleskilltraining.com'
            
            # Get payment webinars
            payment_webinars = PaymentWebinar.objects.filter(payment=payment).select_related(
                'webinar', 'webinar__speaker', 'webinar__speaker__user'
            )
            
            if not payment_webinars.exists():
                self.stdout.write(self.style.WARNING(f"  ⚠️  No webinars found for payment {payment.transaction_id}"))
                return False
            
            webinar_details = []
            
            for pw in payment_webinars:
                # Create enrollment
                if not dry_run:
                    enrollment, created = Enrollment.objects.get_or_create(
                        user=user,
                        webinar=pw.webinar,
                        platform=platform,
                        defaults={
                            'access_type': pw.access_type,
                            'status': 'enrolled',
                            'payment_amount': pw.amount,
                            'payment_method': payment.payment_method,
                            'transaction_id': payment.transaction_id,
                        }
                    )
                    
                    if not created and enrollment.status != 'enrolled':
                        enrollment.status = 'enrolled'
                        enrollment.save()
                        self.stdout.write(f"  ✅ Updated enrollment: {pw.webinar.title}")
                    elif created:
                        self.stdout.write(f"  ✅ Created enrollment: {pw.webinar.title}")
                    else:
                        self.stdout.write(f"  ℹ️  Enrollment exists: {pw.webinar.title}")
                else:
                    self.stdout.write(f"  [DRY RUN] Would create enrollment: {pw.webinar.title}")
                
                # Generate webinar URL
                webinar_slug = self.generate_slug(pw.webinar.title)
                webinar_type = 'live-webinar' if pw.webinar.webinar_type == 'live' else 'recorded-webinar'
                webinar_url = f"{frontend_url}/{webinar_type}/{pw.webinar.webinar_id}/{webinar_slug}"
                
                # Prepare webinar details
                webinar_details.append({
                    'title': pw.webinar.title,
                    'instructor': pw.webinar.speaker.user.get_full_name() if pw.webinar.speaker else 'TBA',
                    # 'scheduled_date': pw.webinar.scheduled_date.strftime('%B %d, %Y at %I:%M %p') if pw.webinar.scheduled_date else 'On Demand',
                    'scheduled_date': pw.webinar.scheduled_date.strftime('%B %d, %Y') if pw.webinar.scheduled_date else 'On Demand',
                    
                    'duration': f"{pw.webinar.duration} minutes" if pw.webinar.duration else 'Self-paced',
                    'webinar_url': webinar_url,
                })
            
            # Update payment status
            # In the process_payment method, replace the payment update section with:

            # Update payment status
            if not dry_run and payment.status == 'pending':
                with transaction.atomic():
                    # Lock payment
                    payment = Payment.objects.select_for_update().get(pk=payment.pk)
                    
                    if payment.status == 'completed':
                        self.stdout.write(f"  ℹ️  Already completed")
                        return True
                    
                    payment.status = 'completed'
                    if not payment.completed_at:
                        payment.completed_at = timezone.now()
                    
                    # ✅ Manually generate unique invoice to avoid conflicts
                    if not payment.invoice_number:
                        year = timezone.now().year
                        month = timezone.now().month
                        
                        # Get last invoice for this month
                        last_invoice = Payment.objects.filter(
                            platform=platform,
                            invoice_number__isnull=False,
                            created_at__year=year,
                            created_at__month=month,
                            status='completed'
                        ).exclude(invoice_number='').order_by('-created_at').first()
                        
                        seq_number = 1
                        if last_invoice and last_invoice.invoice_number:
                            try:
                                parts = last_invoice.invoice_number.split('-')
                                if len(parts) >= 3:
                                    seq_number = int(parts[-1]) + 1
                            except:
                                pass
                        
                        # Keep incrementing until we find an unused number
                        while True:
                            invoice_num = f'PSINV-{year}{month:02d}-{seq_number:04d}'
                            if not Payment.objects.filter(invoice_number=invoice_num).exists():
                                payment.invoice_number = invoice_num
                                break
                            seq_number += 1
                    
                    payment.save(update_fields=['status', 'completed_at', 'invoice_number'])
                
                self.stdout.write(f"  ✅ Payment completed")
                if payment.invoice_number:
                    self.stdout.write(f"  ✅ Invoice: {payment.invoice_number}")

            # Send email
            if not dry_run:
                context = EmailService.get_email_context(
                    user=user,
                    platform=platform,
                    transaction_id=payment.transaction_id,
                    payment_date=payment.completed_at.strftime('%B %d, %Y') if payment.completed_at else timezone.now().strftime('%B %d, %Y'),
                    payment_method=payment.get_payment_method_display(),
                    total_amount=f"{payment.amount:.2f}",
                    currency=payment.currency,
                    webinars=webinar_details,
                    dashboard_url=f"{frontend_url}/my-enrollments",
                    invoice_url=f"{frontend_url}/api/payments/{payment.id}/invoice/",
                )
                
                EmailService.send_email(
                    subject=f'Payment Confirmed - {payment.transaction_id}',
                    template_name='payment_confirmation',
                    context=context,
                    recipient_list=[user.email],
                    platform=platform
                )
                
                self.stdout.write(self.style.SUCCESS(f"  ✅ Email sent to {user.email}"))
            else:
                self.stdout.write(f"  [DRY RUN] Would send email")
            
            return True
            
        except Exception as e:
            self.stdout.write(self.style.ERROR(f"  ❌ Error: {str(e)}"))
            logger.error(f"Error processing {payment.transaction_id}: {str(e)}", exc_info=True)
            return False

    def handle(self, *args, **options):
        transaction_id = options.get('transaction_id')
        all_pending = options.get('all_pending')
        dry_run = options.get('dry_run')
        
        if dry_run:
            self.stdout.write(self.style.WARNING("🔍 DRY RUN MODE"))
        
        processed = 0
        failed = 0
        
        if transaction_id:
            try:
                payment = Payment.objects.get(transaction_id=transaction_id)
                if self.process_payment(payment, dry_run):
                    processed += 1
                else:
                    failed += 1
            except Payment.DoesNotExist:
                self.stdout.write(self.style.ERROR(f"❌ Payment not found: {transaction_id}"))
                return
        
        elif all_pending:
            payments = Payment.objects.filter(
                status='pending',
                payment_method='paypal'
            ).select_related('user', 'platform')
            
            self.stdout.write(f"Found {payments.count()} pending payments")
            
            for payment in payments:
                if self.process_payment(payment, dry_run):
                    processed += 1
                else:
                    failed += 1
        
        else:
            self.stdout.write(self.style.ERROR("❌ Specify --transaction-id or --all-pending"))
            return
        
        # Summary
        self.stdout.write("\n" + "="*50)
        self.stdout.write(self.style.SUCCESS(f"✅ Processed: {processed}"))
        if failed > 0:
            self.stdout.write(self.style.ERROR(f"❌ Failed: {failed}"))
        self.stdout.write("="*50)
