from rest_framework import serializers
from decimal import Decimal
from django.contrib.auth import get_user_model
from .models import Payment, PaymentWebinar, RefundRequest, PaymentGateway
from apps.webinars.models import Webinar

User = get_user_model()


# ============================================================================
# SECTION 1: NESTED & HELPER SERIALIZERS
# ============================================================================

class PaymentWebinarSerializer(serializers.ModelSerializer):
    """Serializer for payment-webinar relationship with webinar code"""
    
    webinar_title = serializers.CharField(source='webinar.title', read_only=True)
    webinar_id = serializers.IntegerField(source='webinar.id', read_only=True)
    webinar_code = serializers.CharField(source='webinar.webinar_id', read_only=True)  # ✅ ADDED
    webinar_slug = serializers.CharField(source='webinar.slug', read_only=True, allow_null=True)
    webinar_type = serializers.CharField(source='webinar.webinar_type', read_only=True)
    scheduled_date = serializers.DateTimeField(source='webinar.scheduled_date', read_only=True, allow_null=True)
    duration = serializers.IntegerField(source='webinar.duration', read_only=True, allow_null=True)
    instructor_name = serializers.SerializerMethodField()
    instructor_id = serializers.SerializerMethodField()
    category = serializers.SerializerMethodField()
    image_url = serializers.SerializerMethodField()
    
    class Meta:
        model = PaymentWebinar
        fields = [
            'id',
            'webinar_id',          # Webinar primary key
            'webinar_code',        # ✅ NEW: Webinar code (webinar_id field)
            'webinar_title',
            'webinar_slug',
            'webinar_type',
            'access_type',
            'amount',
            'scheduled_date',
            'duration',
            'instructor_name',
            'instructor_id',
            'category',
            'image_url',
            'created_at'
        ]
    
    def get_instructor_name(self, obj):
        if obj.webinar.speaker and obj.webinar.speaker.user:
            return obj.webinar.speaker.user.get_full_name()
        return 'TBA'
    
    def get_instructor_id(self, obj):
        if obj.webinar.speaker:
            return obj.webinar.speaker.id
        return None
    
    def get_category(self, obj):
        if obj.webinar.category:
            return {
                'id': obj.webinar.category.id,
                'name': obj.webinar.category.name,
                # 'slug': obj.webinar.category.slug
            }
        return None
    
    def get_image_url(self, obj):
        """Get absolute URL for cover image"""
        if obj.webinar.cover_image:
            request = self.context.get('request')
            if request:
                return request.build_absolute_uri(obj.webinar.cover_image.url)
        return None

class UserDetailSerializer(serializers.ModelSerializer):
    """Simplified user serializer for payment listings"""
    full_name = serializers.SerializerMethodField()
    
    class Meta:
        model = User
        fields = ['id', 'email', 'full_name', 'username']
    
    def get_full_name(self, obj):
        return obj.get_full_name() or obj.email


class WebinarDetailSerializer(serializers.ModelSerializer):
    """Webinar serializer for payment details"""
    instructor = serializers.SerializerMethodField()
    
    class Meta:
        model = Webinar
        fields = ['id', 'webinar_id', 'title', 'instructor']
    
    def get_instructor(self, obj):
        if obj.speaker and obj.speaker.user:
            return obj.speaker.user.get_full_name()
        return 'TBA'


# ============================================================================
# SECTION 2: MAIN PAYMENT SERIALIZERS
# ============================================================================

class PaymentSerializer(serializers.ModelSerializer):
    """Main payment serializer with platform info"""
    
    payment_webinars = PaymentWebinarSerializer(many=True, read_only=True)
    user_email = serializers.CharField(source='user.email', read_only=True)
    user_name = serializers.CharField(source='user.get_full_name', read_only=True)
    invoice_display_number = serializers.SerializerMethodField()
    platform_info = serializers.SerializerMethodField()
    status_display = serializers.CharField(source='get_status_display', read_only=True)
    payment_method_display = serializers.CharField(source='get_payment_method_display', read_only=True)
    
    class Meta:
        model = Payment
        fields = [
            'id', 'user_email', 'user_name', 'amount', 'currency', 'status', 
            'status_display', 'payment_method', 'payment_method_display',
            'transaction_id', 'invoice_number', 'invoice_display_number',
            'gateway_payment_id', 'gateway_order_id', 'platform_info',
            'failure_reason', 'created_at', 'completed_at', 'updated_at',
            'payment_webinars'
        ]
        read_only_fields = [
            'transaction_id', 'platform', 'invoice_number', 
            'created_at', 'completed_at', 'updated_at'
        ]
    
    def get_platform_info(self, obj):
        """Get platform information"""
        if obj.platform:
            return {
                'id': obj.platform.id,
                'platform_id': obj.platform.platform_id,
                'name': obj.platform.name
            }
        return None
    
    def get_invoice_display_number(self, obj):
        if obj.invoice_number:
            return obj.invoice_number
        return f"PENDING-{obj.id}"


class PaymentListSerializer(serializers.ModelSerializer):
    """Lightweight serializer for payment listings (optimized for admin dashboard tables)"""
    user_email = serializers.CharField(source='user.email', read_only=True)
    user_name = serializers.SerializerMethodField()
    status_display = serializers.CharField(source='get_status_display', read_only=True)
    payment_method_display = serializers.CharField(source='get_payment_method_display', read_only=True)
    invoice_display_number = serializers.SerializerMethodField()
    platform_info = serializers.SerializerMethodField()
    payment_webinars = PaymentWebinarSerializer(many=True, read_only=True)
    
    class Meta:
        model = Payment
        fields = [
            'id', 'transaction_id', 'user_email', 'user_name', 'amount', 'currency',
            'status', 'status_display', 'payment_method', 'payment_method_display',
            'invoice_number', 'invoice_display_number', 'gateway_payment_id',
            'gateway_order_id', 'platform_info', 'failure_reason', 'created_at',
            'completed_at', 'updated_at', 'payment_webinars'
        ]
    
    def get_user_name(self, obj):
        return obj.user.get_full_name() or obj.user.email
    
    def get_invoice_display_number(self, obj):
        if obj.invoice_number:
            return obj.invoice_number
        return f"PENDING-{obj.id}"
    
    def get_platform_info(self, obj):
        """Get platform information"""
        if obj.platform:
            return {
                'id': obj.platform.id,
                'platform_id': obj.platform.platform_id,
                'name': obj.platform.name
            }
        return None


class AdminPaymentDetailSerializer(serializers.ModelSerializer):
    """Admin detailed payment view with all metadata"""
    
    user_detail = UserDetailSerializer(source='user', read_only=True)
    payment_webinars = PaymentWebinarSerializer(many=True, read_only=True)
    status_display = serializers.CharField(source='get_status_display', read_only=True)
    payment_method_display = serializers.CharField(source='get_payment_method_display', read_only=True)
    platform_info = serializers.SerializerMethodField()
    invoice_display_number = serializers.SerializerMethodField()
    
    class Meta:
        model = Payment
        fields = [
            'id', 'transaction_id', 'user_detail', 'amount', 'currency',
            'status', 'status_display', 'payment_method', 'payment_method_display',
            'gateway_payment_id', 'gateway_order_id', 'gateway_response',
            'payment_webinars', 'invoice_number', 'invoice_display_number',
            'failure_reason', 'created_at', 'completed_at', 'updated_at', 'platform_info'
        ]
        read_only_fields = [
            'transaction_id', 'created_at', 'completed_at', 'updated_at'
        ]
    
    def get_platform_info(self, obj):
        """Get platform information"""
        if obj.platform:
            return {
                'id': obj.platform.id,
                'platform_id': obj.platform.platform_id,
                'name': obj.platform.name
            }
        return None
    
    def get_invoice_display_number(self, obj):
        if obj.invoice_number:
            return obj.invoice_number
        return f"PENDING-{obj.id}"


class PaymentCreateSerializer(serializers.ModelSerializer):
    """Serializer for creating payments"""
    
    webinar_ids = serializers.ListField(
        child=serializers.IntegerField(),
        write_only=True,
        help_text="List of webinar IDs to purchase"
    )
    
    class Meta:
        model = Payment
        fields = ['payment_method', 'currency', 'webinar_ids']
    
    def validate_payment_method(self, value):
        """Validate payment method is active"""
        try:
            gateway = PaymentGateway.objects.get(gateway_id=value, is_active=True)
            if not gateway.is_configured and not gateway.is_test_mode:
                raise serializers.ValidationError(
                    f"{gateway.display_name} is not properly configured"
                )
        except PaymentGateway.DoesNotExist:
            raise serializers.ValidationError(
                f"Payment method '{value}' is not available"
            )
        
        return value
    
    def validate_webinar_ids(self, value):
        """Validate webinar IDs exist"""
        if not value or len(value) == 0:
            raise serializers.ValidationError("At least one webinar ID is required")
        
        # Check if webinars exist
        webinars = Webinar.objects.filter(id__in=value)
        if len(webinars) != len(value):
            existing_ids = set(w.id for w in webinars)
            missing_ids = set(value) - existing_ids
            raise serializers.ValidationError(
                f"Webinars not found: {list(missing_ids)}"
            )
        
        return value


# ============================================================================
# SECTION 3: REFUND SERIALIZERS
# ============================================================================

class RefundRequestSerializer(serializers.ModelSerializer):
    """Serializer for refund requests with full details"""
    
    payment_transaction_id = serializers.CharField(source='payment.transaction_id', read_only=True)
    payment_amount = serializers.DecimalField(
        source='payment.amount',
        max_digits=10,
        decimal_places=2,
        read_only=True
    )
    user_email = serializers.CharField(source='payment.user.email', read_only=True)
    status_display = serializers.CharField(source='get_status_display', read_only=True)
    processed_by_name = serializers.CharField(
        source='processed_by.get_full_name',
        read_only=True,
        allow_null=True
    )
    
    class Meta:
        model = RefundRequest
        fields = [
            'id', 'payment_transaction_id', 'payment_amount', 
            'user_email', 'reason', 'admin_notes',
            'status', 'status_display', 'refund_amount', 
            'gateway_refund_id', 'requested_at', 'processed_at',
            'processed_by_name', 'processed_by'
        ]
        read_only_fields = [
            'status', 'admin_notes', 'gateway_refund_id',
            'requested_at', 'processed_at', 'processed_by'
        ]


class RefundRequestCreateSerializer(serializers.ModelSerializer):
    """Serializer for creating refund requests"""
    
    class Meta:
        model = RefundRequest
        fields = ['payment', 'reason', 'refund_amount']
    
    def validate_payment(self, value):
        """Validate payment is eligible for refund"""
        # Check if payment is completed
        if value.status != 'completed':
            raise serializers.ValidationError(
                "Only completed payments can be refunded"
            )
        
        # Check if already refunded
        if value.status == 'refunded':
            raise serializers.ValidationError(
                "This payment has already been refunded"
            )
        
        # Check if refund request already exists
        if hasattr(value, 'refund_request'):
            raise serializers.ValidationError(
                "A refund request already exists for this payment"
            )
        
        # Check if payment belongs to current user
        request = self.context.get('request')
        if request and value.user != request.user:
            raise serializers.ValidationError(
                "You can only request refunds for your own payments"
            )
        
        return value
    
    def validate_refund_amount(self, value):
        """Validate refund amount"""
        payment = self.initial_data.get('payment')
        
        if payment and value > payment.amount:
            raise serializers.ValidationError(
                "Refund amount cannot exceed payment amount"
            )
        
        if value <= 0:
            raise serializers.ValidationError(
                "Refund amount must be greater than zero"
            )
        
        return value


# ============================================================================
# SECTION 4: ANALYTICS & SUMMARY SERIALIZERS
# ============================================================================

class PaymentSummarySerializer(serializers.Serializer):
    """Serializer for payment summary/statistics"""
    
    total_payments = serializers.IntegerField()
    total_revenue = serializers.DecimalField(max_digits=12, decimal_places=2)
    completed_payments = serializers.IntegerField()
    pending_payments = serializers.IntegerField()
    failed_payments = serializers.IntegerField()
    refunded_amount = serializers.DecimalField(max_digits=12, decimal_places=2)
    platform = serializers.DictField(required=False)


class OverviewStatsSerializer(serializers.Serializer):
    """Serializer for overview statistics"""
    
    revenue = serializers.DecimalField(max_digits=12, decimal_places=2)
    transactions = serializers.IntegerField()
    average_transaction = serializers.DecimalField(max_digits=12, decimal_places=2)


class PaymentOverviewSerializer(serializers.Serializer):
    """Serializer for payment overview (today/week/month/total)"""
    
    today = OverviewStatsSerializer()
    this_week = OverviewStatsSerializer()
    this_month = OverviewStatsSerializer()
    total = OverviewStatsSerializer()


class PaymentMethodBreakdownSerializer(serializers.Serializer):
    """Serializer for payment method breakdown"""
    
    method = serializers.CharField()
    method_id = serializers.CharField()
    percentage = serializers.FloatField()
    amount = serializers.DecimalField(max_digits=12, decimal_places=2)
    transactions = serializers.IntegerField()


class RevenueAnalyticsSerializer(serializers.Serializer):
    """Complete revenue analytics"""
    
    payment_methods = PaymentMethodBreakdownSerializer(many=True)
    total_refunded_transactions = serializers.IntegerField()
    total_completed_transactions = serializers.IntegerField()
    refund_rate = serializers.FloatField()
    average_transaction_value = serializers.DecimalField(max_digits=12, decimal_places=2)
    total_revenue = serializers.DecimalField(max_digits=12, decimal_places=2)
    platform_commission_percentage = serializers.IntegerField()
    instructor_payout_percentage = serializers.IntegerField()


class RefundStatisticsSerializer(serializers.Serializer):
    """Refund statistics"""
    
    total_completed_payments = serializers.IntegerField()
    total_refunded_payments = serializers.IntegerField()
    refund_rate = serializers.FloatField()
    total_refunded_amount = serializers.DecimalField(max_digits=12, decimal_places=2)
    pending_refund_requests = serializers.IntegerField()
    approved_refund_requests = serializers.IntegerField()
    processed_refund_requests = serializers.IntegerField()
    rejected_refund_requests = serializers.IntegerField()


class PaginatedPaymentSerializer(serializers.Serializer):
    """Paginated payment results"""
    
    results = PaymentListSerializer(many=True)
    count = serializers.IntegerField()
    page = serializers.IntegerField()
    page_size = serializers.IntegerField()
    total_pages = serializers.IntegerField()


# ============================================================================
# SECTION 5: PAYMENT GATEWAY SERIALIZERS
# ============================================================================

class PaymentGatewaySerializer(serializers.ModelSerializer):
    """Payment gateway serializer"""
    
    status = serializers.SerializerMethodField()
    mode = serializers.SerializerMethodField()
    status_display = serializers.SerializerMethodField()
    
    class Meta:
        model = PaymentGateway
        fields = [
            'id', 'gateway_id', 'display_name', 'description',
            'is_active', 'is_test_mode', 'logo_url', 'display_order',
            'supports_refunds', 'supports_partial_refunds', 'supports_webhooks',
            'supported_currencies', 'min_amount', 'max_amount',
            'processing_time', 'processing_fee_percentage',
            'is_configured', 'status', 'mode', 'status_display'
        ]
        read_only_fields = ['is_configured']
    
    def get_status(self, obj):
        return "🟢 Active" if obj.is_active else "🔴 Inactive"
    
    def get_mode(self, obj):
        return "🧪 Test" if obj.is_test_mode else "🚀 Live"
    
    def get_status_display(self, obj):
        return f"{self.get_status(obj)} {self.get_mode(obj)}"