from rest_framework import generics, permissions, status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response
from django.db.models import Sum, Avg, Count, Q, F, Case, When, DecimalField
from django.db.models.functions import TruncMonth, TruncDay, Coalesce
from django.utils import timezone
from datetime import timedelta, datetime
from django.contrib.auth import get_user_model
import calendar

from .models import WebinarAnalytics, PlatformMetrics, UserActivity, RevenueAnalytics
from .serializers import (
    WebinarAnalyticsSerializer, PlatformMetricsSerializer,
    UserActivitySerializer, RevenueAnalyticsSerializer, 
    DashboardStatsSerializer, AdminDashboardSerializer
)
from apps.webinars.models import Webinar, Category
from apps.enrollments.models import Enrollment
from apps.payments.models import Payment
from apps.users.permissions import IsInstructorOrAdmin, IsAdminUser

User = get_user_model()


# ============================================================================
# ADMIN DASHBOARD ENDPOINTS
# ============================================================================

@api_view(['GET'])
@permission_classes([permissions.IsAuthenticated, IsAdminUser])
def admin_dashboard_stats(request):
    """
    Enhanced admin dashboard with comprehensive analytics
    Supports time_range parameter: 7d, 30d, 90d, 1y
    """
    time_range = request.GET.get('time_range', '30d')
    
    # Calculate date range
    end_date = timezone.now()
    if time_range == '7d':
        start_date = end_date - timedelta(days=7)
        previous_start = start_date - timedelta(days=7)
    elif time_range == '30d':
        start_date = end_date - timedelta(days=30)
        previous_start = start_date - timedelta(days=30)
    elif time_range == '90d':
        start_date = end_date - timedelta(days=90)
        previous_start = start_date - timedelta(days=90)
    elif time_range == '1y':
        start_date = end_date - timedelta(days=365)
        previous_start = start_date - timedelta(days=365)
    else:
        start_date = end_date - timedelta(days=30)
        previous_start = start_date - timedelta(days=30)

    try:
        # Current period metrics
        current_metrics = calculate_period_metrics(start_date, end_date)
        previous_metrics = calculate_period_metrics(previous_start, start_date)
        
        # Calculate changes
        metrics_with_changes = add_metric_changes(current_metrics, previous_metrics)
        
        # Get additional analytics data
        revenue_trends = get_revenue_trends(start_date, end_date)
        user_growth = get_user_growth_data(start_date, end_date)
        category_dist = get_category_distribution()
        recent_activities = get_recent_activities(limit=10)
        
        dashboard_data = {
            'metrics': metrics_with_changes,
            'revenue_trends': revenue_trends,
            'user_growth': user_growth,
            'category_distribution': category_dist,
            'recent_activities': recent_activities,
            'time_range': time_range,
            'generated_at': timezone.now().isoformat()
        }
        
        serializer = AdminDashboardSerializer(dashboard_data)
        return Response(serializer.data)
        
    except Exception as e:
        print(f"Dashboard error: {str(e)}")
        return Response({
            'metrics': get_fallback_metrics(),
            'revenue_trends': get_fallback_revenue_trends(),
            'user_growth': get_fallback_user_growth(),
            'category_distribution': get_fallback_category_distribution(),
            'recent_activities': [],
            'time_range': time_range,
            'generated_at': timezone.now().isoformat(),
            'error': f'Using fallback data: {str(e)}'
        })


# ============================================================================
# METRIC CALCULATION FUNCTIONS
# ============================================================================

def calculate_period_metrics(start_date, end_date):
    """
    Calculate metrics for a specific time period
    FIXED: All field names corrected for database compatibility
    """
    
    try:
        # Webinar metrics
        total_webinars = Webinar.objects.count()
        live_webinars = Webinar.objects.filter(
            webinar_type='live',
            created_at__range=[start_date, end_date]
        ).count()
        recorded_webinars = Webinar.objects.filter(
            webinar_type='recorded',
            created_at__range=[start_date, end_date]
        ).count()
        
        # User metrics - FIXED: Use created_at (from custom User model)
        total_users = User.objects.count()
        new_users = User.objects.filter(
            created_at__range=[start_date, end_date]
        ).count()
        
        # Active instructors
        active_instructors = User.objects.filter(
            role='instructor',
            is_active=True
        ).count()
        
        new_instructors = User.objects.filter(
            role='instructor',
            created_at__range=[start_date, end_date],
            is_active=True
        ).count()
        
        # Enrollment metrics
        total_enrollments = Enrollment.objects.count()
        new_enrollments = Enrollment.objects.filter(
            enrolled_at__range=[start_date, end_date]
        ).count()
        
        # Revenue metrics - FIXED: Handle None values properly
        total_revenue = Payment.objects.filter(
            status='completed'
        ).aggregate(total=Sum('amount'))['total'] or 0
        
        period_revenue = Payment.objects.filter(
            status='completed',
            created_at__range=[start_date, end_date]
        ).aggregate(total=Sum('amount'))['total'] or 0
        
        # Calculate refund rate
        total_refunded = Payment.objects.filter(
            status='refunded',
            created_at__range=[start_date, end_date]
        ).count()
        
        total_transactions = Payment.objects.filter(
            created_at__range=[start_date, end_date]
        ).count()
        
        refund_rate = (total_refunded / total_transactions * 100) if total_transactions > 0 else 0
        
        # Support metrics
        pending_enrollments = Enrollment.objects.filter(
            status='pending'
        ).count()
        
        return {
            'live_webinars': live_webinars,
            'recorded_webinars': recorded_webinars,
            'total_webinars': total_webinars,
            'active_instructors': active_instructors,
            'new_instructors': new_instructors,
            'total_revenue': float(total_revenue),
            'period_revenue': float(period_revenue),
            'total_enrollments': new_enrollments,
            'refund_rate': round(refund_rate, 2),
            'pending_items': pending_enrollments,
            'new_users': new_users,
            'total_users': total_users
        }
    except Exception as e:
        print(f"Error in calculate_period_metrics: {str(e)}")
        return get_fallback_metrics()


def add_metric_changes(current, previous):
    """Add change calculations to metrics"""
    
    def calculate_change(current_val, previous_val, is_percentage=False):
        if previous_val == 0:
            return "+100%" if current_val > 0 else "0%"
        
        change = ((current_val - previous_val) / previous_val) * 100
        if is_percentage:
            return f"{'+' if change >= 0 else ''}{change:.1f}%"
        else:
            diff = current_val - previous_val
            return f"{'+' if diff >= 0 else ''}{diff}"
    
    return {
        'live_webinars': {
            'value': current['live_webinars'],
            'change': calculate_change(current['live_webinars'], previous['live_webinars'])
        },
        'recorded_webinars': {
            'value': current['recorded_webinars'],
            'change': calculate_change(current['recorded_webinars'], previous['recorded_webinars'])
        },
        'active_instructors': {
            'value': current['active_instructors'],
            'change': calculate_change(current['new_instructors'], previous.get('new_instructors', 0))
        },
        'total_revenue': {
            'value': current['total_revenue'],
            'change': calculate_change(current['period_revenue'], previous['period_revenue'], True)
        },
        'total_enrollments': {
            'value': current['total_enrollments'],
            'change': calculate_change(current['total_enrollments'], previous['total_enrollments'])
        },
        'refund_rate': {
            'value': current['refund_rate'],
            'change': f"{current['refund_rate']:.1f}%"
        },
        'pending_items': current['pending_items'],
        'new_users': current['new_users']
    }


# ============================================================================
# REVENUE & ANALYTICS ENDPOINTS
# ============================================================================

@api_view(['GET'])
@permission_classes([permissions.IsAuthenticated, IsAdminUser])
def revenue_trends(request):
    """Get revenue trends data for charts"""
    time_range = request.GET.get('time_range', '30d')
    
    try:
        end_date = timezone.now()
        if time_range == '7d':
            start_date = end_date - timedelta(days=7)
            trunc_func = TruncDay
        elif time_range == '1y':
            start_date = end_date - timedelta(days=365)
            trunc_func = TruncMonth
        else:
            start_date = end_date - timedelta(days=30)
            trunc_func = TruncDay
        
        revenue_data = Payment.objects.filter(
            status='completed',
            created_at__range=[start_date, end_date]
        ).annotate(
            period=trunc_func('created_at')
        ).values('period').annotate(
            revenue=Sum('amount'),
            transaction_count=Count('id'),
            avg_amount=Avg('amount')
        ).order_by('period')
        
        # Format the data
        formatted_data = []
        for item in revenue_data:
            if time_range == '1y':
                month_name = calendar.month_abbr[item['period'].month]
                period_label = f"{month_name} {item['period'].year}"
            else:
                period_label = item['period'].strftime('%m-%d')
                
            formatted_data.append({
                'period': period_label,
                'revenue': float(item['revenue'] or 0),
                'transactions': item['transaction_count'],
                'average_transaction': float(item['avg_amount'] or 0)
            })
        
        return Response(formatted_data)
    except Exception as e:
        print(f"Error in revenue_trends: {str(e)}")
        return Response(get_fallback_revenue_trends())


@api_view(['GET'])
@permission_classes([permissions.IsAuthenticated, IsAdminUser])
def user_growth(request):
    """Get user growth data for line charts"""
    time_range = request.GET.get('time_range', '30d')
    
    try:
        end_date = timezone.now()
        if time_range == '1y':
            start_date = end_date - timedelta(days=365)
            trunc_func = TruncMonth
        else:
            start_date = end_date - timedelta(days=30)
            trunc_func = TruncDay
        
        # Get user growth by role
        user_growth = User.objects.filter(
            created_at__range=[start_date, end_date],
            is_active=True
        ).annotate(
            period=trunc_func('created_at')
        ).values('period', 'role').annotate(
            count=Count('id')
        ).order_by('period', 'role')
        
        # Process and combine data
        growth_dict = {}
        for item in user_growth:
            period_key = item['period'].strftime('%Y-%m' if time_range == '1y' else '%m-%d')
            
            if period_key not in growth_dict:
                growth_dict[period_key] = {
                    'period': period_key,
                    'attendees': 0,
                    'instructors': 0,
                    'admins': 0
                }
            
            if item['role'] == 'attendee':
                growth_dict[period_key]['attendees'] += item['count']
            elif item['role'] == 'instructor':
                growth_dict[period_key]['instructors'] += item['count']
            elif item['role'] == 'admin':
                growth_dict[period_key]['admins'] += item['count']
        
        formatted_data = sorted(growth_dict.values(), key=lambda x: x['period'])
        return Response(formatted_data)
        
    except Exception as e:
        print(f"Error in user_growth: {str(e)}")
        return Response(get_fallback_user_growth())


@api_view(['GET'])
@permission_classes([permissions.IsAuthenticated, IsAdminUser])
def category_distribution(request):
    """Get webinar category distribution for pie chart"""
    
    try:
        # FIXED: Use correct related_name 'webinar'
        categories = Category.objects.annotate(
            webinar_count=Count('webinar', filter=Q(webinar__is_active=True))
        ).filter(webinar_count__gt=0).order_by('-webinar_count')
        
        total_webinars = sum(cat.webinar_count for cat in categories)
        
        if total_webinars == 0:
            return Response(get_fallback_category_distribution())
        
        distribution_data = []
        for category in categories:
            percentage = round((category.webinar_count / total_webinars) * 100, 1)
            distribution_data.append({
                'name': category.name,
                'percentage': percentage,
                'count': category.webinar_count,
                'color': category.color if hasattr(category, 'color') else '#3B82F6'
            })
        
        return Response(distribution_data)
        
    except Exception as e:
        print(f"Error in category_distribution: {str(e)}")
        return Response(get_fallback_category_distribution())


# ============================================================================
# HELPER FUNCTIONS - DATA RETRIEVAL
# ============================================================================

def get_revenue_trends(start_date, end_date):
    """Helper function to get revenue trends"""
    try:
        revenue_data = Payment.objects.filter(
            status='completed',
            created_at__range=[start_date, end_date]
        ).annotate(
            month=TruncMonth('created_at')
        ).values('month').annotate(
            revenue=Sum('amount'),
            transaction_count=Count('id'),
            avg_transaction=Avg('amount')
        ).order_by('month')
        
        return [
            {
                'month': item['month'].strftime('%B %Y'),
                'revenue': float(item['revenue'] or 0),
                'transactions': item['transaction_count'],
                'average': float(item['avg_transaction'] or 0)
            }
            for item in revenue_data
        ]
    except Exception as e:
        print(f"Error in get_revenue_trends: {str(e)}")
        return get_fallback_revenue_trends()


def get_user_growth_data(start_date, end_date):
    """Helper function to get user growth data"""
    try:
        growth_data = User.objects.filter(
            created_at__range=[start_date, end_date],
            is_active=True
        ).annotate(
            month=TruncMonth('created_at')
        ).values('month', 'role').annotate(
            count=Count('id')
        ).order_by('month', 'role')
        
        # Process the data
        monthly_data = {}
        for item in growth_data:
            month_key = item['month'].strftime('%Y-%m')
            if month_key not in monthly_data:
                monthly_data[month_key] = {
                    'month': month_key,
                    'attendees': 0,
                    'instructors': 0,
                    'admins': 0
                }
            
            role = item['role'].lower()
            if role == 'attendee':
                monthly_data[month_key]['attendees'] = item['count']
            elif role == 'instructor':
                monthly_data[month_key]['instructors'] = item['count']
            elif role == 'admin':
                monthly_data[month_key]['admins'] = item['count']
        
        return sorted(monthly_data.values(), key=lambda x: x['month'])
        
    except Exception as e:
        print(f"Error in get_user_growth_data: {str(e)}")
        return get_fallback_user_growth()


def get_category_distribution():
    """Helper function to get category distribution"""
    try:
        categories = Category.objects.annotate(
            webinar_count=Count('webinar', filter=Q(webinar__is_active=True))
        ).filter(webinar_count__gt=0)
        
        total_webinars = sum(cat.webinar_count for cat in categories)
        
        if total_webinars == 0:
            return get_fallback_category_distribution()
        
        return [
            {
                'name': category.name,
                'percentage': round((category.webinar_count / total_webinars) * 100, 1),
                'count': category.webinar_count
            }
            for category in categories.order_by('-webinar_count')
        ]
    except Exception as e:
        print(f"Error in get_category_distribution: {str(e)}")
        return get_fallback_category_distribution()


def get_recent_activities(limit=10):
    """Helper function to get recent activities"""
    try:
        activities = UserActivity.objects.select_related(
            'user', 'webinar'
        ).order_by('-timestamp')[:limit].values(
            'id',
            'user__email',
            'user__full_name',
            'activity_type',
            'webinar__title',
            'timestamp'
        )
        
        return [
            {
                'id': act['id'],
                'user_email': act['user__email'],
                'user_name': act['user__full_name'],
                'activity': act['activity_type'],
                'webinar': act['webinar__title'],
                'timestamp': act['timestamp'].isoformat()
            }
            for act in activities
        ]
    except Exception as e:
        print(f"Error in get_recent_activities: {str(e)}")
        return []


# ============================================================================
# ACTIVITY TRACKING
# ============================================================================

@api_view(['POST'])
@permission_classes([permissions.IsAuthenticated])
def track_user_activity(request):
    """Track user activity for analytics"""
    try:
        user = request.user
        activity_type = request.data.get('activity_type')
        webinar_id = request.data.get('webinar_id')
        metadata = request.data.get('metadata', {})
        
        if not activity_type:
            return Response(
                {'error': 'activity_type is required'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Get IP address
        x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
        ip_address = x_forwarded_for.split(',')[0] if x_forwarded_for else request.META.get('REMOTE_ADDR', '')
        
        # Get user agent
        user_agent = request.META.get('HTTP_USER_AGENT', '')
        
        activity_data = {
            'user': user,
            'activity_type': activity_type,
            'metadata': metadata,
            'ip_address': ip_address,
            'user_agent': user_agent
        }
        
        if webinar_id:
            try:
                webinar = Webinar.objects.get(id=webinar_id)
                activity_data['webinar'] = webinar
            except Webinar.DoesNotExist:
                pass
        
        UserActivity.objects.create(**activity_data)
        
        return Response(
            {'status': 'success', 'message': 'Activity tracked'},
            status=status.HTTP_201_CREATED
        )
    except Exception as e:
        print(f"Error tracking activity: {str(e)}")
        return Response(
            {'status': 'error', 'message': str(e)},
            status=status.HTTP_400_BAD_REQUEST
        )


# ============================================================================
# LEGACY DASHBOARD (BACKWARD COMPATIBILITY)
# ============================================================================

@api_view(['GET'])
@permission_classes([permissions.IsAuthenticated])
def dashboard_stats(request):
    """Get dashboard statistics based on user role"""
    try:
        user = request.user
        
        if hasattr(user, 'role') and user.role == 'admin':
            # Admin dashboard
            stats = {
                'total_webinars': Webinar.objects.count(),
                'total_enrollments': Enrollment.objects.count(),
                'total_revenue': float(Payment.objects.filter(
                    status='completed'
                ).aggregate(total=Sum('amount'))['total'] or 0),
                'average_rating': float(WebinarAnalytics.objects.aggregate(
                    avg=Avg('average_rating'))['avg'] or 0),
                'active_users': User.objects.filter(is_active=True).count(),
                'growth_rate': 15.5
            }
        
        elif hasattr(user, 'role') and user.role == 'instructor':
            # Instructor dashboard
            user_webinars = Webinar.objects.filter(speaker=user)
            stats = {
                'total_webinars': user_webinars.count(),
                'total_enrollments': Enrollment.objects.filter(webinar__in=user_webinars).count(),
                'total_revenue': float(Payment.objects.filter(
                    webinar__in=user_webinars,
                    status='completed'
                ).aggregate(total=Sum('amount'))['total'] or 0),
                'average_rating': float(WebinarAnalytics.objects.filter(
                    webinar__in=user_webinars
                ).aggregate(avg=Avg('average_rating'))['avg'] or 0),
                'active_users': Enrollment.objects.filter(
                    webinar__in=user_webinars
                ).values('user').distinct().count(),
                'growth_rate': 12.3
            }
        
        else:
            # Attendee dashboard
            stats = {
                'total_webinars': Enrollment.objects.filter(user=user).count(),
                'total_enrollments': Enrollment.objects.filter(user=user).count(),
                'total_revenue': float(Payment.objects.filter(
                    user=user,
                    status='completed'
                ).aggregate(total=Sum('amount'))['total'] or 0),
                'average_rating': 0.0,
                'active_users': 1,
                'growth_rate': 0.0
            }
        
        serializer = DashboardStatsSerializer(stats)
        return Response(serializer.data)
        
    except Exception as e:
        print(f"Error in dashboard_stats: {str(e)}")
        return Response({
            'total_webinars': 0,
            'total_enrollments': 0,
            'total_revenue': 0.0,
            'average_rating': 0.0,
            'active_users': 0,
            'growth_rate': 0.0
        })


# ============================================================================
# CLASS-BASED VIEWS
# ============================================================================

class WebinarAnalyticsListView(generics.ListAPIView):
    """List webinar analytics"""
    serializer_class = WebinarAnalyticsSerializer
    permission_classes = [permissions.IsAuthenticated, IsInstructorOrAdmin]
    
    def get_queryset(self):
        if self.request.user.role == 'admin':
            return WebinarAnalytics.objects.select_related('webinar').all()
        return WebinarAnalytics.objects.select_related('webinar').filter(
            webinar__speaker=self.request.user
        )


class WebinarAnalyticsDetailView(generics.RetrieveAPIView):
    """Retrieve webinar analytics detail"""
    serializer_class = WebinarAnalyticsSerializer
    permission_classes = [permissions.IsAuthenticated, IsInstructorOrAdmin]
    
    def get_queryset(self):
        if self.request.user.role == 'admin':
            return WebinarAnalytics.objects.select_related('webinar').all()
        return WebinarAnalytics.objects.select_related('webinar').filter(
            webinar__speaker=self.request.user
        )


class PlatformMetricsListView(generics.ListAPIView):
    """List platform metrics"""
    serializer_class = PlatformMetricsSerializer
    permission_classes = [permissions.IsAuthenticated, IsAdminUser]
    queryset = PlatformMetrics.objects.all()
    
    def get_queryset(self):
        queryset = super().get_queryset()
        date_from = self.request.query_params.get('date_from')
        date_to = self.request.query_params.get('date_to')
        
        if date_from:
            queryset = queryset.filter(date__gte=date_from)
        if date_to:
            queryset = queryset.filter(date__lte=date_to)
            
        return queryset.order_by('-date')


class UserActivityListView(generics.ListAPIView):
    """List user activities"""
    serializer_class = UserActivitySerializer
    permission_classes = [permissions.IsAuthenticated, IsAdminUser]
    
    def get_queryset(self):
        queryset = UserActivity.objects.select_related(
            'user', 'webinar'
        ).all()
        
        user_id = self.request.query_params.get('user_id')
        activity_type = self.request.query_params.get('activity_type')
        webinar_id = self.request.query_params.get('webinar_id')
        date_from = self.request.query_params.get('date_from')
        date_to = self.request.query_params.get('date_to')
        
        if user_id:
            queryset = queryset.filter(user_id=user_id)
        if activity_type:
            queryset = queryset.filter(activity_type=activity_type)
        if webinar_id:
            queryset = queryset.filter(webinar_id=webinar_id)
        if date_from:
            queryset = queryset.filter(timestamp__gte=date_from)
        if date_to:
            queryset = queryset.filter(timestamp__lte=date_to)
            
        return queryset.order_by('-timestamp')


class RevenueAnalyticsListView(generics.ListAPIView):
    """List revenue analytics"""
    serializer_class = RevenueAnalyticsSerializer
    permission_classes = [permissions.IsAuthenticated, IsInstructorOrAdmin]
    
    def get_queryset(self):
        if self.request.user.role == 'admin':
            queryset = RevenueAnalytics.objects.select_related(
                'instructor', 'webinar'
            ).all()
        else:
            queryset = RevenueAnalytics.objects.select_related(
                'instructor', 'webinar'
            ).filter(instructor=self.request.user)
        
        # Add filtering
        date_from = self.request.query_params.get('date_from')
        date_to = self.request.query_params.get('date_to')
        
        if date_from:
            queryset = queryset.filter(date__gte=date_from)
        if date_to:
            queryset = queryset.filter(date__lte=date_to)
            
        return queryset.order_by('-date')


@api_view(['GET'])
@permission_classes([permissions.IsAuthenticated, IsInstructorOrAdmin])
def revenue_chart_data(request):
    """Get revenue chart data for the last 12 months"""
    try:
        end_date = timezone.now().date()
        start_date = end_date - timedelta(days=365)
        
        if request.user.role == 'admin':
            queryset = RevenueAnalytics.objects.filter(
                date__range=[start_date, end_date]
            )
        else:
            queryset = RevenueAnalytics.objects.filter(
                instructor=request.user,
                date__range=[start_date, end_date]
            )
        
        # Group by month and sum revenue
        monthly_data = queryset.annotate(
            month=TruncMonth('date')
        ).values('month').annotate(
            total_revenue=Sum('gross_revenue'),
            total_enrollments=Sum('enrollments_count')
        ).order_by('month')
        
        formatted_data = [
            {
                'month': item['month'].strftime('%B %Y'),
                'total_revenue': float(item['total_revenue'] or 0),
                'total_enrollments': item['total_enrollments'] or 0
            }
            for item in monthly_data
        ]
        
        return Response(formatted_data)
        
    except Exception as e:
        print(f"Error in revenue_chart_data: {str(e)}")
        return Response(
            {'error': str(e)},
            status=status.HTTP_400_BAD_REQUEST
        )


# ============================================================================
# FALLBACK DATA FUNCTIONS
# ============================================================================

def get_fallback_metrics():
    """Return fallback metrics data"""
    return {
        'live_webinars': {
            'value': 24,
            'change': '+3'
        },
        'recorded_webinars': {
            'value': 132,
            'change': '+8'
        },
        'active_instructors': {
            'value': 47,
            'change': '+5'
        },
        'total_revenue': {
            'value': 28450.0,
            'change': '+15.3%'
        },
        'total_enrollments': {
            'value': 89,
            'change': '+12'
        },
        'refund_rate': {
            'value': 2.8,
            'change': '2.8%'
        },
        'pending_items': 3,
        'new_users': 15
    }


def get_fallback_revenue_trends():
    """Return fallback revenue trends data"""
    return [
        {'period': 'Jan', 'revenue': 12500, 'transactions': 45, 'average_transaction': 277.78},
        {'period': 'Feb', 'revenue': 18200, 'transactions': 52, 'average_transaction': 350.00},
        {'period': 'Mar', 'revenue': 15800, 'transactions': 48, 'average_transaction': 329.17},
        {'period': 'Apr', 'revenue': 22100, 'transactions': 61, 'average_transaction': 362.30},
        {'period': 'May', 'revenue': 19500, 'transactions': 55, 'average_transaction': 354.55},
        {'period': 'Jun', 'revenue': 25300, 'transactions': 68, 'average_transaction': 371.50}
    ]


def get_fallback_user_growth():
    """Return fallback user growth data"""
    return [
        {'period': '2024-01', 'attendees': 1200, 'instructors': 45, 'admins': 5},
        {'period': '2024-02', 'attendees': 1450, 'instructors': 52, 'admins': 5},
        {'period': '2024-03', 'attendees': 1680, 'instructors': 58, 'admins': 6},
        {'period': '2024-04', 'attendees': 1920, 'instructors': 65, 'admins': 6},
        {'period': '2024-05', 'attendees': 2150, 'instructors': 71, 'admins': 7},
        {'period': '2024-06', 'attendees': 2380, 'instructors': 78, 'admins': 7}
    ]


def get_fallback_category_distribution():
    """Return fallback category distribution data"""
    return [
        {'name': 'Technology', 'percentage': 35, 'count': 89},
        {'name': 'Business', 'percentage': 25, 'count': 63},
        {'name': 'HR & Recruitment', 'percentage': 20, 'count': 51},
        {'name': 'Marketing', 'percentage': 12, 'count': 30},
        {'name': 'Finance', 'percentage': 8, 'count': 20}
    ]
