# apps/payments/admin.py
from django.contrib import admin
from django.forms import ModelForm, CharField, PasswordInput
from django.utils.html import format_html

from .models import PaymentGateway, Payment, PaymentWebinar, RefundRequest


class PaymentGatewayForm(ModelForm):
    """Custom form for payment gateway with secure fields"""
    
    # Razorpay fields
    razorpay_key_id = CharField(required=False, help_text="Razorpay Key ID")
    razorpay_key_secret = CharField(required=False, widget=PasswordInput(render_value=True), help_text="Razorpay Key Secret")
    razorpay_webhook_secret = CharField(required=False, widget=PasswordInput(render_value=True), help_text="Razorpay Webhook Secret")
    
    # PayPal fields
    paypal_client_id = CharField(required=False, help_text="PayPal Client ID")
    paypal_client_secret = CharField(required=False, widget=PasswordInput(render_value=True), help_text="PayPal Client Secret")
    paypal_webhook_id = CharField(required=False, help_text="PayPal Webhook ID")
    
    # Stripe fields
    stripe_publishable_key = CharField(required=False, help_text="Stripe Publishable Key")
    stripe_secret_key = CharField(required=False, widget=PasswordInput(render_value=True), help_text="Stripe Secret Key")
    stripe_webhook_secret = CharField(required=False, widget=PasswordInput(render_value=True), help_text="Stripe Webhook Secret")
    
    # Cashfree fields
    cashfree_app_id = CharField(required=False, help_text="Cashfree App ID")
    cashfree_secret_key = CharField(required=False, widget=PasswordInput(render_value=True), help_text="Cashfree Secret Key")
    
    # PayU fields
    payu_merchant_id = CharField(required=False, help_text="PayU Merchant ID")
    payu_merchant_key = CharField(required=False, widget=PasswordInput(render_value=True), help_text="PayU Merchant Key")
    payu_salt = CharField(required=False, widget=PasswordInput(render_value=True), help_text="PayU Salt")
    
    class Meta:
        model = PaymentGateway
        fields = '__all__'
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        
        # ✅ Configure platform field
        if 'platform' in self.fields:
            from apps.platforms.models import Platform
            self.fields['platform'].queryset = Platform.objects.filter(is_active=True).order_by('name')
            self.fields['platform'].required = False  # ✅ Make optional
            self.fields['platform'].empty_label = "🌐 Global (All Platforms)"
            self.fields['platform'].help_text = "Select a platform for platform-specific gateway, or leave blank for global gateway"
        
        # Load existing configuration values
        if self.instance.pk:
            config = self.instance.configuration or {}
            gateway_id = self.instance.gateway_id
            
            if gateway_id == 'razorpay':
                self.fields['razorpay_key_id'].initial = config.get('key_id', '')
                self.fields['razorpay_key_secret'].initial = config.get('key_secret', '')
                self.fields['razorpay_webhook_secret'].initial = config.get('webhook_secret', '')
            elif gateway_id == 'paypal':
                self.fields['paypal_client_id'].initial = config.get('client_id', '')
                self.fields['paypal_client_secret'].initial = config.get('client_secret', '')
                self.fields['paypal_webhook_id'].initial = config.get('webhook_id', '')
            elif gateway_id == 'stripe':
                self.fields['stripe_publishable_key'].initial = config.get('publishable_key', '')
                self.fields['stripe_secret_key'].initial = config.get('secret_key', '')
                self.fields['stripe_webhook_secret'].initial = config.get('webhook_secret', '')
            elif gateway_id == 'cashfree':
                self.fields['cashfree_app_id'].initial = config.get('app_id', '')
                self.fields['cashfree_secret_key'].initial = config.get('secret_key', '')
            elif gateway_id == 'payu':
                self.fields['payu_merchant_id'].initial = config.get('merchant_id', '')
                self.fields['payu_merchant_key'].initial = config.get('merchant_key', '')
                self.fields['payu_salt'].initial = config.get('salt', '')
    
    def clean_platform(self):
        """✅ NEW: Convert empty platform to None for global gateways"""
        platform = self.cleaned_data.get('platform')
        # If empty/blank, return None for database NULL
        if not platform:
            return None
        return platform
    
    def save(self, commit=True):
        instance = super().save(commit=False)
        
        existing_config = instance.configuration or {}
        
        gateway_id = instance.gateway_id
        configuration = {}
        
        if gateway_id == 'razorpay':
            configuration = {
                'key_id': self.cleaned_data.get('razorpay_key_id', ''),
                'key_secret': self.cleaned_data.get('razorpay_key_secret', '') or existing_config.get('key_secret', ''),
                'webhook_secret': self.cleaned_data.get('razorpay_webhook_secret', '') or existing_config.get('webhook_secret', ''),
            }
        elif gateway_id == 'paypal':
            configuration = {
                'client_id': self.cleaned_data.get('paypal_client_id', ''),
                'client_secret': self.cleaned_data.get('paypal_client_secret', '') or existing_config.get('client_secret', ''),
                'webhook_id': self.cleaned_data.get('paypal_webhook_id', ''),
            }
        elif gateway_id == 'stripe':
            configuration = {
                'publishable_key': self.cleaned_data.get('stripe_publishable_key', ''),
                'secret_key': self.cleaned_data.get('stripe_secret_key', '') or existing_config.get('secret_key', ''),
                'webhook_secret': self.cleaned_data.get('stripe_webhook_secret', '') or existing_config.get('webhook_secret', ''),
            }
        elif gateway_id == 'cashfree':
            configuration = {
                'app_id': self.cleaned_data.get('cashfree_app_id', ''),
                'secret_key': self.cleaned_data.get('cashfree_secret_key', '') or existing_config.get('secret_key', ''),
            }
        elif gateway_id == 'payu':
            configuration = {
                'merchant_id': self.cleaned_data.get('payu_merchant_id', ''),
                'merchant_key': self.cleaned_data.get('payu_merchant_key', '') or existing_config.get('merchant_key', ''),
                'salt': self.cleaned_data.get('payu_salt', '') or existing_config.get('salt', ''),
            }
        
        configuration = {k: v for k, v in configuration.items() if v}
        instance.configuration = configuration
        
        if commit:
            instance.save()
        return instance

@admin.register(PaymentGateway)
class PaymentGatewayAdmin(admin.ModelAdmin):
    form = PaymentGatewayForm
    
    list_display = [
        'platform_name',
        'display_name', 
        'gateway_id', 
        'status_indicator', 
        'configuration_status',
        'mode_indicator',
        'scope_indicator',
        'supported_currencies_display',
        'amount_limits',
        'display_order'
    ]
    
    list_filter = [ 'platform',
    ('platform', admin.EmptyFieldListFilter), 
    'is_active', 'is_test_mode', 'gateway_id', 'supports_refunds']
    search_fields = ['display_name', 'gateway_id', 'description']
    ordering = ['display_order', 'display_name']
    
    fieldsets = (
        ('Platform & Gateway Information', {  # ✅ FIXED: Add platform field here
            'fields': (
                'platform',  # ✅ THIS WAS MISSING!
                'gateway_id', 
                'display_name', 
                'description', 
                'logo_url'
            ),
            'description': 'Select a platform for platform-specific gateway, or leave blank for global gateway.'
        }),
        ('Status & Display', {
            'fields': ('is_active', 'is_test_mode', 'display_order')
        }),
        ('Razorpay Configuration', {
            'fields': ('razorpay_key_id', 'razorpay_key_secret', 'razorpay_webhook_secret'),
            'classes': ('collapse',),
        }),
        ('PayPal Configuration', {
            'fields': ('paypal_client_id', 'paypal_client_secret', 'paypal_webhook_id'),
            'classes': ('collapse',),
        }),
        ('Stripe Configuration', {
            'fields': ('stripe_publishable_key', 'stripe_secret_key', 'stripe_webhook_secret'),
            'classes': ('collapse',),
        }),
        ('Cashfree Configuration', {
            'fields': ('cashfree_app_id', 'cashfree_secret_key'),
            'classes': ('collapse',),
        }),
        ('PayU Configuration', {
            'fields': ('payu_merchant_id', 'payu_merchant_key', 'payu_salt'),
            'classes': ('collapse',),
        }),
        ('Features & Limits', {
            'fields': (
                ('supports_refunds', 'supports_partial_refunds', 'supports_webhooks'),
                'supported_currencies',
                ('min_amount', 'max_amount'),
                'processing_time',
                'processing_fee_percentage'
            )
        }),
    )
    def scope_indicator(self, obj):
        if obj.platform:
            return format_html(
                '<span style="color: blue;" title="Platform-specific">🏢 Platform</span>'
            )
        return format_html(
            '<span style="color: purple;" title="Available to all platforms">🌐 Global</span>'
        )
    scope_indicator.short_description = 'Scope'

    def platform_name(self, obj):
        if obj.platform:
            return obj.platform.name
        return format_html('<span style="color: gray; font-style: italic;">— Global —</span>')
    platform_name.short_description = 'Platform'
    platform_name.admin_order_field = 'platform__name'
    
    def scope_indicator(self, obj):
        if obj.platform:
            return format_html(
                '<span style="color: blue;" title="Platform-specific">🏢 Platform</span>'
            )
        return format_html(
            '<span style="color: purple;" title="Available to all platforms">🌐 Global</span>'
        )
    scope_indicator.short_description = 'Scope'
    
    def status_indicator(self, obj):
        if obj.is_active:
            return format_html('<span style="color: green;">🟢 Active</span>')
        return format_html('<span style="color: red;">🔴 Inactive</span>')
    status_indicator.short_description = 'Status'
    
    def mode_indicator(self, obj):
        if obj.is_test_mode:
            return format_html('<span style="color: orange;">🧪 Test Mode</span>')
        return format_html('<span style="color: blue;">🚀 Live Mode</span>')
    mode_indicator.short_description = 'Mode'
    
    def configuration_status(self, obj):
        if obj.is_configured:
            return format_html('<span style="color: green;">✅ Configured</span>')
        return format_html('<span style="color: red;">❌ Missing Config</span>')
    configuration_status.short_description = 'Config'
    
    def supported_currencies_display(self, obj):
        currencies = obj.supported_currencies or []
        if len(currencies) <= 3:
            return ', '.join(currencies)
        return f"{', '.join(currencies[:3])}... (+{len(currencies)-3} more)"
    supported_currencies_display.short_description = 'Currencies'
    
    def amount_limits(self, obj):
        return f"${obj.min_amount} - ${obj.max_amount}"
    amount_limits.short_description = 'Amount Limits'
    
    def get_queryset(self, request):
        """Optimize queryset"""
        qs = super().get_queryset(request)
        return qs.select_related('platform')
    
    actions = ['enable_gateways', 'disable_gateways', 'switch_to_test_mode', 'switch_to_live_mode']
    
    def enable_gateways(self, request, queryset):
        updated = queryset.update(is_active=True)
        self.message_user(request, f'{updated} gateways were enabled.')
    enable_gateways.short_description = "Enable selected gateways"
    
    def disable_gateways(self, request, queryset):
        updated = queryset.update(is_active=False)
        self.message_user(request, f'{updated} gateways were disabled.')
    disable_gateways.short_description = "Disable selected gateways"
    
    def switch_to_test_mode(self, request, queryset):
        updated = queryset.update(is_test_mode=True)
        self.message_user(request, f'{updated} gateways switched to test mode.')
    switch_to_test_mode.short_description = "Switch to test mode"
    
    def switch_to_live_mode(self, request, queryset):
        updated = queryset.update(is_test_mode=False)
        self.message_user(request, f'{updated} gateways switched to live mode.')
    switch_to_live_mode.short_description = "Switch to live mode"


@admin.register(Payment)
class PaymentAdmin(admin.ModelAdmin):
    """Payment admin with platform support"""
    
    list_display = [
        'transaction_id', 
        'user_email', 
        'platform_display', 
        'amount_display', 
        'payment_method', 
        'status_display', 
        'invoice_number',
        'bcc_sent_indicator',  # ✅ NEW: Shows if BCC was sent
        'created_at'
    ]
    list_filter = ['platform', 'status', 'payment_method', 'currency', 'created_at']
    search_fields = [
        'transaction_id', 'invoice_number', 'gateway_payment_id',
        'user__email', 'user__first_name', 'user__last_name'
    ]
    readonly_fields = [
        'transaction_id', 'platform', 'invoice_number', 
        'created_at', 'updated_at', 'completed_at',
        'bcc_recipients_display'  # ✅ NEW: Show BCC recipients
    ]
    date_hierarchy = 'created_at'
    
    fieldsets = (
        ('Payment Information', {
            'fields': ('user', 'platform', 'transaction_id', 'invoice_number')
        }),
        ('Amount & Currency', {
            'fields': ('amount', 'currency', 'payment_method')
        }),
        ('Gateway Details', {
            'fields': ('gateway_payment_id', 'gateway_order_id', 'status', 'failure_reason')
        }),
        ('Notification Details', {  # ✅ NEW SECTION
            'fields': ('bcc_recipients_display',),
            'classes': ('collapse',),
            'description': 'BCC recipients for payment confirmation emails'
        }),
        ('Timestamps', {
            'fields': ('created_at', 'completed_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )
    
    def user_email(self, obj):
        return obj.user.email
    user_email.short_description = 'User'
    user_email.admin_order_field = 'user__email'
    
    def platform_display(self, obj):
        """Display platform name"""
        return obj.platform.name if obj.platform else "No Platform"
    platform_display.short_description = 'Platform'
    platform_display.admin_order_field = 'platform__name'
    
    def amount_display(self, obj):
        """Display formatted amount with currency"""
        return f"{obj.currency} {obj.amount}"
    amount_display.short_description = 'Amount'
    amount_display.admin_order_field = 'amount'
    
    def status_display(self, obj):
        """Display colored status"""
        colors = {
            'pending': 'orange',
            'completed': 'green',
            'failed': 'red',
            'refunded': 'blue',
            'cancelled': 'gray',
        }
        color = colors.get(obj.status, 'black')
        return format_html(
            '<span style="color: {}; font-weight: bold;">{}</span>',
            color,
            obj.get_status_display()
        )
    status_display.short_description = 'Status'
    status_display.admin_order_field = 'status'
    
    # ✅ NEW: Show if BCC was sent
    def bcc_sent_indicator(self, obj):
        """Show if payment confirmation was BCC'd to admin"""
        if obj.status == 'completed' and obj.platform:
            bcc_emails = obj.platform.get_admin_emails_for_bcc()
            if bcc_emails:
                return format_html(
                    '<span style="color: green;" title="BCC: {}">📧 ✓</span>',
                    ', '.join(bcc_emails)
                )
        return format_html('<span style="color: gray;">—</span>')
    bcc_sent_indicator.short_description = 'BCC'
    
    # ✅ NEW: Show BCC recipients in detail view
    def bcc_recipients_display(self, obj):
        """Display BCC recipients for this payment"""
        if not obj.platform:
            return format_html('<span style="color: gray;">No platform configured</span>')
        
        bcc_emails = obj.platform.get_admin_emails_for_bcc()
        
        if bcc_emails:
            email_list = '<br>'.join([
                f'<span style="color: green;">✓ {email}</span>' 
                for email in bcc_emails
            ])
            return format_html(
                '<div style="padding: 10px; background: #f0f9ff; border: 1px solid #bae6fd; border-radius: 4px;">'
                '<strong>Payment confirmation BCC sent to:</strong><br>{}</div>',
                email_list
            )
        else:
            return format_html(
                '<div style="padding: 10px; background: #fff7ed; border: 1px solid #fed7aa; border-radius: 4px;">'
                '<strong>⚠️ No BCC configured</strong><br>'
                'Set <code>contact_email</code> or <code>support_email</code> in Platform settings'
                '</div>'
            )
    bcc_recipients_display.short_description = 'BCC Recipients'
    
    def get_queryset(self, request):
        """Optimize queryset"""
        qs = super().get_queryset(request)
        return qs.select_related('user', 'platform')


@admin.register(PaymentWebinar)
class PaymentWebinarAdmin(admin.ModelAdmin):
    """Payment-Webinar relationship admin"""
    
    list_display = ['payment_transaction', 'webinar_title', 'amount', 'access_type', 'created_at']
    list_filter = ['access_type', 'created_at']
    search_fields = [
        'payment__transaction_id', 'webinar__title'
    ]
    readonly_fields = ['created_at']
    
    def payment_transaction(self, obj):
        return obj.payment.transaction_id
    payment_transaction.short_description = 'Transaction ID'
    
    def webinar_title(self, obj):
        return obj.webinar.title
    webinar_title.short_description = 'Webinar'
    
    def get_queryset(self, request):
        """Optimize queryset"""
        qs = super().get_queryset(request)
        return qs.select_related('payment', 'payment__user', 'webinar')


@admin.register(RefundRequest)
class RefundRequestAdmin(admin.ModelAdmin):
    """Refund request admin"""
    
    list_display = [
        'id', 'payment_transaction', 'user_email', 
        'refund_amount', 'status_display', 'requested_at'
    ]
    list_filter = ['status', 'requested_at', 'processed_at']
    search_fields = [
        'payment__transaction_id', 'payment__user__email',
        'gateway_refund_id'
    ]
    readonly_fields = ['requested_at', 'processed_at']
    
    fieldsets = (
        ('Refund Information', {
            'fields': ('payment', 'refund_amount', 'reason')
        }),
        ('Status & Processing', {
            'fields': ('status', 'admin_notes', 'gateway_refund_id', 'processed_by')
        }),
        ('Timestamps', {
            'fields': ('requested_at', 'processed_at')
        }),
    )
    
    def payment_transaction(self, obj):
        return obj.payment.transaction_id
    payment_transaction.short_description = 'Transaction ID'
    
    def user_email(self, obj):
        return obj.payment.user.email
    user_email.short_description = 'User'
    
    def status_display(self, obj):
        """Display colored status"""
        colors = {
            'pending': 'orange',
            'approved': 'blue',
            'rejected': 'red',
            'processed': 'green',
        }
        color = colors.get(obj.status, 'black')
        return format_html(
            '<span style="color: {}; font-weight: bold;">{}</span>',
            color,
            obj.get_status_display()
        )
    status_display.short_description = 'Status'
    
    def get_queryset(self, request):
        """Optimize queryset"""
        qs = super().get_queryset(request)
        return qs.select_related('payment', 'payment__user', 'payment__platform', 'processed_by')
