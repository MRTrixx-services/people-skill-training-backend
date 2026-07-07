# Create a management command: apps/payments/management/commands/generate_invoice_numbers.py
from django.core.management.base import BaseCommand
from apps.payments.models import Payment

class Command(BaseCommand):
    help = 'Generate invoice numbers for existing completed payments'

    def handle(self, *args, **kwargs):
        payments = Payment.objects.filter(
            status='completed',
            invoice_number=''
        ).order_by('completed_at')
        
        count = 0
        for payment in payments:
            payment.invoice_number = Payment.generate_invoice_number()
            payment.save(update_fields=['invoice_number'])
            count += 1
            self.stdout.write(f"Generated {payment.invoice_number}")
        
        self.stdout.write(self.style.SUCCESS(f'Generated {count} invoice numbers'))
