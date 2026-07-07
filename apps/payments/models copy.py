from django.db import models
from django.contrib.auth import get_user_model
from django.core.validators import MinValueValidator
from django.utils import timezone
from apps.webinars.models import Webinar
import json
import uuid
import string
import random
import logging
User = get_user_model()

logger = logging.getLogger(__name__) 
def get_default_currencies():
    """Default supported currencies"""
    return ['USD', 'EUR', 'GBP']


def get_default_configuration():
    """Default empty configuration"""
    return {}


class PaymentGateway(models.Model):
    """Model to manage payment gateways via Django admin"""
    
    GATEWAY_CHOICES = [
        ('razorpay', 'Razorpay'),
        ('paypal', 'PayPal'),
        ('stripe', 'Stripe'),
        ('cashfree', 'Cashfree'),
        ('payu', 'PayU'),
    ]
    
    # Basic Info
    # gateway_id = models.CharField(max_length=20, choices=GATEWAY_CHOICES, unique=True)
    gateway_id = models.CharField(max_length=20, choices=GATEWAY_CHOICES)
    display_name = models.CharField(max_length=100)
    description = models.TextField()
    
    # Status
    is_active = models.BooleanField(default=True, help_text="Enable/disable this gateway")
    is_test_mode = models.BooleanField(default=True, help_text="Use test/sandbox mode")
    
    # Display Settings
    logo_url = models.URLField(blank=True, help_text="URL to gateway logo image")
    display_order = models.PositiveIntegerField(default=0, help_text="Order in which gateways appear (0 = first)")
    
    # Gateway Configuration (stored as JSON)
    configuration = models.JSONField(
        default=get_default_configuration,
        help_text="Gateway-specific configuration (API keys, etc.)"
    )
    
    # Supported Features
    supports_refunds = models.BooleanField(default=True)
    supports_partial_refunds = models.BooleanField(default=True)
    supports_webhooks = models.BooleanField(default=True)
    
    # Currency & Limits
    supported_currencies = models.JSONField(
        default=get_default_currencies,
        help_text="List of supported currencies ['USD', 'EUR', 'GBP']"
    )
    min_amount = models.DecimalField(
        max_digits=10, 
        decimal_places=2, 
        default=1.00,
        validators=[MinValueValidator(0)]
    )
    max_amount = models.DecimalField(
        max_digits=10, 
        decimal_places=2, 
        default=100000.00,
        validators=[MinValueValidator(0)]
    )
    
    # Processing Info
    processing_time = models.CharField(max_length=50, default="Instant")
    processing_fee_percentage = models.DecimalField(
        max_digits=5, 
        decimal_places=4, 
        default=0.0200,
        help_text="Processing fee as decimal (0.02 = 2%)"
    )
    
    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        db_table = 'payment_gateways'
        verbose_name = 'Payment Gateway'
        verbose_name_plural = 'Payment Gateways'
        ordering = ['display_order', 'display_name']
        unique_together = [('gateway_id', 'is_test_mode')]
    def __str__(self):
        status = "🟢 Active" if self.is_active else "🔴 Inactive"
        mode = "🧪 Test" if self.is_test_mode else "🚀 Live"
        return f"{self.display_name} - {status} {mode}"
    
    @property
    def is_configured(self):
        """Check if gateway is properly configured"""
        required_fields = {
            'razorpay': ['key_id', 'key_secret'],
            'paypal': ['client_id', 'client_secret'],
            'stripe': ['publishable_key', 'secret_key'],
            'cashfree': ['app_id', 'secret_key'],
            'payu': ['merchant_id', 'merchant_key', 'salt'],
        }
        
        required = required_fields.get(self.gateway_id, [])
        return all(field in self.configuration for field in required)


class Payment(models.Model):
    """Payment model - Platform-specific"""
    
    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('completed', 'Completed'),
        ('failed', 'Failed'),
        ('refunded', 'Refunded'),
        ('cancelled', 'Cancelled'),
    ]
    
    PAYMENT_METHOD_CHOICES = [
        ('razorpay', 'Razorpay'),
        ('paypal', 'PayPal'),
        ('stripe', 'Stripe'),
        ('cashfree', 'Cashfree'),
        ('payu', 'PayU'),
    ]
    
    # User and payment info
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='payments')
    
    # ✅ PLATFORM ASSIGNMENT (from user.platform)
    platform = models.ForeignKey(
        'platforms.Platform',
        on_delete=models.CASCADE,
        related_name='payments',
        help_text="Platform where payment was made (from user.platform)"
    )
    
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    currency = models.CharField(max_length=3, default='USD')
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    payment_method = models.CharField(max_length=50, choices=PAYMENT_METHOD_CHOICES)
    
    # Webinars (support multiple)
    webinars = models.ManyToManyField(Webinar, related_name='payments', through='PaymentWebinar')
    webinar = models.ForeignKey(
        Webinar, 
        on_delete=models.CASCADE, 
        related_name='single_payments', 
        null=True, 
        blank=True,
        help_text="Backward compatibility - use webinars ManyToMany instead"
    )
    
    # Transaction details
    transaction_id = models.CharField(max_length=100, unique=True, db_index=True)
    gateway_payment_id = models.CharField(max_length=100, blank=True)
    gateway_order_id = models.CharField(max_length=100, blank=True)
    failure_reason = models.TextField(blank=True)
    gateway_response = models.JSONField(
        default=dict,
        blank=True,
        help_text="Raw gateway response data for debugging"
    )
    invoice_number = models.CharField(
        max_length=50,
        unique=True,
        blank=True,
        null=True,  # ✅ This must be here
        help_text="Invoice number (generated on payment completion)"
    )
    
    # Invoice
    # invoice_number = models.CharField(
    #     max_length=50, 
    #     unique=True, 
    #     blank=True,
    #     db_index=True,
    #     help_text="Auto-generated invoice number (e.g., INV-2025-10-0001)"
    # )
    
    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        db_table = 'payments'
        verbose_name = 'Payment'
        verbose_name_plural = 'Payments'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['platform', 'status']),
            models.Index(fields=['platform', 'user']),
            models.Index(fields=['user', 'status']),
            models.Index(fields=['transaction_id']),
            models.Index(fields=['invoice_number']),
            models.Index(fields=['created_at']),
        ]
    
    def __str__(self):
        platform_name = self.platform.name if self.platform else 'No Platform'
        return f"Payment {self.transaction_id} - {self.user.email} - ${self.amount} ({platform_name})"
    
    def save(self, *args, **kwargs):
        """Auto-generate transaction_id and invoice_number on creation"""
        
        # Generate transaction_id if not set
        if not self.transaction_id:
            timestamp = timezone.now().strftime('%Y%m%d%H%M%S')
            random_str = ''.join(random.choices(string.ascii_uppercase + string.digits, k=6))
            self.transaction_id = f'TXN{timestamp}{random_str}'
        
        # Generate invoice_number only when payment is completed
        is_new_completion = (
            self.pk and 
            self.status == 'completed' and 
            not self.invoice_number
        )
        
        # Check if status changed to completed
        if self.pk:
            old_instance = Payment.objects.filter(pk=self.pk).first()
            if old_instance and old_instance.status != 'completed' and self.status == 'completed':
                is_new_completion = True
        
        if is_new_completion or (not self.pk and self.status == 'completed'):
            if not self.invoice_number:
                # ✅ Generate platform-specific invoice prefix
                if self.platform:
                    # Use platform's invoice_prefix if set, otherwise generate from name
                    if hasattr(self.platform, 'invoice_prefix') and self.platform.invoice_prefix:
                        invoice_prefix = self.platform.invoice_prefix
                    else:
                        # Generate prefix from platform name (e.g., "PeopleSkillTraining" -> "PSINV")
                        # Take first letter of each word
                        words = self.platform.name.replace('-', ' ').replace('_', ' ').split()
                        prefix = ''.join([word[0].upper() for word in words if word])
                        invoice_prefix = f"{prefix}INV"
                else:
                    # Default prefix for no platform
                    invoice_prefix = 'INV'
                
                year = timezone.now().year
                month = timezone.now().month
                
                # ✅ Get the last invoice for this platform and month
                last_invoice = Payment.objects.filter(
                    platform=self.platform,
                    invoice_number__isnull=False,
                    created_at__year=year,
                    created_at__month=month,
                    status='completed'
                ).exclude(
                    invoice_number=''
                ).order_by('-created_at').first()
                
                if last_invoice and last_invoice.invoice_number:
                    try:
                        # Extract sequence number
                        parts = last_invoice.invoice_number.split('-')
                        if len(parts) >= 3:
                            last_seq = int(parts[-1])
                            seq_number = last_seq + 1
                        else:
                            seq_number = 1
                    except (ValueError, IndexError):
                        seq_number = 1
                else:
                    seq_number = 1
                
                # ✅ Format: PSINV-202510-0001 (for PeopleSkillTraining)
                #           XYZINV-202510-0001 (for other platforms)
                self.invoice_number = f'{invoice_prefix}-{year}{month:02d}-{seq_number:04d}'
                logger.info(f"✅ Generated invoice number: {self.invoice_number} for platform: {self.platform.name if self.platform else 'None'}")
        
        # For pending/failed payments, ensure invoice_number is None
        elif self.status in ['pending', 'failed', 'refunded']:
            if not self.invoice_number:
                self.invoice_number = None
        
        super().save(*args, **kwargs)




    # def save(self, *args, **kwargs):
    #     # Auto-assign platform from user
    #     if not self.platform_id and self.user and self.user.platform:
    #         self.platform = self.user.platform
        
    #     # Generate transaction ID
    #     if not self.transaction_id:
    #         self.transaction_id = str(uuid.uuid4())
        
    #     # Generate invoice number only for completed payments
    #     if not self.invoice_number and self.status == 'completed':
    #         self.invoice_number = self.generate_invoice_number()
        
    #     super().save(*args, **kwargs)
    
    @classmethod
    def generate_invoice_number(cls):
        """Generate unique invoice number in format: INV-YYYY-MM-NNNN"""
        from django.db.models import Max
        import datetime
        
        today = datetime.date.today()
        year = today.year
        month = today.month
        
        # Get the latest invoice number for this month
        prefix = f"INV-{year}-{month:02d}-"
        
        last_payment = cls.objects.filter(
            invoice_number__startswith=prefix,
            status='completed'
        ).aggregate(Max('invoice_number'))
        
        last_number = last_payment['invoice_number__max']
        
        if last_number:
            # Extract the sequence number (e.g., "INV-2025-10-0005" -> 5)
            sequence = int(last_number.split('-')[-1]) + 1
        else:
            sequence = 1
        
        # Format: INV-2025-10-0001
        return f"{prefix}{sequence:04d}"
    
    @property
    def invoice_display_number(self):
        """Display invoice number or fallback"""
        return self.invoice_number or f"TEMP-{self.id}"


class PaymentWebinar(models.Model):
    """Junction table for Payment-Webinar relationship with pricing"""
    
    payment = models.ForeignKey(Payment, on_delete=models.CASCADE, related_name='payment_webinars')
    webinar = models.ForeignKey(Webinar, on_delete=models.CASCADE, related_name='payment_webinars')
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    access_type = models.CharField(
        max_length=50, 
        default='liveOne',
        help_text="liveOne, liveGroup, recordedOne, recordedGroup, comboOne, comboGroup"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        db_table = 'payment_webinars'
        unique_together = ('payment', 'webinar', 'access_type')
        verbose_name = 'Payment Webinar'
        verbose_name_plural = 'Payment Webinars'
        indexes = [
            models.Index(fields=['payment', 'webinar']),
        ]
    
    def __str__(self):
        return f"{self.payment.transaction_id} - {self.webinar.title} ({self.access_type}) - ${self.amount}"


class RefundRequest(models.Model):
    """Refund request model"""
    
    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('approved', 'Approved'),
        ('rejected', 'Rejected'),
        ('processed', 'Processed'),
    ]
    
    payment = models.OneToOneField(Payment, on_delete=models.CASCADE, related_name='refund_request')
    reason = models.TextField()
    admin_notes = models.TextField(blank=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    refund_amount = models.DecimalField(max_digits=10, decimal_places=2)
    gateway_refund_id = models.CharField(max_length=100, blank=True)
    
    requested_at = models.DateTimeField(auto_now_add=True)
    processed_at = models.DateTimeField(null=True, blank=True)
    processed_by = models.ForeignKey(
        User, 
        on_delete=models.SET_NULL, 
        null=True, 
        blank=True, 
        related_name='processed_refunds'
    )
    
    class Meta:
        db_table = 'refund_requests'
        verbose_name = 'Refund Request'
        verbose_name_plural = 'Refund Requests'
        ordering = ['-requested_at']
        indexes = [
            models.Index(fields=['status', 'requested_at']),
        ]
    
    def __str__(self):
        return f"Refund Request - {self.payment.transaction_id} - {self.status}"


class PaymentWebhook(models.Model):
    """Payment webhook logs"""
    
    gateway = models.CharField(max_length=50, db_index=True)
    event_type = models.CharField(max_length=100)
    webhook_id = models.CharField(max_length=100, unique=True, db_index=True)
    payload = models.JSONField()
    processed = models.BooleanField(default=False, db_index=True)
    error_message = models.TextField(blank=True)
    
    created_at = models.DateTimeField(auto_now_add=True)
    processed_at = models.DateTimeField(null=True, blank=True)
    
    class Meta:
        db_table = 'payment_webhooks'
        verbose_name = 'Payment Webhook'
        verbose_name_plural = 'Payment Webhooks'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['gateway', 'processed']),
            models.Index(fields=['webhook_id']),
            models.Index(fields=['processed', 'created_at']),
        ]
    
    def __str__(self):
        status = "✅ Processed" if self.processed else "⏳ Pending"
        return f"{self.gateway} - {self.event_type} - {status}"
