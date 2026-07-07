# apps/payments/management/commands/setup_payment_gateways.py
from django.core.management.base import BaseCommand
from apps.payments.models import PaymentGateway

class Command(BaseCommand):
    help = 'Setup initial payment gateways'
    
    def handle(self, *args, **options):
        gateways = [
            {
                'gateway_id': 'razorpay',
                'display_name': 'Razorpay',
                'description': 'Pay securely with Razorpay - UPI, Cards, Net Banking',
                'logo_url': 'https://razorpay.com/assets/razorpay-logo.svg',
                'supported_currencies': ['INR'],
                'min_amount': 1.00,
                'max_amount': 1000000.00,
                'display_order': 1
            },
            {
                'gateway_id': 'paypal',
                'display_name': 'PayPal',
                'description': 'Pay with your PayPal account or credit card',
                'logo_url': 'https://www.paypalobjects.com/webstatic/icon/pp258.png',
                'supported_currencies': ['USD', 'EUR', 'GBP'],
                'min_amount': 1.00,
                'max_amount': 10000.00,
                'display_order': 2
            },
            {
                'gateway_id': 'stripe',
                'display_name': 'Stripe',
                'description': 'Pay securely with Stripe - Cards accepted worldwide',
                'supported_currencies': ['USD', 'EUR', 'GBP', 'INR'],
                'min_amount': 0.50,
                'max_amount': 999999.99,
                'display_order': 3,
                'is_active': False  # Disabled by default
            }
        ]
        
        for gateway_data in gateways:
            gateway, created = PaymentGateway.objects.get_or_create(
                gateway_id=gateway_data['gateway_id'],
                defaults=gateway_data
            )
            
            if created:
                self.stdout.write(f"Created gateway: {gateway.display_name}")
            else:
                self.stdout.write(f"Gateway exists: {gateway.display_name}")
