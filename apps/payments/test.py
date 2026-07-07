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

logger = logging.getLogger(__name__)

def generate_slug(title):
    \"\"\"Generate URL-friendly slug from title\"\"\"
    import re
    slug = title.lower()
    slug = re.sub(r'[^a-z0-9\\s-]', '', slug)  # Remove special characters
    slug = re.sub(r'\\s+', '-', slug)  # Replace spaces with hyphens
    slug = re.sub(r'-+', '-', slug)  # Replace multiple hyphens with single
    return slug.strip('-')


# ============================================================================
# SECTION 1: USER PAYMENT VIEWS
# ============================================================================

class PaymentListView(generics.ListAPIView):
    \"\"\"List user's payments - Platform-filtered\"\"\"
    serializer_class = PaymentListSerializer
    permission_classes = [permissions.IsAuthenticated]
    filterset_fields = ['status', 'payment_method']
    search_fields = ['transaction_id', 'invoice_number']
    ordering_fields = ['created_at', 'amount']
    ordering = ['-created_at']

    def get_queryset(self):
        queryset = Payment.objects.filter(
            user=self.request.user
        ).select_related('user', 'platform').prefetch_related('payment_webinars__webinar')
        
        # Platform filtering
        platform = getattr(self.request, 'platform', None)
        if platform:
            queryset = queryset.filter(platform=platform)
        
        return queryset


class PaymentDetailView(generics.RetrieveAPIView):
    \"\"\"Payment detail - Platform-aware\"\"\"
    serializer_class = AdminPaymentDetailSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        queryset = Payment.objects.filter(
            user=self.request.user
        ).select_related('user', 'platform').prefetch_related('payment_webinars__webinar')
        
        # Platform filtering
        platform = getattr(self.request, 'platform', None)
        if platform:
            queryset = queryset.filter(platform=platform)
        
        return queryset


@api_view(['GET'])
@permission_classes([permissions.AllowAny])
def get_available_payment_gateways(request):
    \"\"\"Get list of available payment gateways from database with USD support\"\"\"
    
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
    \"\"\"
    Enhanced checkout: Check for existing pending payment or create new one
    \"\"\"
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
            # ✅ FIXED: Support both 'webinar_id' (string) and 'id' (integer)
            webinar_id_str = item.get('webinar_id')  # e.g., \"WEB2510016\" or 16
            webinar_pk = item.get('id')  # e.g., 16
            
            access_type = item.get('access_type', 'recorded_single')
            price = Decimal(str(item.get('price', 0)))
            
            if price <= 0:
                logger.error(f"❌ Invalid price for webinar {webinar_id_str or webinar_pk}: {price}")
                return Response({
                    'success': False,
                    'error': f'Invalid price for webinar {webinar_id_str or webinar_pk}'
                }, status=status.HTTP_400_BAD_REQUEST)
            
            try:
                # ✅ Try multiple lookup strategies
                webinar = None
                
                # Strategy 1: Try to lookup by webinar_id (string like \"WEB2510016\")
                if webinar_id_str and isinstance(webinar_id_str, str) and not webinar_id_str.isdigit():
                    try:
                        webinar = Webinar.objects.get(webinar_id=webinar_id_str)
                        logger.debug(f"✅ Found webinar by webinar_id: {webinar.webinar_id}")
                    except Webinar.DoesNotExist:
                        pass
                
                # Strategy 2: Try to lookup by primary key (integer like 16)
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
            
            # ✅ Compare by database ID (primary key), not webinar_id string
            existing_webinar_pks = set(
                existing_payment.payment_webinars.values_list('webinar__id', flat=True)
            )
            requested_webinar_pks = set(item['webinar'].id for item in webinar_items)
            
            logger.info(f"   - Existing webinar IDs: {sorted(existing_webinar_pks)}")
            logger.info(f"   - Requested webinar IDs: {sorted(requested_webinar_pks)}")
            
            # ✅ Check if webinars match
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
                
                return Response({
                    'success': True,
                    'message': 'Resuming existing payment',
                    'payment': PaymentSerializer(existing_payment).data,
                    'gateway_order_id': existing_payment.gateway_order_id,
                    'gateway_config': gateway.get_client_config()
                })
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
                
                order_data = {
                    'user_id': user.id,
                    'user_email': user.email,
                    'user_name': user.get_full_name() or user.email,
                    'platform_id': platform.platform_id if platform else 'default',
                    'transaction_id': payment.transaction_id,
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
                
                return Response({
                    'success': True,
                    'message': 'Payment initiated successfully',
                    'payment': PaymentSerializer(payment).data,
                    'gateway_order_id': payment.gateway_order_id,
                    'gateway_config': gateway.get_client_config()
                })
                
            except PaymentGatewayError as e:
                logger.error(f"❌ Gateway error: {str(e)}")
                payment.status = 'failed'
                payment.error_message = str(e)
                payment.save(update_fields=['status', 'error_message'])
                
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


@api_view(['POST'])
@permission_classes([permissions.IsAuthenticated])
def verify_payment(request):
    \"\"\"Verify payment completion and send confirmation email\"\"\"
    try:
        user = request.user
        platform = getattr(request, 'platform', None)
        
        logger.debug(f"✅ Request authenticated for platform: {platform.name if platform else 'None'}")
        
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
            logger.error(f"⚠️ Gateway not found: {payment_method}")
            return Response({
                'success': False,
                'error': f'Payment gateway {payment_method} not configured'
            }, status=status.HTTP_400_BAD_REQUEST)
        
        logger.debug(f"✅ Gateway found: {payment_method}")
        
        # Get payment record
        payment = get_object_or_404(
            Payment.objects.select_related('user', 'platform'),
            transaction_id=transaction_id,
            user=user
        )
        
        # Verify payment with gateway
        logger.info(f"🔍 Verifying payment: {transaction_id}")
        verification_result = gateway.verify_payment(payment_data)
        
        if verification_result.get('verified'):
            # Update payment status
            with transaction.atomic():
                payment.status = 'completed'
                payment.gateway_payment_id = verification_result.get('payment_id', '')
                payment.completed_at = timezone.now()
                payment.save()
                
                logger.info(f"✅ Payment verified: {transaction_id}")
                
                # ✅ Create enrollments and prepare webinar details for email
                payment_webinars = PaymentWebinar.objects.filter(payment=payment).select_related('webinar', 'webinar__speaker')
                webinar_details = []
                
                # Get platform-specific frontend URL
                frontend_url = f"https://{platform.domain}" if platform and platform.domain else getattr(settings, 'DEFAULT_FRONTEND_URL', 'https://peopleskilltraining.com')
                
                for pw in payment_webinars:
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
                        logger.info(f"✅ Created enrollment: {user.email} → {pw.webinar.title}")
                    else:
                        logger.info(f"ℹ️ Enrollment already exists: {user.email} → {pw.webinar.title}")
                    
                    # ✅ Generate slug from webinar title
                    webinar_slug = generate_slug(pw.webinar.title)
                    
                    # ✅ Generate correct webinar URL based on type
                    webinar_type = 'live-webinar' if pw.webinar.webinar_type == 'live' else 'recorded-webinar'
                    webinar_url = f"{frontend_url}/{webinar_type}/{pw.webinar.webinar_id}/{webinar_slug}"
                    
                    # ✅ Prepare webinar details for email
                    webinar_details.append({
                        'title': pw.webinar.title,
                        'instructor': pw.webinar.speaker.user.get_full_name() if pw.webinar.speaker else 'TBA',
                        'scheduled_date': pw.webinar.scheduled_date.strftime('%B %d, %Y at %I:%M %p') if pw.webinar.scheduled_date else 'On Demand',
                        'duration': f"{pw.webinar.duration} minutes" if pw.webinar.duration else 'Self-paced',
                        'webinar_url': webinar_url,
                    })

                # ✅ Send payment confirmation email with BCC to admin
                try:
                    from apps.notifications.email_service import EmailService
       
                    # Get platform-specific email context
                    context = EmailService.get_email_context(
                        user=user,
                        platform=platform,
                        transaction_id=payment.transaction_id,
                        payment_date=payment.completed_at.strftime('%B %d, %Y'),
                        payment_method=payment.get_payment_method_display(),
                        total_amount=f"{payment.amount:.2f}",
                        currency=payment.currency,
                        webinars=webinar_details,
                        dashboard_url=f"{frontend_url}/attendee/enrollments",
                        invoice_url=f"{frontend_url}/attendee/orders"
                    )
                    
                    # ✅ Get admin BCC list
                    bcc_list = platform.get_admin_emails_for_bcc() if platform else []
                    if bcc_list:
                        logger.info(f"📧 Will send BCC copy to: {', '.join(bcc_list)}")
                    # Send email via Brevo with BCC
                    EmailService.send_email(
                        subject=f'Payment Confirmed - {payment.transaction_id}',
                        template_name='payment_confirmation',
                        context=context,
                        recipient_list=[user.email],
                        platform=platform,
                        bcc=bcc_list  # ✅ Send copy to admin
                    )
                    
                    logger.info(f"✅ Sent payment confirmation email to {user.email}" + 
                               (f" with BCC to {bcc_list[0]}" if bcc_list else ""))
                    
                except Exception as e:
                    logger.error(f"❌ Failed to send payment confirmation email: {str(e)}")
                    # Don't fail the payment - email is non-critical

            # Return success response
            serializer = PaymentSerializer(payment)
            return Response({
                'success': True,
                'message': 'Payment verified successfully',
                'payment': serializer.data
            })
        else:
            # Payment verification failed
            payment.status = 'failed'
            payment.failure_reason = verification_result.get('message', 'Verification failed')
            payment.save()
            
            logger.warning(f"⚠️ Payment verification failed: {transaction_id}")
            
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
    \"\"\"Generate and download PDF invoice\"\"\"
    try:
        # Get payment
        payment = get_object_or_404(Payment, pk=pk, user=request.user)
        
        if payment.status != 'completed':
            return Response({
                'success': False,
                'error': 'Invoice only available for completed payments'
            }, status=400)
        
        # Calculate totals
        subtotal = sum([pw.amount for pw in payment.payment_webinars.all()])
        processing_fee = Decimal('0.00')
        discount = Decimal('0.00')
        
        # Check access types
        access_types = [pw.access_type for pw in payment.payment_webinars.all()]
        has_live_access = any('live' in at.lower() or 'combo' in at.lower() for at in access_types)
        has_recorded_access = any('recorded' in at.lower() or 'combo' in at.lower() for at in access_types)
        
        # Render HTML template
        html_string = render_to_string('payments/invoice.html', {
            'payment': payment,
            'subtotal': subtotal,
            'processing_fee': processing_fee,
            'discount': discount,
            'has_live_access': has_live_access,
            'has_recorded_access': has_recorded_access,
        })
        
        # Generate PDF
        html = HTML(string=html_string)
        pdf = html.write_pdf()
        
        # Return PDF response
        response = HttpResponse(pdf, content_type='application/pdf')
        response['Content-Disposition'] = f'attachment; filename="Invoice_{payment.transaction_id}.pdf"'
        
        return response
        
    except Exception as e:
        logger.error(f"Invoice generation error: {str(e)}", exc_info=True)
        return Response({
            'success': False,
            'error': 'Failed to generate invoice'
        }, status=500)


# ============================================================================
# SECTION 2: REFUND REQUEST VIEWS
# ============================================================================

class RefundRequestListView(generics.ListCreateAPIView):
    \"\"\"List and create refund requests\"\"\"
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
        \"\"\"Create refund request for current user\"\"\"
        serializer.save()


class RefundRequestDetailView(generics.RetrieveUpdateDestroyAPIView):
    \"\"\"Retrieve, update, or delete a refund request\"\"\"
    serializer_class = RefundRequestSerializer
    permission_classes = [permissions.IsAuthenticated, IsAdminUser]
    
    def get_queryset(self):
        return RefundRequest.objects.select_related(
            'payment',
            'payment__user',
            'processed_by'
        ).all()
    
    def perform_update(self, serializer):
        \"\"\"Update refund request\"\"\"
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
    \"\"\"Process a refund request\"\"\"
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