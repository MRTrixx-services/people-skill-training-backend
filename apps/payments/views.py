from rest_framework import generics, status, permissions
from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response
from django.shortcuts import get_object_or_404
from django.utils import timezone
from django.conf import settings
from django.db import transaction
from django.http import HttpResponse
from apps.webinars.models import Webinar
from apps.users.permissions import IsInstructorOrAdmin, IsAdminUser
# Stripe imports
import stripe
from django.http import JsonResponse
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
from weasyprint import HTML
from decimal import Decimal
from apps.notifications.email_service import send_payment_confirmation_email_task
import logging
from .gateway_manager import payment_gateway_manager
from .gateways.base import PaymentGatewayError, PaymentVerificationError, RefundError
from django.db.models import Sum, Count, Q, F, Avg, DecimalField
from rest_framework.pagination import PageNumberPagination
import traceback
logger = logging.getLogger(__name__)

def generate_slug(title):
    import re
    slug = title.lower()
    slug = re.sub(r'[^a-z0-9\s-]', '', slug)
    slug = re.sub(r'\s+', '-', slug)
    slug = re.sub(r'-+', '-', slug)
    return slug.strip('-')


# ============================================================================
# ADMIN INVOICE ENDPOINTS - NEW
# ============================================================================

@api_view(['GET'])
@permission_classes([permissions.IsAuthenticated])
def download_invoice_admin(request, pk):
    """
    Admin endpoint to download invoice PDF
    URL: /api/payments/admin/payments/<pk>/invoice/
    Method: GET
    Permissions: Authenticated users (admin check in logic)
    """
    try:
        logger.info(f"📥 Admin invoice download request for payment {pk}")
        
        # ✅ Get payment by primary key
        payment = get_object_or_404(Payment, pk=pk)
        
        # ✅ Check if user is admin/staff
        if not request.user.is_staff and not request.user.is_superuser:
            logger.warning(f"⚠️ Permission denied for user {request.user.id} trying to access payment {pk}")
            return Response({
                'error': 'Permission denied',
                'message': 'Only administrators can download invoices'
            }, status=status.HTTP_403_FORBIDDEN)
        
        # ✅ Verify payment is completed
        if payment.status != 'completed':
            return Response({
                'success': False,
                'error': 'Invoice only available for completed payments'
            }, status=status.HTTP_400_BAD_REQUEST)
        
        # ✅ Generate invoice PDF using existing logic
        platform = payment.platform or getattr(request, 'platform', None)
        subtotal = sum([pw.amount for pw in payment.payment_webinars.all()])
        processing_fee = Decimal('0.00')
        discount = Decimal('0.00')
        access_types = [pw.access_type for pw in payment.payment_webinars.all()]
        has_live_access = any('live' in at.lower() or 'combo' in at.lower() for at in access_types)
        has_recorded_access = any('recorded' in at.lower() or 'combo' in at.lower() for at in access_types)
        
        platform_id = getattr(platform, 'platform_id', '').lower() if platform else ''
        if platform_id == 'compliancetrained':
            primary_color = '#008c9d'
            secondary_color = '#01bbc7'
            logo_url = platform.logo_url if platform and platform.logo_url else None
        elif platform_id == 'peopleskilltraining':
            primary_color = '#6b21a8'
            secondary_color = '#a855f7'
            logo_url = platform.logo_url if platform and platform.logo_url else None
        elif platform_id == 'workforceskilled':
            primary_color = '#295F2D'
            secondary_color = '#FFE67C'
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
        
        filename = f"{invoice_number}.pdf"
        
        # ✅ Create HTTP response with PDF
        response = HttpResponse(pdf, content_type='application/pdf')
        response['Content-Disposition'] = f'attachment; filename="{filename}"'
        response['Content-Length'] = len(pdf)
        
        logger.info(f"✅ Admin invoice downloaded successfully: {invoice_number}")
        
        return response
        
    except Payment.DoesNotExist:
        logger.error(f"❌ Payment {pk} not found")
        return Response({
            'error': 'Payment not found',
            'message': f'No payment exists with ID {pk}'
        }, status=status.HTTP_404_NOT_FOUND)
        
    except Exception as e:
        logger.error(f"❌ Admin invoice download error: {str(e)}")
        logger.error(traceback.format_exc())
        return Response({
            'error': 'Failed to download invoice',
            'message': str(e),
            'details': 'An unexpected error occurred while generating the invoice'
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['POST'])
@permission_classes([permissions.IsAuthenticated])
def resend_invoice_admin(request, pk):
    """
    Admin endpoint to resend invoice via email
    URL: /api/payments/admin/payments/<pk>/resend-invoice/
    Method: POST
    Permissions: Authenticated users (admin check in logic)
    Body: { "email": "user@example.com" }
    """
    try:
        logger.info(f"📤 Admin resend invoice request for payment {pk}")
        
        # ✅ Get payment
        payment = get_object_or_404(Payment, pk=pk)
        
        # ✅ Check if user is admin/staff
        if not request.user.is_staff and not request.user.is_superuser:
            logger.warning(f"⚠️ Permission denied for user {request.user.id}")
            return Response({
                'error': 'Permission denied',
                'message': 'Only administrators can resend invoices'
            }, status=status.HTTP_403_FORBIDDEN)
        
        # ✅ Verify payment is completed
        if payment.status != 'completed':
            return Response({
                'success': False,
                'error': 'Invoice only available for completed payments'
            }, status=status.HTTP_400_BAD_REQUEST)
        
        # ✅ Get email from request
        email = request.data.get('email', '').strip()
        if not email:
            email = payment.user_email
        
        if not email:
            return Response({
                'error': 'Email required',
                'message': 'No email address provided'
            }, status=status.HTTP_400_BAD_REQUEST)
        
        # ✅ Generate invoice PDF
        platform = payment.platform or getattr(request, 'platform', None)
        subtotal = sum([pw.amount for pw in payment.payment_webinars.all()])
        processing_fee = Decimal('0.00')
        discount = Decimal('0.00')
        access_types = [pw.access_type for pw in payment.payment_webinars.all()]
        has_live_access = any('live' in at.lower() or 'combo' in at.lower() for at in access_types)
        has_recorded_access = any('recorded' in at.lower() or 'combo' in at.lower() for at in access_types)
        
        platform_id = getattr(platform, 'platform_id', '').lower() if platform else ''
        if platform_id == 'compliancetrained':
            primary_color = '#008c9d'
            secondary_color = '#01bbc7'
            logo_url = platform.logo_url if platform and platform.logo_url else None
        elif platform_id == 'peopleskilltraining':
            primary_color = '#6b21a8'
            secondary_color = '#a855f7'
            logo_url = platform.logo_url if platform and platform.logo_url else None
        elif platform_id == 'workforceskilled':
            primary_color = '#295F2D'
            secondary_color = '#FFE67C'
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
        pdf_buffer = html.write_pdf()
        
        # ✅ Send email with invoice attachment
        from apps.notifications.email_service import EmailService
        
        # Build webinar details for email
        payment_webinars = payment.payment_webinars.select_related('webinar', 'webinar__speaker', 'webinar__speaker__user')
        webinar_details = []
        for pw in payment_webinars:
            webinar_details.append({
                'title': pw.webinar.title,
                'instructor': pw.webinar.speaker.user.get_full_name() if pw.webinar.speaker else 'TBA',
                'scheduled_date': pw.webinar.scheduled_date.strftime("%B %d, %Y") if pw.webinar.scheduled_date else 'On Demand',
                'duration': f"{pw.webinar.duration} minutes" if pw.webinar.duration else 'Self-paced',
                'access_type': pw.access_type,
                'amount': f"{pw.amount:.2f}",
            })
        
        context = EmailService.get_email_context(
            user=payment.user,
            platform=platform,
            transaction_id=payment.transaction_id,
            payment_date=payment.completed_at.strftime('%B %d, %Y') if payment.completed_at else payment.created_at.strftime('%B %d, %Y'),
            payment_method=payment.get_payment_method_display(),
            total_amount=f"{payment.amount:.2f}",
            currency=payment.currency,
            webinars=webinar_details,
            dashboard_url=f"https://www.peopleskilltraining.com/attendee/enrollments",
            invoice_url=f"https://www.peopleskilltraining.com/attendee/orders"
        )
        
        # ✅ Attach PDF to email
        email_sent = EmailService.send_email(
            subject=f'Your Invoice - {invoice_number}',
            template_name='payment_confirmation',  # Reuse existing template or create new one
            context=context,
            recipient_list=[email],
            platform=platform,
            attachments=[{
                'filename': f'{invoice_number}.pdf',
                'content': pdf_buffer,
                'content_type': 'application/pdf'
            }]
        )
        
        if email_sent:
            logger.info(f"✅ Invoice resent to {email}")
            return Response({
                'success': True,
                'message': f'Invoice sent successfully to {email}',
                'email': email
            }, status=status.HTTP_200_OK)
        else:
            logger.error(f"❌ Failed to send invoice to {email}")
            return Response({
                'error': 'Failed to send invoice',
                'message': 'Email delivery failed'
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
            
    except Payment.DoesNotExist:
        logger.error(f"❌ Payment {pk} not found")
        return Response({
            'error': 'Payment not found',
            'message': f'No payment exists with ID {pk}'
        }, status=status.HTTP_404_NOT_FOUND)
        
    except Exception as e:
        logger.error(f"❌ Admin resend invoice error: {str(e)}")
        logger.error(traceback.format_exc())
        return Response({
            'error': 'Failed to resend invoice',
            'message': str(e)
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


# ============================================================================
# ADMIN ANALYTICS VIEWS (Unchanged - keeping your existing code)
# ============================================================================

class AdminPaymentDetailView(generics.RetrieveAPIView):
    permission_classes = [permissions.IsAuthenticated, IsAdminUser]
    serializer_class = PaymentListSerializer
    queryset = Payment.objects.select_related('user', 'platform').prefetch_related('payment_webinars__webinar')

class PaymentOverviewView(generics.RetrieveAPIView):
    """Payment overview statistics for admin dashboard"""
    permission_classes = [permissions.IsAuthenticated, IsAdminUser]
    serializer_class = PaymentOverviewSerializer
    
    def get_object(self):
        platform = getattr(self.request, 'platform', None)
        payments = Payment.objects.all()
        if platform:
            payments = payments.filter(platform=platform)
        
        today_start = timezone.now().replace(hour=0, minute=0, second=0, microsecond=0)
        today_payments = payments.filter(created_at__gte=today_start, status='completed')
        today_revenue = today_payments.aggregate(total=Sum('amount'))['total'] or Decimal('0.00')
        today_transactions = today_payments.count()
        
        week_start = today_start - timezone.timedelta(days=today_start.weekday())
        week_payments = payments.filter(created_at__gte=week_start, status='completed')
        week_revenue = week_payments.aggregate(total=Sum('amount'))['total'] or Decimal('0.00')
        week_transactions = week_payments.count()
        
        month_start = today_start.replace(day=1)
        month_payments = payments.filter(created_at__gte=month_start, status='completed')
        month_revenue = month_payments.aggregate(total=Sum('amount'))['total'] or Decimal('0.00')
        month_transactions = month_payments.count()
        
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
        payments = Payment.objects.all()
        refund_requests = RefundRequest.objects.all()
        
        if platform:
            payments = payments.filter(platform=platform)
            refund_requests = refund_requests.filter(payment__platform=platform)
        
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
        
        total_refunded = refund_requests.filter(status__in=['processed', 'approved']).count()
        total_completed = payments.filter(status='completed').count()
        refund_rate = (total_refunded / total_completed * 100) if total_completed > 0 else 0
        
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
        payments = Payment.objects.all()
        refund_requests = RefundRequest.objects.all()
        
        if platform:
            payments = payments.filter(platform=platform)
            refund_requests = refund_requests.filter(payment__platform=platform)
        
        total_completed_payments = payments.filter(status='completed').count()
        total_refunded_payments = payments.filter(status='refunded').count()
        total_refunded_amount = refund_requests.filter(status__in=['processed', 'approved']).aggregate(
            total=Sum('refund_amount')
        )['total'] or Decimal('0.00')
        
        refund_rate = (total_refunded_payments / total_completed_payments * 100) if total_completed_payments > 0 else 0
        
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
    pagination_class = PageNumberPagination
    
    def get_queryset(self):
        queryset = Payment.objects.filter(
            user=self.request.user
        ).select_related('user', 'platform').prefetch_related('payment_webinars__webinar')
        platform = getattr(self.request, 'platform', None)
        if platform:
            queryset = queryset.filter(platform=platform)
        return queryset

class PaymentDetailView(generics.RetrieveAPIView):
    serializer_class = PaymentListSerializer
    permission_classes = [permissions.IsAuthenticated]
    lookup_field = 'invoice_number'
    lookup_url_kwarg = 'invoice_number'
    
    def get_queryset(self):
        queryset = Payment.objects.filter(
            user=self.request.user
        ).select_related('user', 'platform').prefetch_related('payment_webinars__webinar')
        platform = getattr(self.request, 'platform', None)
        if platform:
            queryset = queryset.filter(platform=platform)
        return queryset


# ============================================================================
# PAYMENT GATEWAY CONFIGURATION
# ============================================================================

@api_view(['GET'])
@permission_classes([permissions.AllowAny])
def get_available_payment_gateways(request):
    """
    ✅ Get available payment gateways with platform filtering
    - Global gateways (no platform assigned) → Available to ALL
    - Platform-specific gateways → Only available on that platform
    """
    # ✅ Get current platform from request
    platform = getattr(request, 'platform', None)
    
    # ✅ Filter gateways: Global OR platform-specific
    if platform:
        # Show gateways with NO platform (global) OR assigned to this platform
        gateways_db = PaymentGateway.objects.filter(
            is_active=True
        ).filter(
            Q(platform__isnull=True) | Q(platform=platform)  # ✅ FIXED: platform (singular)
        ).distinct().order_by('display_order')
        logger.info(f"🌐 Platform '{platform.name}' - Found {gateways_db.count()} available gateways")
    else:
        # No platform context → Show only global gateways
        gateways_db = PaymentGateway.objects.filter(
            is_active=True,
            platform__isnull=True  # ✅ FIXED: platform (singular)
        ).order_by('display_order')
        logger.info(f"🌍 No platform context - Showing {gateways_db.count()} global gateways")
    
    available_gateways = []
    for gateway in gateways_db:
        supported_currencies = gateway.supported_currencies or ['USD']
        if 'USD' not in supported_currencies:
            supported_currencies.insert(0, 'USD')
        
        # ✅ Build safe configuration (ONLY public keys)
        safe_config = {}
        if gateway.gateway_id == 'stripe':
            safe_config = {
                'publishable_key': gateway.configuration.get('publishable_key', '')
            }
        elif gateway.gateway_id == 'razorpay':
            safe_config = {
                'key_id': gateway.configuration.get('key_id', '')
            }
        elif gateway.gateway_id == 'paypal':
            safe_config = {
                'client_id': gateway.configuration.get('client_id', '')
            }
        
        # ✅ Check if gateway is global or platform-specific
        is_global = gateway.platform is None  # ✅ FIXED: platform (singular)
        assigned_platform = None
        if not is_global:
            assigned_platform = {
                'id': gateway.platform.platform_id,  # ✅ FIXED: platform (singular)
                'name': gateway.platform.name
            }
        
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
            'configuration': safe_config,
            # ✅ NEW: Platform availability info
            'availability': {
                'is_global': is_global,
                'platform': assigned_platform,  # ✅ FIXED: Single platform object
                'available_on_current_platform': True  # Already filtered
            }
        }
        available_gateways.append(gateway_info)
    
    # ✅ Get default gateway (first available)
    default_gateway = gateways_db.first()
    default_gateway_id = default_gateway.gateway_id if default_gateway else getattr(settings, 'DEFAULT_PAYMENT_GATEWAY', 'razorpay')
    
    return Response({
        'success': True,
        'gateways': available_gateways,
        'default_gateway': default_gateway_id,
        'current_platform': {
            'id': platform.platform_id if platform else None,
            'name': platform.name if platform else 'Global'
        },
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


# ============================================================================
# STRIPE CHECKOUT SESSION HELPER
# ============================================================================

def create_stripe_checkout_session(payment, webinar_items, gateway, return_url, cancel_url, billing_info, currency):
    """
    ✅ CREATE STRIPE CHECKOUT SESSION WITH MULTIPLE LINE ITEMS
    Does not interfere with PayPal/Razorpay
    """
    try:
        config = gateway.configuration
        stripe.api_key = config.get('secret_key')
        
        if not stripe.api_key:
            raise PaymentGatewayError('Stripe secret key not configured')
        
        logger.info(f"🔵 Creating Stripe Checkout Session...")
        logger.info(f"   Transaction: {payment.transaction_id}")
        logger.info(f"   Amount: {currency} {payment.amount}")
        logger.info(f"   Items: {len(webinar_items)}")
        
        # ✅ Build line items from webinars
        line_items = []
        for item in webinar_items:
            webinar = item['webinar']
            price = item['price']
            access_type = item['access_type']
            description = f"{access_type.replace('_', ' ').title()} Access"
            if webinar.scheduled_date:
                description += f" • {webinar.scheduled_date.strftime('%b %d, %Y')}"
            
            line_items.append({
                'price_data': {
                    'currency': currency.lower(),
                    'unit_amount': int(float(price) * 100),
                    'product_data': {
                        'name': webinar.title,
                        'description': description,
                        'metadata': {
                            'webinar_id': str(webinar.id),
                            'webinar_code': webinar.webinar_id,
                            'access_type': access_type
                        },
                    },
                },
                'quantity': 1,
            })
        
        # ✅ Create Checkout Session
        session = stripe.checkout.Session.create(
            payment_method_types=['card'],
            line_items=line_items,
            mode='payment',
            success_url=f"{return_url}?session_id={{CHECKOUT_SESSION_ID}}",  # ✅ Changed
            cancel_url=f"{cancel_url}?transaction_id={payment.transaction_id}",  # ✅ Changed
            client_reference_id=payment.transaction_id,
            customer_email=billing_info.get('email'),
            metadata={
                'transaction_id': payment.transaction_id,
                'payment_id': str(payment.id),
                'platform_id': payment.platform.platform_id if payment.platform else 'default',
                'user_id': str(payment.user.id),
            },
            billing_address_collection='required',
            phone_number_collection={'enabled': True},
        )
        
        # ✅ Save session info to payment
        payment.gateway_order_id = session.id
        payment.gateway_response = {
            'session_id': session.id,
            'checkout_url': session.url,
            'payment_status': session.payment_status,
            'created_at': session.created,
        }
        payment.save(update_fields=['gateway_order_id', 'gateway_response'])
        
        logger.info(f"✅ Stripe Checkout Session created: {session.id}")
        logger.info(f"   Checkout URL: {session.url}")
        
        return {
            'success': True,
            'payment': PaymentSerializer(payment).data,
            'gateway_order_id': session.id,
            'checkout_url': session.url,
            'gateway_config': {
                'publishable_key': config.get('publishable_key')
            }
        }
        
    except stripe.error.StripeError as e:
        logger.error(f"❌ Stripe error: {e}")
        payment.status = 'failed'
        payment.failure_reason = str(e)
        payment.save(update_fields=['status', 'failure_reason'])
        raise PaymentGatewayError(f"Stripe error: {str(e)}")


# ============================================================================
# CHECKOUT ENDPOINT (✅ COMPLETE WITH STRIPE)
# ============================================================================

@api_view(['POST'])
@permission_classes([permissions.IsAuthenticated])
def checkout(request):
    """
    ✅ COMPLETE CHECKOUT FUNCTION WITH STRIPE CHECKOUT SESSION
    Supports: Stripe (Checkout Session), Razorpay, PayPal
    """
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
        
        # ============================================
        # STEP 1: CALCULATE TOTAL & VALIDATE WEBINARS
        # ============================================
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
        
        # ============================================
        # STEP 2: CHECK FOR EXISTING PENDING PAYMENT
        # ============================================
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
        
        if existing_payment:
            logger.info(f"🔍 Found pending payment: {existing_payment.transaction_id}")
            existing_webinar_pks = set(
                existing_payment.payment_webinars.values_list('webinar__id', flat=True)
            )
            requested_webinar_pks = set(item['webinar'].id for item in webinar_items)
            
            if existing_webinar_pks == requested_webinar_pks:
                logger.info(f"♻️ ✅ REUSING existing pending payment: {existing_payment.transaction_id}")
                
                # ✅ STRIPE: Return existing checkout URL
                if payment_method == 'stripe':
                    checkout_url = existing_payment.gateway_response.get('checkout_url')
                    if checkout_url:
                        logger.info(f"✅ Returning existing Stripe checkout URL")
                        gateway_db = PaymentGateway.objects.filter(gateway_id='stripe', is_active=True).first()
                        return Response({
                            'success': True,
                            'message': 'Resuming existing payment',
                            'payment': PaymentSerializer(existing_payment).data,
                            'gateway_order_id': existing_payment.gateway_order_id,
                            'checkout_url': checkout_url,
                            'gateway_config': {
                                'publishable_key': gateway_db.configuration.get('publishable_key', '') if gateway_db else ''
                            }
                        })
                
                # ✅ RAZORPAY/PAYPAL: Return existing gateway order
                gateway = payment_gateway_manager.get_gateway(payment_method)
                if gateway:
                    return Response({
                        'success': True,
                        'message': 'Resuming existing payment',
                        'payment': PaymentSerializer(existing_payment).data,
                        'gateway_order_id': existing_payment.gateway_order_id,
                        'gateway_config': gateway.get_client_config()
                    })
        
        # ============================================
        # STEP 3: CREATE NEW PAYMENT
        # ============================================
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
            
            # ============================================
            # STEP 4: CREATE GATEWAY ORDER
            # ============================================
            try:
                # ✅ STRIPE CHECKOUT SESSION
                if payment_method == 'stripe':
                    logger.info(f"🔵 Processing Stripe Checkout Session...")
                    gateway_db = PaymentGateway.objects.filter(
                        gateway_id='stripe',
                        is_active=True
                    ).first()
                    
                    if not gateway_db:
                        raise PaymentGatewayError('Stripe gateway not configured')
                    
                    stripe_response = create_stripe_checkout_session(
                        payment=payment,
                        webinar_items=webinar_items,
                        gateway=gateway_db,
                        return_url=request.data.get('return_url'),
                        cancel_url=request.data.get('cancel_url'),
                        billing_info=request.data.get('billing_info', {}),
                        currency=currency
                    )
                    
                    return Response(stripe_response)
                
                # ✅ RAZORPAY / PAYPAL / OTHER GATEWAYS
                else:
                    gateway = payment_gateway_manager.get_gateway(payment_method)
                    if not gateway:
                        raise PaymentGatewayError(f'Payment gateway {payment_method} not available')
                    
                    order_data = {
                        'user_id': user.id,
                        'user_email': user.email,
                        'user_name': user.get_full_name() or user.email,
                        'platform_id': platform.platform_id if platform else 'default',
                        'transaction_id': payment.transaction_id,
                        'billing_info': request.data.get('billing_info', {}),
                        'notes': {
                            'transaction_id': payment.transaction_id,
                            'user_email': user.email,
                            'webinar_count': len(webinar_items)
                        }
                    }
                    
                    logger.info(f"📤 Creating gateway order for {payment_method}...")
                    gateway_response = gateway.create_order(total_amount, currency, order_data)
                    
                    payment.gateway_order_id = gateway_response.get('order_id')
                    payment.gateway_response = gateway_response
                    payment.save(update_fields=['gateway_order_id', 'gateway_response'])
                    
                    logger.info(f"📦 Gateway order created successfully:")
                    logger.info(f"   - Gateway Order ID: {payment.gateway_order_id}")
                    
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


# ============================================================================
# STRIPE SESSION DETAILS (✅ FOR STRIPE CHECKOUT RETURN)
# ============================================================================

@api_view(['GET'])
@permission_classes([permissions.IsAuthenticated])
def stripe_session_details(request, session_id):
    """
    ✅ Retrieve Stripe Checkout Session details
    Called from StripeReturnPage.jsx
    """
    try:
        platform = getattr(request, 'platform', None)
        user = request.user
        
        logger.info(f"🔍 Retrieving Stripe session: {session_id}")
        
        gateway_db = PaymentGateway.objects.filter(
            gateway_id='stripe',
            is_active=True
        ).first()
        
        if not gateway_db:
            return Response({
                'success': False,
                'error': 'Stripe gateway not configured'
            }, status=400)
        
        config = gateway_db.configuration
        stripe.api_key = config.get('secret_key')
        
        # ✅ Retrieve session from Stripe
        session = stripe.checkout.Session.retrieve(session_id)
        
        logger.info(f"✅ Retrieved Stripe session: {session.id}")
        logger.info(f"   Payment status: {session.payment_status}")
        logger.info(f"   Payment intent: {session.payment_intent}")
        
        # Find payment by session_id
        payment = Payment.objects.filter(
            gateway_order_id=session_id,
            user=user
        ).first()
        
        if not payment:
            transaction_id = session.metadata.get('transaction_id')
            if transaction_id:
                payment = Payment.objects.filter(
                    transaction_id=transaction_id,
                    user=user
                ).first()
        
        if not payment:
            return Response({
                'success': False,
                'error': 'Payment not found'
            }, status=404)
        
        # ✅ Update payment if paid
        if session.payment_status == 'paid' and payment.status == 'pending':
            logger.info(f"💳 Completing payment: {payment.transaction_id}")
            
            with transaction.atomic():
                if not payment.invoice_number:
                    payment.invoice_number = Payment.generate_unique_invoice_number(payment.platform)
                
                payment.status = 'completed'
                payment.gateway_payment_id = session.payment_intent
                payment.completed_at = timezone.now()
                payment.gateway_response.update({
                    'payment_intent': session.payment_intent,
                    'payment_status': session.payment_status,
                    'completed_at': timezone.now().isoformat(),
                })
                payment.save()
                
                logger.info(f"✅ Payment completed: {payment.transaction_id}")
                logger.info(f"   Invoice: {payment.invoice_number}")
                
                # ✅ Create enrollments
                payment_webinars = PaymentWebinar.objects.filter(
                    payment=payment
                ).select_related('webinar', 'webinar__speaker', 'webinar__speaker__user')
                
                frontend_url = f"https://{platform.domain}" if platform and platform.domain else settings.DEFAULT_FRONTEND_URL
                
                webinar_details = []
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
                    
                    webinar_slug = generate_slug(pw.webinar.title)
                    webinar_type = 'live-webinar' if pw.webinar.webinar_type == 'live' else 'recorded-webinar'
                    webinar_url = f"{frontend_url}/{webinar_type}/{pw.webinar.webinar_id}/{webinar_slug}"
                    
                    webinar_details.append({
                        'title': pw.webinar.title,
                        'instructor': pw.webinar.speaker.user.get_full_name() if pw.webinar.speaker else 'TBA',
                        'scheduled_date': pw.webinar.scheduled_date.strftime('%B %d, %Y') if pw.webinar.scheduled_date else 'On Demand',
                        'duration': f"{pw.webinar.duration} minutes" if pw.webinar.duration else 'Self-paced',
                        'webinar_url': webinar_url,
                    })
                
                # ✅ Send payment confirmation email
                try:
                    from apps.notifications.email_service import EmailService
                    
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
                    
                    bcc_list = platform.get_admin_emails_for_bcc() if platform else []
                    
                    EmailService.send_email(
                        subject=f'Payment Confirmed - {payment.transaction_id}',
                        template_name='payment_confirmation',
                        context=context,
                        recipient_list=[user.email],
                        platform=platform,
                        bcc=bcc_list
                    )
                    
                    logger.info(f"✅ Sent payment confirmation email to {user.email}")
                
                except Exception as e:
                    logger.error(f"❌ Failed to send email: {str(e)}")
        
        return Response({
            'success': True,
            'payment_status': session.payment_status,
            'amount_total': session.amount_total,
            'currency': session.currency,
            'payment': PaymentSerializer(payment).data
        })
    
    except stripe.error.StripeError as e:
        logger.error(f"❌ Stripe error: {e}")
        return Response({
            'success': False,
            'error': str(e)
        }, status=400)
    
    except Exception as e:
        logger.error(f"❌ Error: {e}", exc_info=True)
        return Response({
            'success': False,
            'error': str(e)
        }, status=500)


# ============================================================================
# VERIFY PAYMENT (✅ WORKS FOR RAZORPAY/PAYPAL - NOT NEEDED FOR STRIPE)
# ============================================================================

@api_view(['POST'])
@permission_classes([permissions.IsAuthenticated])
def verify_payment(request):
    """
    ✅ Verify payment for Razorpay/PayPal (and any non-Stripe gateway)
    Sends confirmation email synchronously like Stripe.
    """
    try:
        user = request.user
        platform = getattr(request, 'platform', None)
        payment_method = request.data.get('payment_method')
        transaction_id = request.data.get('transaction_id')
        payment_data = request.data.get('payment_data', {})
        
        if not payment_method or not transaction_id:
            return Response({
                'success': False,
                'error': 'Payment method and transaction ID are required'
            }, status=status.HTTP_400_BAD_REQUEST)
        
        # ✅ Stripe doesn't use this endpoint
        if payment_method == 'stripe':
            return Response({
                'success': False,
                'error': 'Stripe payments use session-based verification. Use /stripe/session/<session_id>/ instead.'
            }, status=status.HTTP_400_BAD_REQUEST)
        
        gateway = payment_gateway_manager.get_gateway(payment_method)
        if not gateway:
            logger.error(f"Gateway not found: {payment_method}")
            return Response({
                'success': False,
                'error': f'Payment gateway {payment_method} not configured'
            }, status=status.HTTP_400_BAD_REQUEST)
        
        payment = get_object_or_404(
            Payment.objects.select_related('user', 'platform'),
            transaction_id=transaction_id,
            user=user
        )
        
        logger.info(f"Verifying payment {transaction_id}")
        
        verification_result = gateway.verify_payment(payment_data)
        
        if verification_result.get('verified'):
            with transaction.atomic():
                if not payment.invoice_number:
                    payment.invoice_number = Payment.generate_unique_invoice_number(payment.platform)
                
                payment.status = 'completed'
                payment.gateway_payment_id = verification_result.get('payment_id', '')
                payment.completed_at = timezone.now()
                payment.save(update_fields=['invoice_number', 'status', 'gateway_payment_id', 'completed_at'])
                
                logger.info(f"✅ Payment verified: {transaction_id}")
                
                # Fetch webinar details for email & response
                payment_webinars = PaymentWebinar.objects.filter(
                    payment=payment
                ).select_related('webinar', 'webinar__speaker', 'webinar__speaker__user')
                
                frontend_url = f"https://www.{platform.domain}" if platform and platform.domain else getattr(settings, 'DEFAULT_FRONTEND_URL', 'https://www.peopleskilltraining.com')
                
                webinar_details = []
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
                
                # ✅ 🔥 SEND EMAIL SYNCHRONOUSLY — SAME AS STRIPE
                email_sent = False
                try:
                    from apps.notifications.email_service import EmailService
                    
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
                    
                    bcc_list = platform.get_admin_emails_for_bcc() if platform else []
                    
                    EmailService.send_email(
                        subject=f'Payment Confirmed - {payment.transaction_id}',
                        template_name='payment_confirmation',
                        context=context,
                        recipient_list=[user.email],
                        platform=platform,
                        bcc=bcc_list
                    )
                    
                    email_sent = True
                    logger.info(f"✅ Sent payment confirmation email to {user.email}")
                
                except Exception as e:
                    logger.error(f"❌ Failed to send email for {payment_method} payment: {str(e)}")
                
                return Response({
                    'success': True,
                    'message': 'Payment verified successfully',
                    'payment': PaymentSerializer(payment).data,
                    'webinars': webinar_details,
                    'email_sent': email_sent,
                })
        
        else:
            payment.status = 'failed'
            payment.failure_reason = verification_result.get('message', 'Verification failed')
            payment.save()
            
            logger.warning(f"❌ Payment verification failed: {transaction_id}")
            
            return Response({
                'success': False,
                'error': 'Payment verification failed',
                'details': verification_result.get('message')
            }, status=status.HTTP_400_BAD_REQUEST)
    
    except PaymentVerificationError as e:
        logger.error(f"Payment verification error: {str(e)}")
        return Response({'success': False, 'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)
    
    except Exception as e:
        logger.error(f"Unexpected error during payment verification: {str(e)}", exc_info=True)
        return Response({
            'success': False,
            'error': 'An unexpected error occurred'
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


# ============================================================================
# USER INVOICE DOWNLOAD (existing)
# ============================================================================

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
        if platform_id == 'compliancetrained':
            primary_color = '#008c9d'
            secondary_color = '#01bbc7'
            logo_url = platform.logo_url if platform and platform.logo_url else None
        elif platform_id == 'peopleskilltraining':
            primary_color = '#6b21a8'
            secondary_color = '#a855f7'
            logo_url = platform.logo_url if platform and platform.logo_url else None
        elif platform_id == 'workforceskilled':
            primary_color = '#295F2D'
            secondary_color = '#FFE67C'
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
        
        filename = f"{invoice_number}.pdf"
        
        response = HttpResponse(pdf, content_type='application/pdf')
        response['Content-Disposition'] = f'attachment; filename="{filename}"'
        
        return response
    
    except Exception as e:
        logger.error(f"Invoice generation error: {str(e)}", exc_info=True)
        return Response({'success': False, 'error': 'Failed to generate invoice'}, status=500)


# ============================================================================
# REFUND REQUEST VIEWS (Unchanged)
# ============================================================================

class RefundRequestListView(generics.ListCreateAPIView):
    serializer_class = RefundRequestSerializer
    permission_classes = [permissions.IsAuthenticated]
    
    def get_queryset(self):
        if hasattr(self.request.user, 'role') and self.request.user.role == 'admin':
            queryset = RefundRequest.objects.select_related(
                'payment',
                'payment__user',
                'processed_by'
            ).all()
        else:
            queryset = RefundRequest.objects.select_related(
                'payment',
                'payment__user',
                'processed_by'
            ).filter(payment__user=self.request.user)
        
        status_filter = self.request.query_params.get('status')
        if status_filter:
            queryset = queryset.filter(status=status_filter)
        
        date_from = self.request.query_params.get('date_from')
        date_to = self.request.query_params.get('date_to')
        if date_from:
            queryset = queryset.filter(requested_at__gte=date_from)
        if date_to:
            queryset = queryset.filter(requested_at__lte=date_to)
        
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
        
        refund.status = 'processed'
        refund.processed_by = request.user
        refund.processed_at = timezone.now()
        refund.save()
        
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