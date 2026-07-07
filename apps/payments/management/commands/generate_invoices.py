# apps/payments/management/commands/generate_invoices.py
from django.core.management.base import BaseCommand
from apps.payments.models import Payment
from apps.payments.invoice_generator import InvoiceGenerator

class Command(BaseCommand):
    help = 'Generate invoices for completed payments missing invoice numbers'

    def handle(self, *args, **options):
        self.stdout.write('🔄 Starting invoice generation process...\n')

        # Query payments without invoices
        payments = Payment.get_payments_without_invoices()
        total = payments.count()
        success_count = 0
        failure_count = 0

        for payment in payments:
            try:
                # Generate invoice number
                payment.invoice_number = Payment.generate_unique_invoice_number(payment.platform)
                payment.save(update_fields=['invoice_number'])
                
                # Generate invoice PDF (optional)
                generator = InvoiceGenerator(platform=payment.platform)
                pdf = generator.generate_invoice(payment)
                # You can save/send pdf here
                
                self.stdout.write(self.style.SUCCESS(f'✅ Generated invoice for Payment ID {payment.id}'))
                success_count += 1
            except Exception as e:
                self.stderr.write(f'❌ Error generating invoice for Payment ID {payment.id}: {str(e)}')
                failure_count += 1

        self.stdout.write('\n📊 Process Summary:')
        self.stdout.write(f'  Total payments checked: {total}')
        self.stdout.write(self.style.SUCCESS(f'  Successful invoices generated: {success_count}'))
        self.stdout.write(self.style.ERROR(f'  Failures: {failure_count}'))
        self.stdout.write('\n✅ Done!\n')
