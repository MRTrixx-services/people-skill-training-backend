
from rest_framework import generics, status, permissions
from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response
from django.shortcuts import get_object_or_404
from django.utils import timezone
from django.conf import settings
from django.db import transaction
from apps.webinars.models import Webinar
from apps.users.permissions import IsInstructorOrAdmin, IsAdminUser

from apps.enrollments.models import Enrollment
from .models import Payment, RefundRequest, PaymentGateway, PaymentWebinar
from .serializers import (
    PaymentSerializer, PaymentCreateSerializer,
    RefundRequestSerializer, RefundRequestCreateSerializer,
    PaymentListSerializer, AdminPaymentDetailSerializer,
    PaymentOverviewSerializer, RevenueAnalyticsSerializer,
    RefundStatisticsSerializer, PaginatedPaymentSerializer
)
import uuid
import razorpay
from django.template.loader import render_to_string
from django.http import HttpResponse
from weasyprint import HTML
from decimal import Decimal
from apps.notifications.email_service import send_payment_confirmation_email_task
import logging
from .gateway_manager import payment_gateway_manager
from .gateways.base import PaymentGatewayError, PaymentVerificationError, RefundError
from django.db.models import Sum, Count, Q, F, Avg, DecimalField
from rest_framework.pagination import PageNumberPagination  # ADD THIS IMPORT

logger = logging.getLogger(__name__)

def generate_slug(title):
    import re
    slug = title.lower()
    slug = re.sub(r'[^a-z0-9\\s-]', '', slug)  # Remove special characters
    slug = re.sub(r'\\s+', '-', slug)  # Replace spaces with hyphens
    slug = re.sub(r'-+', '-', slug)  # Replace multiple hyphens with single
    return slug.strip('-')

# ============================================================================
# ADMIN ANALYTICS VIEWS
# ============================================================================
class AdminPaymentDetailView(generics.RetrieveAPIView):
    permission_classes = [permissions.IsAuthenticated, IsAdminUser]
    serializer_class = PaymentListSerializer  # Or create a detailed serializer
    queryset = Payment.objects.select_related('user', 'platform').prefetch_related('payment_webinars__webinar')
    
class PaymentOverviewView(generics.RetrieveAPIView):
    """Payment overview statistics for admin dashboard"""
    permission_classes = [permissions.IsAuthenticated, IsAdminUser]
    serializer_class = PaymentOverviewSerializer
    
    def get_object(self):
        platform = getattr(self.request, 'platform', None)
        
        # Base queryset
        payments = Payment.objects.all()
        if platform:
            payments = payments.filter(platform=platform)
        
        # Today's stats
        today_start = timezone.now().replace(hour=0, minute=0, second=0, microsecond=0)
        today_payments = payments.filter(created_at__gte=today_start, status='completed')
        today_revenue = today_payments.aggregate(total=Sum('amount'))['total'] or Decimal('0.00')
        today_transactions = today_payments.count()
        
        # This week stats
        week_start = today_start - timezone.timedelta(days=today_start.weekday())
        week_payments = payments.filter(created_at__gte=week_start, status='completed')
        week_revenue = week_payments.aggregate(total=Sum('amount'))['total'] or Decimal('0.00')
        week_transactions = week_payments.count()
        
        # This month stats
        month_start = today_start.replace(day=1)
        month_payments = payments.filter(created_at__gte=month_start, status='completed')
        month_revenue = month_payments.aggregate(total=Sum('amount'))['total'] or Decimal('0.00')
        month_transactions = month_payments.count()
        
        # Total stats
        total_payments = payments.filter(status='completed')
        total_revenue = total_payments.aggregate(total=Sum('amount'))['total'] or Decimal('0.00')
        total_transactions = total_payments.count()
        
        return {
            'today': {
                'revenue': today_revenue,
                'transactions': today_transactions,
                'average_transaction': today_revenue / today_transactions if today_transactions > 0 else Decimal('0.00')
            },
            'this_week': {
                'revenue': week_revenue,
                'transactions': week_transactions,
                'average_transaction': week_revenue / week_transactions if week_transactions > 0 else Decimal('0.00')
            },
            'this_month': {
                'revenue': month_revenue,
                'transactions': month_transactions,
                'average_transaction': month_revenue / month_transactions if month_transactions > 0 else Decimal('0.00')
            },
            'total': {
                'revenue': total_revenue,
                'transactions': total_transactions,
                'average_transaction': total_revenue / total_transactions if total_transactions > 0 else Decimal('0.00')
            }
        }

class RevenueAnalyticsView(generics.RetrieveAPIView):
    """Detailed revenue analytics for admin dashboard"""
    permission_classes = [permissions.IsAuthenticated, IsAdminUser]
    serializer_class = RevenueAnalyticsSerializer
    
    def get_object(self):
        platform = getattr(self.request, 'platform', None)
        
        # Base queryset
        payments = Payment.objects.all()
        refund_requests = RefundRequest.objects.all()
        
        if platform:
            payments = payments.filter(platform=platform)
            refund_requests = refund_requests.filter(payment__platform=platform)
        
        # Payment method breakdown
        method_breakdown = payments.filter(status='completed').values('payment_method').annotate(
            total_amount=Sum('amount'),
            transaction_count=Count('id')
        ).order_by('-total_amount')
        
        total_revenue = payments.filter(status='completed').aggregate(
            total=Sum('amount')
        )['total'] or Decimal('0.00')
        
        payment_methods = []
        for method in method_breakdown:
            percentage = (method['total_amount'] / total_revenue * 100) if total_revenue > 0 else 0
            payment_methods.append({
                'method': dict(Payment.PAYMENT_METHOD_CHOICES).get(method['payment_method'], method['payment_method']),
                'method_id': method['payment_method'],
                'percentage': float(percentage),
                'amount': method['total_amount'],
                'transactions': method['transaction_count']
            })
        
        # FIXED: Use RefundRequest for refund counts instead of Payment
        total_refunded = refund_requests.filter(status__in=['processed', 'approved']).count()
        total_completed = payments.filter(status='completed').count()
        refund_rate = (total_refunded / total_completed * 100) if total_completed > 0 else 0
        
        # Average transaction value
        avg_transaction = payments.filter(status='completed').aggregate(
            avg=Avg('amount')
        )['avg'] or Decimal('0.00')
        
        return {
            'payment_methods': payment_methods,
            'total_refunded_transactions': total_refunded,
            'total_completed_transactions': total_completed,
            'refund_rate': float(refund_rate),
            'average_transaction_value': avg_transaction,
            'total_revenue': total_revenue,
            'platform_commission_percentage': 20,
            'instructor_payout_percentage': 80,
        }

class RefundStatisticsView(generics.RetrieveAPIView):
    """Refund statistics for admin dashboard"""
    permission_classes = [permissions.IsAuthenticated, IsAdminUser]
    serializer_class = RefundStatisticsSerializer
    
    def get_object(self):
        platform = getattr(self.request, 'platform', None)
        
        # Base queryset
        payments = Payment.objects.all()
        refund_requests = RefundRequest.objects.all()
        
        if platform:
            payments = payments.filter(platform=platform)
            refund_requests = refund_requests.filter(payment__platform=platform)
        
        # Payment statistics
        total_completed_payments = payments.filter(status='completed').count()
        total_refunded_payments = payments.filter(status='refunded').count()
        
        # FIXED: Calculate total refunded amount from RefundRequest instead of Payment
        total_refunded_amount = refund_requests.filter(status__in=['processed', 'approved']).aggregate(
            total=Sum('refund_amount')
        )['total'] or Decimal('0.00')
        
        # Refund rate
        refund_rate = (total_refunded_payments / total_completed_payments * 100) if total_completed_payments > 0 else 0
        
        # Refund request status counts
        refund_status_counts = refund_requests.aggregate(
            pending=Count('id', filter=Q(status='pending')),
            approved=Count('id', filter=Q(status='approved')),
            processed=Count('id', filter=Q(status='processed')),
            rejected=Count('id', filter=Q(status='rejected'))
        )
        
        return {
            'total_completed_payments': total_completed_payments,
            'total_refunded_payments': total_refunded_payments,
            'refund_rate': float(refund_rate),
            'total_refunded_amount': total_refunded_amount,
            'pending_refund_requests': refund_status_counts['pending'],
            'approved_refund_requests': refund_status_counts['approved'],
            'processed_refund_requests': refund_status_counts['processed'],
            'rejected_refund_requests': refund_status_counts['rejected'],
        }

class AdminPaymentListView(generics.ListAPIView):
    """Admin payment list with pagination and filtering"""
    permission_classes = [permissions.IsAuthenticated, IsAdminUser]
    serializer_class = PaymentListSerializer
    filterset_fields = ['status', 'payment_method']
    search_fields = ['transaction_id', 'user__email', 'invoice_number']
    ordering_fields = ['created_at', 'amount', 'completed_at']
    ordering = ['-created_at']
    
    def get_queryset(self):
        platform = getattr(self.request, 'platform', None)
        queryset = Payment.objects.select_related('user', 'platform').prefetch_related('payment_webinars__webinar')
        
        if platform:
            queryset = queryset.filter(platform=platform)
        
        return queryset

# ============================================================================
# USER PAYMENT VIEWS
# ============================================================================

class PaymentListView(generics.ListAPIView):
    serializer_class = PaymentListSerializer
    permission_classes = [permissions.IsAuthenticated]
    filterset_fields = ['status', 'payment_method']
    search_fields = ['transaction_id', 'invoice_number']
    ordering_fields = ['created_at', 'amount']
    ordering = ['-created_at']
    pagination_class = PageNumberPagination  # ADD THIS

    def get_queryset(self):
        queryset = Payment.objects.filter(
            user=self.request.user
        ).select_related('user', 'platform').prefetch_related('payment_webinars__webinar')
        
        # Platform filtering
        platform = getattr(self.request, 'platform', None)
        if platform:
            queryset = queryset.filter(platform=platform)
        
        return queryset

# class PaymentDetailView(generics.RetrieveAPIView):
#     serializer_class = PaymentListSerializer  # Use same serializer for consistency
#     permission_classes = [permissions.IsAuthenticated]

#     def get_queryset(self):
#         queryset = Payment.objects.filter(
#             user=self.request.user
#         ).select_related('user', 'platform').prefetch_related('payment_webinars__webinar')
        
#         # Platform filtering
#         platform = getattr(self.request, 'platform', None)
#         if platform:
#             queryset = queryset.filter(platform=platform)
        
#         return queryset

class PaymentDetailView(generics.RetrieveAPIView):
    serializer_class = PaymentListSerializer  # Use consistent serializer
    permission_classes = [permissions.IsAuthenticated]
    lookup_field = 'invoice_number'           # Use invoice_number for lookup
    lookup_url_kwarg = 'invoice_number'       # URL kwarg name

    def get_queryset(self):
        queryset = Payment.objects.filter(
            user=self.request.user
        ).select_related('user', 'platform').prefetch_related('payment_webinars__webinar')

        platform = getattr(self.request, 'platform', None)
        if platform:
            queryset = queryset.filter(platform=platform)

        return queryset
        
@api_view(['GET'])
@permission_classes([permissions.AllowAny])
def get_available_payment_gateways(request):
  
    gateways_db = PaymentGateway.objects.filter(is_active=True).order_by('display_order')
    
    available_gateways = []
    for gateway in gateways_db:
        supported_currencies = gateway.supported_currencies or ['USD']
        if 'USD' not in supported_currencies:
            supported_currencies.insert(0, 'USD')
        
        gateway_info = {
            'id': gateway.gateway_id,
            'name': gateway.display_name,
            'description': gateway.description,
            'logo_url': gateway.logo_url,
            'supported_currencies': supported_currencies,
            'min_amount': float(gateway.min_amount),
            'max_amount': float(gateway.max_amount),
            'supports_refunds': gateway.supports_refunds,
            'supports_partial_refunds': gateway.supports_partial_refunds,
            'test_mode': gateway.is_test_mode,
            'processing_time': gateway.processing_time,
            'processing_fee': float(gateway.processing_fee_percentage),
            'features': {
                'instant_refunds': gateway.supports_refunds,
                'partial_refunds': gateway.supports_partial_refunds,
                'webhooks': gateway.supports_webhooks,
            },
            'is_configured': gateway.is_configured,
            'display_order': gateway.display_order,
            'configuration': gateway.configuration or {}
        }
        available_gateways.append(gateway_info)
    
    default_gateway = gateways_db.first()
    default_gateway_id = default_gateway.gateway_id if default_gateway else getattr(settings, 'DEFAULT_PAYMENT_GATEWAY', 'razorpay')
    
    return Response({
        'success': True,
        'gateways': available_gateways,
        'default_gateway': default_gateway_id,
        'default_currency': 'USD',
        'supported_currencies': ['USD', 'EUR', 'GBP', 'INR', 'CAD', 'AUD'],
        'currency_info': {
            'USD': {'symbol': '$', 'name': 'US Dollar', 'decimals': 2},
            'EUR': {'symbol': '€', 'name': 'Euro', 'decimals': 2},
            'GBP': {'symbol': '£', 'name': 'British Pound', 'decimals': 2},
            'INR': {'symbol': '₹', 'name': 'Indian Rupee', 'decimals': 2},
            'CAD': {'symbol': 'C$', 'name': 'Canadian Dollar', 'decimals': 2},
            'AUD': {'symbol': 'A$', 'name': 'Australian Dollar', 'decimals': 2}
        }
    })


@api_view(['POST'])
@permission_classes([permissions.IsAuthenticated])
def checkout(request):
    try:
        user = request.user
        platform = getattr(request, 'platform', None)
        
        webinar_data = request.data.get('webinars', [])
        payment_method = request.data.get('payment_method', 'razorpay')
        currency = request.data.get('currency', 'USD')
        
        if not webinar_data:
            logger.warning(f"⚠️ Checkout attempted with no webinars by {user.email}")
            return Response({
                'success': False,
                'error': 'No webinars provided'
            }, status=status.HTTP_400_BAD_REQUEST)
        
        # Calculate total amount
        total_amount = Decimal('0.00')
        webinar_items = []
        
        for item in webinar_data:
            webinar_id_str = item.get('webinar_id')
            webinar_pk = item.get('id')
            
            access_type = item.get('access_type', 'recorded_single')
            price = Decimal(str(item.get('price', 0)))
            
            if price <= 0:
                logger.error(f"❌ Invalid price for webinar {webinar_id_str or webinar_pk}: {price}")
                return Response({
                    'success': False,
                    'error': f'Invalid price for webinar {webinar_id_str or webinar_pk}'
                }, status=status.HTTP_400_BAD_REQUEST)
            
            try:
                webinar = None
                
                # Strategy 1: Try webinar_id (string like "WEB2510016")
                if webinar_id_str and isinstance(webinar_id_str, str) and not webinar_id_str.isdigit():
                    try:
                        webinar = Webinar.objects.get(webinar_id=webinar_id_str)
                        logger.debug(f"✅ Found webinar by webinar_id: {webinar.webinar_id}")
                    except Webinar.DoesNotExist:
                        pass
                
                # Strategy 2: Try primary key (integer)
                if not webinar:
                    lookup_id = None
                    if webinar_id_str and str(webinar_id_str).isdigit():
                        lookup_id = int(webinar_id_str)
                    elif webinar_pk:
                        lookup_id = webinar_pk
                    
                    if lookup_id:
                        try:
                            webinar = Webinar.objects.get(id=lookup_id)
                            logger.debug(f"✅ Found webinar by ID: {webinar.id} ({webinar.webinar_id})")
                        except Webinar.DoesNotExist:
                            pass
                
                if not webinar:
                    raise Webinar.DoesNotExist
                
                webinar_items.append({
                    'webinar': webinar,
                    'access_type': access_type,
                    'price': price
                })
                total_amount += price
                
            except Webinar.DoesNotExist:
                logger.error(f"❌ Webinar not found - webinar_id: {webinar_id_str}, id: {webinar_pk}")
                return Response({
                    'success': False,
                    'error': f'Webinar not found (ID: {webinar_id_str or webinar_pk})'
                }, status=status.HTTP_404_NOT_FOUND)
        
        logger.info(f"💰 Checkout request from {user.email}:")
        logger.info(f"   - Items: {len(webinar_items)}")
        logger.info(f"   - Total: {currency} {total_amount}")
        logger.info(f"   - Method: {payment_method}")
        logger.info(f"   - Platform: {platform.platform_id if platform else 'default'}")
        
        # ✅ CHECK FOR EXISTING PENDING PAYMENT
        time_window = timezone.now() - timezone.timedelta(hours=24)
        
        existing_payment = Payment.objects.filter(
            user=user,
            platform=platform,
            status='pending',
            amount=total_amount,
            currency=currency,
            payment_method=payment_method,
            created_at__gte=time_window
        ).order_by('-created_at').first()
        
        # Check if existing payment has same webinars
        if existing_payment:
            logger.info(f"🔍 Found pending payment: {existing_payment.transaction_id}")
            logger.info(f"   - Created: {existing_payment.created_at}")
            logger.info(f"   - Amount: {existing_payment.amount}")
            logger.info(f"   - Gateway Order ID: {existing_payment.gateway_order_id}")
            
            existing_webinar_pks = set(
                existing_payment.payment_webinars.values_list('webinar__id', flat=True)
            )
            requested_webinar_pks = set(item['webinar'].id for item in webinar_items)
            
            logger.info(f"   - Existing webinar IDs: {sorted(existing_webinar_pks)}")
            logger.info(f"   - Requested webinar IDs: {sorted(requested_webinar_pks)}")
            
            if existing_webinar_pks == requested_webinar_pks:
                logger.info(f"♻️ ✅ REUSING existing pending payment: {existing_payment.transaction_id}")
                
                # Verify gateway order is still valid
                if not existing_payment.gateway_order_id:
                    logger.warning(f"⚠️ Existing payment has no gateway_order_id, creating new gateway order")
                    
                    gateway = payment_gateway_manager.get_gateway(payment_method)
                    if not gateway:
                        return Response({
                            'success': False,
                            'error': f'Payment gateway {payment_method} not available'
                        }, status=status.HTTP_400_BAD_REQUEST)
                    
                    order_data = {
                        'user_id': user.id,
                        'user_email': user.email,
                        'user_name': user.get_full_name() or user.email,
                        'platform_id': platform.platform_id if platform else 'default',
                        'transaction_id': existing_payment.transaction_id,
                        'notes': {
                            'transaction_id': existing_payment.transaction_id,
                            'user_email': user.email,
                            'webinar_count': len(webinar_items),
                            'reused_payment': True
                        }
                    }
                    
                    gateway_response = gateway.create_order(total_amount, currency, order_data)
                    
                    existing_payment.gateway_order_id = gateway_response.get('order_id')
                    existing_payment.gateway_response = gateway_response
                    existing_payment.save(update_fields=['gateway_order_id', 'gateway_response'])
                    
                    logger.info(f"📦 Created new gateway order for existing payment: {existing_payment.gateway_order_id}")
                
                gateway = payment_gateway_manager.get_gateway(payment_method)
                if not gateway:
                    return Response({
                        'success': False,
                        'error': f'Payment gateway {payment_method} not available'
                    }, status=status.HTTP_400_BAD_REQUEST)
                
                # ✅ BUILD RESPONSE WITH CLIENT_SECRET
                response_data = {
                    'success': True,
                    'message': 'Resuming existing payment',
                    'payment': PaymentSerializer(existing_payment).data,
                    'gateway_order_id': existing_payment.gateway_order_id,
                    'gateway_config': gateway.get_client_config()
                }
                
                # ✅ ADD CLIENT_SECRET FOR STRIPE (RESUMED PAYMENT)
                if payment_method == 'stripe' and existing_payment.gateway_response:
                    client_secret = existing_payment.gateway_response.get('client_secret')
                    if client_secret:
                        response_data['client_secret'] = client_secret
                        logger.info(f"✅ Including existing Stripe client_secret in response")
                    else:
                        logger.warning(f"⚠️ No client_secret found in existing payment gateway_response")
                
                return Response(response_data)
            else:
                logger.info(f"⚠️ Webinar IDs don't match - creating new payment")
                logger.info(f"   - Missing from request: {existing_webinar_pks - requested_webinar_pks}")
                logger.info(f"   - New in request: {requested_webinar_pks - existing_webinar_pks}")
        else:
            logger.info(f"🆕 No existing pending payment found - creating new")
        
        # ✅ CREATE NEW PAYMENT
        with transaction.atomic():
            payment = Payment.objects.create(
                user=user,
                platform=platform,
                amount=total_amount,
                currency=currency,
                payment_method=payment_method,
                status='pending'
            )
            
            logger.info(f"✅ Created new payment: {payment.transaction_id}")
            logger.info(f"   - Payment ID: {payment.id}")
            logger.info(f"   - Amount: {currency} {total_amount}")
            
            # Create PaymentWebinar records
            for item in webinar_items:
                PaymentWebinar.objects.create(
                    payment=payment,
                    webinar=item['webinar'],
                    access_type=item['access_type'],
                    amount=item['price']
                )
                logger.debug(f"   - Added: {item['webinar'].title} ({item['access_type']}) - ${item['price']}")
            
            # Create gateway order
            try:
                gateway = payment_gateway_manager.get_gateway(payment_method)
                if not gateway:
                    raise PaymentGatewayError(f'Payment gateway {payment_method} not available')
                
                # In views.py checkout function (around line 180)
                order_data = {
                    'user_id': user.id,
                    'user_email': user.email,
                    'user_name': user.get_full_name() or user.email,
                    'platform_id': platform.platform_id if platform else 'default',
                    'transaction_id': payment.transaction_id,
                    'billing_info': request.data.get('billing_info', {}),  # ✅ ADD THIS
                    'notes': {
                        'transaction_id': payment.transaction_id,
                        'user_email': user.email,
                        'webinar_count': len(webinar_items)
                    }
                }

                logger.info(f"📤 Creating gateway order...")
                gateway_response = gateway.create_order(total_amount, currency, order_data)
                
                payment.gateway_order_id = gateway_response.get('order_id')
                payment.gateway_response = gateway_response
                payment.save(update_fields=['gateway_order_id', 'gateway_response'])
                
                logger.info(f"📦 Gateway order created successfully:")
                logger.info(f"   - Gateway Order ID: {payment.gateway_order_id}")
                logger.info(f"   - Transaction ID: {payment.transaction_id}")
                
                # ✅ BUILD RESPONSE WITH CLIENT_SECRET FOR STRIPE (NEW PAYMENT)
                response_data = {
                    'success': True,
                    'message': 'Payment initiated successfully',
                    'payment': PaymentSerializer(payment).data,
                    'gateway_order_id': payment.gateway_order_id,
                    'gateway_config': gateway.get_client_config()
                }
                
                # ✅ CRITICAL: Add client_secret for Stripe payments
                if payment_method == 'stripe' and 'client_secret' in gateway_response:
                    response_data['client_secret'] = gateway_response['client_secret']
                    logger.info(f"✅ Stripe client_secret included in response")
                    logger.info(f"   - Client Secret: {gateway_response['client_secret'][:20]}...")
                elif payment_method == 'stripe':
                    logger.error(f"❌ Stripe payment created but client_secret missing from gateway response!")
                    logger.error(f"   - Gateway response keys: {list(gateway_response.keys())}")
                
                return Response(response_data)
                
            except PaymentGatewayError as e:
                logger.error(f"❌ Gateway error: {str(e)}")
                payment.status = 'failed'
                payment.failure_reason = str(e)
                payment.save(update_fields=['status', 'failure_reason'])
                return Response({
                    'success': False,
                    'error': str(e)
                }, status=status.HTTP_400_BAD_REQUEST)
    
    except Exception as e:
        logger.error(f"❌ Checkout error: {str(e)}", exc_info=True)
        return Response({
            'success': False,
            'error': 'Payment processing failed. Please try again.'
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

# @api_view(['POST'])
# @permission_classes([permissions.IsAuthenticated])
# def verify_payment(request):
   
#     try:
#         user = request.user
#         platform = getattr(request, 'platform', None)
        
#         logger.debug(f"✅ Request authenticated for platform: {platform.name if platform else 'None'}")
        
#         payment_method = request.data.get('payment_method')
#         transaction_id = request.data.get('transaction_id')
#         payment_data = request.data.get('payment_data', {})
        
#         if not payment_method or not transaction_id:
#             return Response({
#                 'success': False,
#                 'error': 'Payment method and transaction ID are required'
#             }, status=status.HTTP_400_BAD_REQUEST)
        
#         # Get gateway
#         gateway = payment_gateway_manager.get_gateway(payment_method)
#         if not gateway:
#             logger.error(f"⚠️ Gateway not found: {payment_method}")
#             return Response({
#                 'success': False,
#                 'error': f'Payment gateway {payment_method} not configured'
#             }, status=status.HTTP_400_BAD_REQUEST)
        
#         logger.debug(f"✅ Gateway found: {payment_method}")
        
#         # Get payment record
#         payment = get_object_or_404(
#             Payment.objects.select_related('user', 'platform'),
#             transaction_id=transaction_id,
#             user=user
#         )
        
#         # Verify payment with gateway
#         logger.info(f"🔍 Verifying payment: {transaction_id}")
#         verification_result = gateway.verify_payment(payment_data)
        
#         if verification_result.get('verified'):
#             # Update payment status
#             with transaction.atomic():
#                 payment.status = 'completed'
#                 payment.gateway_payment_id = verification_result.get('payment_id', '')
#                 payment.completed_at = timezone.now()
#                 payment.save()
                
#                 logger.info(f"✅ Payment verified: {transaction_id}")
                
#                 # ✅ Create enrollments and prepare webinar details for email
#                 payment_webinars = PaymentWebinar.objects.filter(payment=payment).select_related('webinar', 'webinar__speaker')
#                 webinar_details = []
                
#                 # Get platform-specific frontend URL
#                 frontend_url = f"https://{platform.domain}" if platform and platform.domain else getattr(settings, 'DEFAULT_FRONTEND_URL', 'https://peopleskilltraining.com')
                
#                 for pw in payment_webinars:
#                     enrollment, created = Enrollment.objects.get_or_create(
#                         user=user,
#                         webinar=pw.webinar,
#                         platform=platform,
#                         defaults={
#                             'access_type': pw.access_type,
#                             'status': 'enrolled',
#                             'payment_amount': pw.amount,
#                             'payment_method': payment.payment_method,
#                             'transaction_id': payment.transaction_id,
#                         }
#                     )
                    
#                     if created:
#                         logger.info(f"✅ Created enrollment: {user.email} → {pw.webinar.title}")
#                     else:
#                         logger.info(f"ℹ️ Enrollment already exists: {user.email} → {pw.webinar.title}")
                    
#                     # ✅ Generate slug from webinar title
#                     webinar_slug = generate_slug(pw.webinar.title)
                    
#                     # ✅ Generate correct webinar URL based on type
#                     webinar_type = 'live-webinar' if pw.webinar.webinar_type == 'live' else 'recorded-webinar'
#                     webinar_url = f"{frontend_url}/{webinar_type}/{pw.webinar.webinar_id}/{webinar_slug}"
                    
#                     # ✅ Prepare webinar details for email
#                     webinar_details.append({
#                         'title': pw.webinar.title,
#                         'instructor': pw.webinar.speaker.user.get_full_name() if pw.webinar.speaker else 'TBA',
#                         'scheduled_date': pw.webinar.scheduled_date.strftime('%B %d, %Y at %I:%M %p') if pw.webinar.scheduled_date else 'On Demand',
#                         'duration': f"{pw.webinar.duration} minutes" if pw.webinar.duration else 'Self-paced',
#                         'webinar_url': webinar_url,
#                     })

#                 # ✅ Send payment confirmation email with BCC to admin
#                 try:
#                     from apps.notifications.email_service import EmailService
       
#                     # Get platform-specific email context
#                     context = EmailService.get_email_context(
#                         user=user,
#                         platform=platform,
#                         transaction_id=payment.transaction_id,
#                         payment_date=payment.completed_at.strftime('%B %d, %Y'),
#                         payment_method=payment.get_payment_method_display(),
#                         total_amount=f"{payment.amount:.2f}",
#                         currency=payment.currency,
#                         webinars=webinar_details,
#                         dashboard_url=f"{frontend_url}/attendee/enrollments",
#                         invoice_url=f"{frontend_url}/attendee/orders"
#                     )
                    
#                     # ✅ Get admin BCC list
#                     bcc_list = platform.get_admin_emails_for_bcc() if platform else []
#                     if bcc_list:
#                         logger.info(f"📧 Will send BCC copy to: {', '.join(bcc_list)}")
#                     # Send email via Brevo with BCC
#                     EmailService.send_email(
#                         subject=f'Payment Confirmed - {payment.transaction_id}',
#                         template_name='payment_confirmation',
#                         context=context,
#                         recipient_list=[user.email],
#                         platform=platform,
#                         bcc=bcc_list  # ✅ Send copy to admin
#                     )
                    
#                     logger.info(f"✅ Sent payment confirmation email to {user.email}" + 
#                                (f" with BCC to {bcc_list[0]}" if bcc_list else ""))
                    
#                 except Exception as e:
#                     logger.error(f"❌ Failed to send payment confirmation email: {str(e)}")
#                     # Don't fail the payment - email is non-critical

#             # Return success response
#             serializer = PaymentSerializer(payment)
#             return Response({
#                 'success': True,
#                 'message': 'Payment verified successfully',
#                 'payment': serializer.data
#             })
#         else:
#             # Payment verification failed
#             payment.status = 'failed'
#             payment.failure_reason = verification_result.get('message', 'Verification failed')
#             payment.save()
            
#             logger.warning(f"⚠️ Payment verification failed: {transaction_id}")
            
#             return Response({
#                 'success': False,
#                 'error': 'Payment verification failed',
#                 'details': verification_result.get('message')
#             }, status=status.HTTP_400_BAD_REQUEST)
    
#     except PaymentVerificationError as e:
#         logger.error(f"Payment verification error: {str(e)}")
#         return Response({
#             'success': False,
#             'error': str(e)
#         }, status=status.HTTP_400_BAD_REQUEST)
    
#     except Exception as e:
#         logger.error(f"Unexpected error during payment verification: {str(e)}", exc_info=True)
#         return Response({
#             'success': False,
#             'error': 'An unexpected error occurred during payment verification'
#         }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

# @api_view(['POST'])
# @permission_classes([permissions.IsAuthenticated])
# def verify_payment(request):
#     try:
#         user = request.user
#         platform = getattr(request, 'platform', None)
        
#         logger.debug(f"Request authenticated for {platform.name if platform else None}")
        
#         payment_method = request.data.get('payment_method')
#         transaction_id = request.data.get('transaction_id')
#         payment_data = request.data.get('payment_data', {})
        
#         if not payment_method or not transaction_id:
#             return Response({
#                 'success': False,
#                 'error': 'Payment method and transaction ID are required'
#             }, status=status.HTTP_400_BAD_REQUEST)
        
#         # Get gateway
#         gateway = payment_gateway_manager.get_gateway(payment_method)
#         if not gateway:
#             logger.error(f"Gateway not found: {payment_method}")
#             return Response({
#                 'success': False,
#                 'error': f'Payment gateway {payment_method} not configured'
#             }, status=status.HTTP_400_BAD_REQUEST)
        
#         logger.debug(f"Gateway found: {payment_method}")
        
#         # Get payment record
#         payment = get_object_or_404(
#             Payment.objects.select_related('user', 'platform'),
#             transaction_id=transaction_id,
#             user=user
#         )
        
#         logger.info(f"Verifying payment {transaction_id}")
        
#         # Verify payment with gateway
#         verification_result = gateway.verify_payment(payment_data)
        
#         if verification_result.get('verified'):
#             # Update payment status
          
#             with transaction.atomic():
#                 if not payment.invoice_number:
#                     payment.invoice_number = Payment.generate_unique_invoice_number(payment.platform)

#                 payment.status = 'completed'
#                 payment.gateway_payment_id = verification_result.get('payment_id', '')
#                 payment.completed_at = timezone.now()
#                 # payment.save()
#                 payment.save(update_fields=['invoice_number', 'status', 'gateway_payment_id', 'completed_at'])
        
                
#                 logger.info(f"Payment verified: {transaction_id}")
                
#                 # Create enrollments
#                 payment_webinars = PaymentWebinar.objects.filter(
#                     payment=payment
#                 ).select_related('webinar', 'webinar__speaker', 'webinar__speaker__user')
                
#                 # Get frontend URL
#                 frontend_url = f"https://www.{platform.domain}" if platform and platform.domain else getattr(settings, 'DEFAULT_FRONTEND_URL', 'https://www.peopleskilltraining.com')
                
#                 # Create enrollments and prepare webinar details
#                 webinar_details = []
#                 for pw in payment_webinars:
#                     # Create enrollment
#                     enrollment, created = Enrollment.objects.get_or_create(
#                         user=user,
#                         webinar=pw.webinar,
#                         platform=platform,
#                         defaults={
#                             'access_type': pw.access_type,
#                             'status': 'enrolled',
#                             'payment_amount': pw.amount,
#                             'payment_method': payment.payment_method,
#                             'transaction_id': payment.transaction_id,
#                         }
#                     )
                    
#                     if created:
#                         logger.info(f"Created enrollment: {user.email} -> {pw.webinar.title}")
#                     else:
#                         logger.info(f"Enrollment already exists: {user.email} -> {pw.webinar.title}")
                    
#                     # Prepare webinar details for response (optional)
#                     # webinar_url = f"{frontend_url}/webinars/{pw.webinar.webinar_id}"
#                       # Determine webinar type based URL path
#                     webinar_slug = generate_slug(pw.webinar.title)
#                     webinar_type_path = 'live-webinar' if pw.webinar.webinar_type == 'live' else 'recorded-webinar'
                    
#                     webinar_url = f"{frontend_url}/{webinar_type_path}/{pw.webinar.webinar_id}/{webinar_slug}"
                    
#                     webinar_details.append({
#                         'title': pw.webinar.title,
#                         'instructor': pw.webinar.speaker.user.get_full_name() if pw.webinar.speaker else 'TBA',
#                         # 'scheduled_date': pw.webinar.scheduled_date.strftime("%B %d, %Y at %I:%M %p") if pw.webinar.scheduled_date else 'On Demand',
#                         'scheduled_date': pw.webinar.scheduled_date.strftime("%B %d, %Y") if pw.webinar.scheduled_date else 'On Demand',
                        
#                         'duration': f"{pw.webinar.duration} minutes" if pw.webinar.duration else 'Self-paced',
#                         'webinar_url': webinar_url,
#                         'access_type': pw.access_type,
#                         'amount': f"{pw.amount:.2f}",
#                     })
                
#                 # Send payment confirmation email via Celery
#                 try:
#                     # Import here to avoid circular imports
#                     from apps.notifications.email_service import send_payment_confirmation_email_task
                    
#                     # Queue the email task
#                     task = send_payment_confirmation_email_task.delay(user.id, payment.id)
#                     logger.info(f"[{platform.name if platform else 'System'}] 📧 Payment confirmation email queued (Task: {task.id})")
                    
#                 except Exception as email_error:
#                     logger.error(f"❌ Failed to queue payment confirmation email: {email_error}")
                    
#                     # Fallback to synchronous sending
#                     try:
#                         from apps.notifications.email_service import EmailService
                        
#                         # Prepare order object (mock it from payment)
#                         class OrderMock:
#                             def __init__(self, payment_obj):
#                                 self.order_id = payment_obj.transaction_id
#                                 self.total_amount = payment_obj.amount
#                                 self.currency = payment_obj.currency
#                                 self.transaction_id = payment_obj.transaction_id
#                                 self.payment_method = payment_obj.payment_method
#                                 self.created_at = payment_obj.completed_at or payment_obj.created_at
#                                 self.platform = payment_obj.platform
#                                 self.invoice_number = payment.invoice_number
#                                 self._payment = payment_obj  # Store payment reference
                            
#                             def items(self):
#                                 """Return mock items manager"""
#                                 class ItemsMock:
#                                     def __init__(self, payment_obj):
#                                         self._payment = payment_obj
                                    
#                                     def all(self):
#                                         """Return PaymentWebinar queryset"""
#                                         return PaymentWebinar.objects.filter(
#                                             payment=self._payment  # ✅ Fixed: Use payment object, not transaction_id
#                                         ).select_related('webinar', 'webinar__speaker', 'webinar__speaker__user')
                                
#                                 return ItemsMock(self._payment)
                        
#                         order_mock = OrderMock(payment)
                        
#                         EmailService.send_payment_confirmation_email(
#                             user=user,
#                             order=order_mock,
#                             platform=platform
#                         )
                        
#                         logger.info(f"[{platform.name if platform else 'System'}] ✅ Payment confirmation sent synchronously")
#                     except Exception as sync_error:
#                         logger.error(f"❌ Failed to send payment confirmation synchronously: {sync_error}", exc_info=True)
                
#                 # Return success response
#                 serializer = PaymentSerializer(payment)
#                 return Response({
#                     'success': True,
#                     'message': 'Payment verified successfully',
#                     'payment': serializer.data,
#                     'webinars': webinar_details,  # Include webinar details in response
#                 })
#         else:
#             # Payment verification failed
#             payment.status = 'failed'
#             payment.failure_reason = verification_result.get('message', 'Verification failed')
#             payment.save()
            
#             logger.warning(f"Payment verification failed: {transaction_id}")
#             return Response({
#                 'success': False,
#                 'error': 'Payment verification failed',
#                 'details': verification_result.get('message')
#             }, status=status.HTTP_400_BAD_REQUEST)
    
#     except PaymentVerificationError as e:
#         logger.error(f"Payment verification error: {str(e)}")
#         return Response({
#             'success': False,
#             'error': str(e)
#         }, status=status.HTTP_400_BAD_REQUEST)
    
#     except Exception as e:
#         logger.error(f"Unexpected error during payment verification: {str(e)}", exc_info=True)
#         return Response({
#             'success': False,
#             'error': 'An unexpected error occurred during payment verification'
#         }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)



@api_view(['POST'])
@permission_classes([permissions.IsAuthenticated])
def verify_payment(request):
    try:
        user = request.user
        platform = getattr(request, 'platform', None)
        
        logger.debug(f"Request authenticated for {platform.name if platform else None}")
        
        payment_method = request.data.get('payment_method')
        transaction_id = request.data.get('transaction_id')
        payment_data = request.data.get('payment_data', {})
        
        if not payment_method or not transaction_id:
            return Response({
                'success': False,
                'error': 'Payment method and transaction ID are required'
            }, status=status.HTTP_400_BAD_REQUEST)
        
        # Get gateway
        gateway = payment_gateway_manager.get_gateway(payment_method)
        if not gateway:
            logger.error(f"Gateway not found: {payment_method}")
            return Response({
                'success': False,
                'error': f'Payment gateway {payment_method} not configured'
            }, status=status.HTTP_400_BAD_REQUEST)
        
        logger.debug(f"Gateway found: {payment_method}")
        
        # Get payment record
        payment = get_object_or_404(
            Payment.objects.select_related('user', 'platform'),
            transaction_id=transaction_id,
            user=user
        )
        
        logger.info(f"Verifying payment {transaction_id}")
        
        # Verify payment with gateway
        verification_result = gateway.verify_payment(payment_data)
        
        if verification_result.get('verified'):
            # Update payment status
            with transaction.atomic():
                if not payment.invoice_number:
                    payment.invoice_number = Payment.generate_unique_invoice_number(payment.platform)

                payment.status = 'completed'
                payment.gateway_payment_id = verification_result.get('payment_id', '')
                payment.completed_at = timezone.now()
                payment.save(update_fields=['invoice_number', 'status', 'gateway_payment_id', 'completed_at'])
        
                logger.info(f"Payment verified: {transaction_id}")
                
                # Create enrollments
                payment_webinars = PaymentWebinar.objects.filter(
                    payment=payment
                ).select_related('webinar', 'webinar__speaker', 'webinar__speaker__user')
                
                # Get frontend URL
                frontend_url = f"https://www.{platform.domain}" if platform and platform.domain else getattr(settings, 'DEFAULT_FRONTEND_URL', 'https://www.peopleskilltraining.com')
                
                # Create enrollments and prepare webinar details
                webinar_details = []
                for pw in payment_webinars:
                    # Create enrollment
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
                    
                    if created:
                        logger.info(f"Created enrollment: {user.email} -> {pw.webinar.title}")
                    else:
                        logger.info(f"Enrollment already exists: {user.email} -> {pw.webinar.title}")
                    
                    # Prepare webinar details
                    webinar_slug = generate_slug(pw.webinar.title)
                    webinar_type_path = 'live-webinar' if pw.webinar.webinar_type == 'live' else 'recorded-webinar'
                    webinar_url = f"{frontend_url}/{webinar_type_path}/{pw.webinar.webinar_id}/{webinar_slug}"
                    
                    webinar_details.append({
                        'title': pw.webinar.title,
                        'instructor': pw.webinar.speaker.user.get_full_name() if pw.webinar.speaker else 'TBA',
                        'scheduled_date': pw.webinar.scheduled_date.strftime("%B %d, %Y") if pw.webinar.scheduled_date else 'On Demand',
                        'duration': f"{pw.webinar.duration} minutes" if pw.webinar.duration else 'Self-paced',
                        'webinar_url': webinar_url,
                        'access_type': pw.access_type,
                        'amount': f"{pw.amount:.2f}",
                    })
                
                # ✅ Send payment confirmation email and check if sent
                email_sent = False
                email_error_message = None
                
                try:
                    # Try async sending via Celery
                    from apps.notifications.email_service import send_payment_confirmation_email_task
                    
                    # Use apply_async with countdown to ensure transaction commits first
                    task = send_payment_confirmation_email_task.apply_async(
                        args=[user.id, payment.id],
                        countdown=2  # Wait 2 seconds for DB commit
                    )
                    
                    logger.info(f"[{platform.name if platform else 'System'}] 📧 Payment confirmation email queued (Task: {task.id})")
                    
                    # For Celery tasks, we assume success (actual delivery checked by worker)
                    email_sent = True
                    
                except Exception as celery_error:
                    logger.error(f"❌ Failed to queue payment confirmation email: {celery_error}")
                    
                    # ✅ Fallback to synchronous sending with fail_silently=False
                    try:
                        from apps.notifications.email_service import EmailService
                        from django.core.mail import send_mail
                        
                        # Prepare order mock
                        class OrderMock:
                            def __init__(self, payment_obj):
                                self.order_id = payment_obj.transaction_id
                                self.total_amount = payment_obj.amount
                                self.currency = payment_obj.currency
                                self.transaction_id = payment_obj.transaction_id
                                self.payment_method = payment_obj.payment_method
                                self.created_at = payment_obj.completed_at or payment_obj.created_at
                                self.platform = payment_obj.platform
                                self.invoice_number = payment_obj.invoice_number
                                self._payment = payment_obj
                            
                            def items(self):
                                class ItemsMock:
                                    def __init__(self, payment_obj):
                                        self._payment = payment_obj
                                    
                                    def all(self):
                                        return PaymentWebinar.objects.filter(
                                            payment=self._payment
                                        ).select_related('webinar', 'webinar__speaker', 'webinar__speaker__user')
                                
                                return ItemsMock(self._payment)
                        
                        order_mock = OrderMock(payment)
                        
                        # ✅ Send with fail_silently=False to catch SMTP errors
                        result = EmailService.send_payment_confirmation_email(
                            user=user,
                            order=order_mock,
                            platform=platform
                        )
                        
                        # Check if send returned success (typically returns 1 for success)
                        if result and result > 0:
                            email_sent = True
                            logger.info(f"[{platform.name if platform else 'System'}] ✅ Payment confirmation sent synchronously")
                        else:
                            email_error_message = "Email sending returned 0 (not sent)"
                            logger.warning(f"❌ Email not sent: {email_error_message}")
                            
                    except Exception as sync_error:
                        email_error_message = str(sync_error)
                        logger.error(f"❌ Failed to send payment confirmation synchronously: {sync_error}", exc_info=True)
                
                # ✅ Return response with email status
                serializer = PaymentSerializer(payment)
                response_data = {
                    'success': True,
                    'message': 'Payment verified successfully',
                    'payment': serializer.data,
                    'webinars': webinar_details,
                    'email_sent': email_sent,  # ✅ Include email status
                }
                
                # ✅ Add email error details if failed
                if not email_sent and email_error_message:
                    response_data['email_error'] = email_error_message
                    response_data['message'] = 'Payment verified but confirmation email failed to send'
                
                return Response(response_data)
        else:
            # Payment verification failed
            payment.status = 'failed'
            payment.failure_reason = verification_result.get('message', 'Verification failed')
            payment.save()
            
            logger.warning(f"Payment verification failed: {transaction_id}")
            return Response({
                'success': False,
                'error': 'Payment verification failed',
                'details': verification_result.get('message')
            }, status=status.HTTP_400_BAD_REQUEST)
    
    except PaymentVerificationError as e:
        logger.error(f"Payment verification error: {str(e)}")
        return Response({
            'success': False,
            'error': str(e)
        }, status=status.HTTP_400_BAD_REQUEST)
    
    except Exception as e:
        logger.error(f"Unexpected error during payment verification: {str(e)}", exc_info=True)
        return Response({
            'success': False,
            'error': 'An unexpected error occurred during payment verification'
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['GET'])
@permission_classes([permissions.IsAuthenticated])
def download_invoice(request, pk):
    try:
        payment = get_object_or_404(
            Payment.objects.select_related('user', 'platform'),
            pk=pk,
            user=request.user
        )
        
        if payment.status != 'completed':
            return Response({
                'success': False,
                'error': 'Invoice only available for completed payments'
            }, status=400)
        
        platform = payment.platform or getattr(request, 'platform', None)
        
        subtotal = sum([pw.amount for pw in payment.payment_webinars.all()])
        processing_fee = Decimal('0.00')
        discount = Decimal('0.00')
        
        access_types = [pw.access_type for pw in payment.payment_webinars.all()]
        has_live_access = any('live' in at.lower() or 'combo' in at.lower() for at in access_types)
        has_recorded_access = any('recorded' in at.lower() or 'combo' in at.lower() for at in access_types)
        
        platform_id = getattr(platform, 'platform_id', '').lower() if platform else ''
        
        # Set platform specific colors and fallback logo overrides
        if platform_id == 'compliancetrained':
            primary_color = '#008c9d'  # Dark teal
            secondary_color = '#01bbc7'  # Light turquoise
            logo_url = platform.logo_url if platform and platform.logo_url else None
        elif platform_id == 'peopleskilltraining':
            primary_color = '#6b21a8'  # Purple
            secondary_color = '#a855f7'  # Light purple
            logo_url = platform.logo_url if platform and platform.logo_url else None
        elif platform_id == 'workforceskilled':
            primary_color = '#295F2D'  # Deep green
            secondary_color = '#FFE67C'  # Soft yellow-gold
            logo_url = platform.logo_url if platform and platform.logo_url else None
        else:
            primary_color = platform.primary_color if platform else '#2563eb'
            secondary_color = platform.secondary_color if platform else '#1e40af'
            logo_url = platform.logo_url if platform and platform.logo_url else None
        
        platform_data = {
            'name': platform.name if platform else 'PeopleSkill Training',
            'logo_url': logo_url,
            'primary_color': primary_color,
            'secondary_color': secondary_color,
            'accent_color': platform.accent_color if platform else '#10b981',
            'support_email': platform.support_email if platform else 'support@peopleskilltraining.com',
            'contact_phone': platform.contact_phone if platform else None,
            'address': platform.address if platform else '2313 East Venango St Ste 4B PMB 1026, Philadelphia, PA 19134, United States',
            'website': f"https://www.{platform.domain}" if platform and platform.domain else 'https://www.peopleskilltraining.com',
            'invoice_prefix': platform.invoice_prefix if platform and hasattr(platform, 'invoice_prefix') else 'INV',
        }
        
        platform_data['address_lines'] = [line.strip() for line in platform_data['address'].split(',')] if platform_data['address'] else []
        invoice_number = payment.invoice_number or f"{platform_data['invoice_prefix']}-{payment.id:06d}"
  
        html_string = render_to_string('payments/invoice.html', {
            'payment': payment,
            'platform': platform_data,
            'subtotal': subtotal,
            'processing_fee': processing_fee,
            'discount': discount,
            'has_live_access': has_live_access,
            'has_recorded_access': has_recorded_access,
             'invoice_number': invoice_number,
        })
        
        html = HTML(string=html_string)
        pdf = html.write_pdf()
      
        # invoice_number = f"{platform_data['invoice_prefix']}-{payment.id:06d}"
        filename = f"{invoice_number}.pdf"
        
        response = HttpResponse(pdf, content_type='application/pdf')
        response['Content-Disposition'] = f'attachment; filename="{filename}"'
        return response
    
    except Exception as e:
        logger.error(f"Invoice generation error: {str(e)}", exc_info=True)
        return Response({'success': False, 'error': 'Failed to generate invoice'}, status=500)

# ============================================================================
# SECTION 2: REFUND REQUEST VIEWS
# ============================================================================

class RefundRequestListView(generics.ListCreateAPIView):
   
    serializer_class = RefundRequestSerializer
    permission_classes = [permissions.IsAuthenticated]
    
    def get_queryset(self):
        if hasattr(self.request.user, 'role') and self.request.user.role == 'admin':
            # Admins see all refunds
            queryset = RefundRequest.objects.select_related(
                'payment',
                'payment__user',
                'processed_by'
            ).all()
        else:
            # Users only see their own refunds
            queryset = RefundRequest.objects.select_related(
                'payment',
                'payment__user',
                'processed_by'
            ).filter(payment__user=self.request.user)
        
        # Filter by status
        status_filter = self.request.query_params.get('status')
        if status_filter:
            queryset = queryset.filter(status=status_filter)
        
        # Filter by date range
        date_from = self.request.query_params.get('date_from')
        date_to = self.request.query_params.get('date_to')
        
        if date_from:
            queryset = queryset.filter(requested_at__gte=date_from)
        if date_to:
            queryset = queryset.filter(requested_at__lte=date_to)
        
        # Order by requested_at
        return queryset.order_by('-requested_at')
    
    def perform_create(self, serializer):
      
        serializer.save()


class RefundRequestDetailView(generics.RetrieveUpdateDestroyAPIView):
 
    serializer_class = RefundRequestSerializer
    permission_classes = [permissions.IsAuthenticated, IsAdminUser]
    
    def get_queryset(self):
        return RefundRequest.objects.select_related(
            'payment',
            'payment__user',
            'processed_by'
        ).all()
    
    def perform_update(self, serializer):
        
        if serializer.validated_data.get('status') == 'processed':
            serializer.save(
                processed_by=self.request.user,
                processed_at=timezone.now()
            )
        else:
            serializer.save()


@api_view(['POST'])
@permission_classes([permissions.IsAuthenticated, IsAdminUser])
def process_refund(request, pk):
   
    try:
        refund = RefundRequest.objects.get(pk=pk)
        payment = refund.payment
        
        if refund.status != 'approved':
            return Response(
                {'error': 'Refund must be approved before processing'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        if payment.status == 'refunded':
            return Response(
                {'error': 'Payment already refunded'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Process refund with payment gateway
        # This would call your payment gateway's refund API
        
        # Update refund status
        refund.status = 'processed'
        refund.processed_by = request.user
        refund.processed_at = timezone.now()
        refund.save()
        
        # Update payment status
        payment.status = 'refunded'
        payment.refunded_amount = refund.refund_amount
        payment.save()
        
        return Response(
            {'status': 'success', 'message': 'Refund processed successfully'},
            status=status.HTTP_200_OK
        )
        
    except RefundRequest.DoesNotExist:
        return Response(
            {'error': 'Refund request not found'},
            status=status.HTTP_404_NOT_FOUND
        )
    except Exception as e:
        logger.error(f"Error processing refund: {str(e)}")
        return Response(
            {'error': str(e)},
            status=status.HTTP_400_BAD_REQUEST
        )