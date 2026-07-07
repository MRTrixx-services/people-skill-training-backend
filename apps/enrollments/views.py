from rest_framework import generics, permissions, status, filters
from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response
from django_filters.rest_framework import DjangoFilterBackend
from django.db.models import Count, Q, Avg, Sum
from django.utils import timezone
from datetime import timedelta

from apps.users.permissions import IsAdminOnly
from apps.webinars.models import Webinar
from .models import (
    Enrollment, EnrollmentFeedback, AttendanceLog, 
    Certificate, WaitlistEntry
)
from .serializers import (
    EnrollmentSerializer,
    EnrollmentCreateSerializer,
    EnrollmentFeedbackSerializer,
    AttendanceLogSerializer,
    CertificateSerializer,
    WaitlistEntrySerializer,
    WaitlistCreateSerializer,
    EnrollmentStatsSerializer,
    UserEnrollmentStatsSerializer,
    AttendanceTrackingSerializer
)


class EnrollmentListView(generics.ListAPIView):
    """List enrollments - Platform-filtered (admin only or user's own)"""
    
    serializer_class = EnrollmentSerializer
    permission_classes = [permissions.IsAuthenticated]
    filter_backends = [DjangoFilterBackend, filters.OrderingFilter]
    filterset_fields = ['status', 'access_type', 'certificate_issued']
    ordering = ['-enrolled_at']
    
    def get_queryset(self):
        queryset = Enrollment.objects.select_related(
            'user', 'webinar', 'platform'
        )
        
        platform = getattr(self.request, 'platform', None)
        
        if self.request.user.is_admin():
            # Admins see all or platform-filtered
            if platform and not self.request.user.is_superuser:
                queryset = queryset.filter(platform=platform)
            return queryset
        
        # Regular users see only their own
        queryset = queryset.filter(user=self.request.user)
        
        # Additional platform filter
        if platform:
            queryset = queryset.filter(platform=platform)
        
        return queryset


class EnrollmentDetailView(generics.RetrieveUpdateAPIView):
    """Enrollment detail view - Platform-aware"""
    
    serializer_class = EnrollmentSerializer
    permission_classes = [permissions.IsAuthenticated]
    
    def get_queryset(self):
        queryset = Enrollment.objects.select_related('user', 'webinar', 'platform')
        
        platform = getattr(self.request, 'platform', None)
        
        if self.request.user.is_admin():
            if platform and not self.request.user.is_superuser:
                queryset = queryset.filter(platform=platform)
            return queryset
        
        # User's own enrollments only
        queryset = queryset.filter(user=self.request.user)
        
        if platform:
            queryset = queryset.filter(platform=platform)
        
        return queryset


class EnrollmentCreateView(generics.CreateAPIView):
    """Create enrollment - Platform-aware"""
    
    serializer_class = EnrollmentCreateSerializer
    permission_classes = [permissions.IsAuthenticated]
    
    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        enrollment = serializer.save()
        
        # Return full enrollment data
        response_serializer = EnrollmentSerializer(enrollment, context={'request': request})
        return Response({
            'success': True,
            'enrollment': response_serializer.data,
            'message': 'Successfully enrolled in webinar'
        }, status=status.HTTP_201_CREATED)


class MyEnrollmentsView(generics.ListAPIView):
    """List current user's enrollments - Platform-filtered"""
    
    serializer_class = EnrollmentSerializer
    permission_classes = [permissions.IsAuthenticated]
    filter_backends = [DjangoFilterBackend, filters.OrderingFilter]
    filterset_fields = ['status', 'access_type']
    ordering = ['-enrolled_at']
    
    def get_queryset(self):
        queryset = Enrollment.objects.filter(
            user=self.request.user
        ).select_related('webinar', 'platform')
        
        # Platform filtering
        platform = getattr(self.request, 'platform', None)
        
        if platform:
            queryset = queryset.filter(platform=platform)
        
        return queryset


class UpcomingEnrollmentsView(generics.ListAPIView):
    """List user's upcoming enrollments - Platform-filtered"""
    
    serializer_class = EnrollmentSerializer
    permission_classes = [permissions.IsAuthenticated]
    
    def get_queryset(self):
        queryset = Enrollment.objects.filter(
            user=self.request.user,
            status='enrolled',
            webinar__scheduled_date__gt=timezone.now()
        ).select_related('webinar', 'platform').order_by('webinar__scheduled_date')
        
        # Platform filtering
        platform = getattr(self.request, 'platform', None)
        
        if platform:
            queryset = queryset.filter(platform=platform)
        
        return queryset


class EnrollmentFeedbackView(generics.CreateAPIView):
    """Submit enrollment feedback"""
    
    serializer_class = EnrollmentFeedbackSerializer
    permission_classes = [permissions.IsAuthenticated]
    
    def create(self, request, *args, **kwargs):
        enrollment_id = kwargs.get('enrollment_id')
        
        try:
            enrollment = Enrollment.objects.get(
                id=enrollment_id,
                user=request.user,
                status='attended'
            )
        except Enrollment.DoesNotExist:
            return Response({
                'success': False,
                'error': 'Enrollment not found or not attended'
            }, status=status.HTTP_404_NOT_FOUND)
        
        # Check if feedback already exists
        if hasattr(enrollment, 'detailed_feedback'):
            return Response({
                'success': False,
                'error': 'Feedback already submitted for this enrollment'
            }, status=status.HTTP_400_BAD_REQUEST)
        
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        feedback = serializer.save(enrollment=enrollment)
        
        # Update enrollment feedback status
        enrollment.feedback_submitted = True
        enrollment.would_recommend = feedback.would_recommend
        enrollment.save()
        
        return Response({
            'success': True,
            'feedback': serializer.data,
            'message': 'Feedback submitted successfully'
        }, status=status.HTTP_201_CREATED)


class CertificateListView(generics.ListAPIView):
    """List user's certificates - Platform-filtered"""
    
    serializer_class = CertificateSerializer
    permission_classes = [permissions.IsAuthenticated]
    ordering = ['-issued_at']
    
    def get_queryset(self):
        queryset = Certificate.objects.filter(
            enrollment__user=self.request.user
        ).select_related('enrollment', 'enrollment__webinar', 'enrollment__platform')
        
        # Platform filtering
        platform = getattr(self.request, 'platform', None)
        
        if platform:
            queryset = queryset.filter(enrollment__platform=platform)
        
        return queryset


class CertificateDetailView(generics.RetrieveAPIView):
    """Certificate detail view - Public for verification"""
    
    serializer_class = CertificateSerializer
    permission_classes = [permissions.AllowAny]  # For public verification
    lookup_field = 'certificate_id'
    
    def get_queryset(self):
        return Certificate.objects.select_related(
            'enrollment', 'enrollment__user', 'enrollment__webinar', 'enrollment__platform'
        )


class WaitlistCreateView(generics.CreateAPIView):
    """Join waitlist - Platform-aware"""
    
    serializer_class = WaitlistCreateSerializer
    permission_classes = [permissions.IsAuthenticated]
    
    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        waitlist_entry = serializer.save()
        
        response_serializer = WaitlistEntrySerializer(
            waitlist_entry, 
            context={'request': request}
        )
        return Response({
            'success': True,
            'waitlist_entry': response_serializer.data,
            'message': f'Added to waitlist at position {waitlist_entry.position}'
        }, status=status.HTTP_201_CREATED)


class MyWaitlistView(generics.ListAPIView):
    """List user's waitlist entries - Platform-filtered"""
    
    serializer_class = WaitlistEntrySerializer
    permission_classes = [permissions.IsAuthenticated]
    ordering = ['-joined_at']
    
    def get_queryset(self):
        queryset = WaitlistEntry.objects.filter(
            user=self.request.user,
            is_active=True
        ).select_related('webinar', 'platform')
        
        # Platform filtering
        platform = getattr(self.request, 'platform', None)
        
        if platform:
            queryset = queryset.filter(platform=platform)
        
        return queryset


@api_view(['POST'])
@permission_classes([permissions.IsAuthenticated])
def cancel_enrollment(request, enrollment_id):
    """Cancel enrollment"""
    
    try:
        enrollment = Enrollment.objects.get(
            id=enrollment_id,
            user=request.user
        )
    except Enrollment.DoesNotExist:
        return Response({
            'success': False,
            'error': 'Enrollment not found'
        }, status=status.HTTP_404_NOT_FOUND)
    
    # Check if cancellation is allowed
    if enrollment.status not in ['enrolled']:
        return Response({
            'success': False,
            'error': 'Cannot cancel this enrollment',
            'current_status': enrollment.status
        }, status=status.HTTP_400_BAD_REQUEST)
    
    # Check cancellation deadline (e.g., 24 hours before)
    if enrollment.webinar.scheduled_date:
        cancellation_deadline = enrollment.webinar.scheduled_date - timedelta(hours=24)
        if timezone.now() > cancellation_deadline:
            return Response({
                'success': False,
                'error': 'Cancellation deadline has passed'
            }, status=status.HTTP_400_BAD_REQUEST)
    
    enrollment.status = 'cancelled'
    enrollment.save()
    
    # TODO: Notify waitlist if applicable
    
    return Response({
        'success': True,
        'message': 'Enrollment cancelled successfully'
    }, status=status.HTTP_200_OK)


@api_view(['POST'])
@permission_classes([permissions.IsAuthenticated])
def track_attendance(request):
    """Track user attendance in real-time"""
    
    serializer = AttendanceTrackingSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)
    
    enrollment_id = serializer.validated_data['enrollment_id']
    action = serializer.validated_data['action']
    
    try:
        enrollment = Enrollment.objects.get(
            id=enrollment_id,
            user=request.user
        )
    except Enrollment.DoesNotExist:
        return Response({
            'success': False,
            'error': 'Enrollment not found'
        }, status=status.HTTP_404_NOT_FOUND)
    
    # Get client IP and user agent
    ip_address = request.META.get('HTTP_X_FORWARDED_FOR')
    if ip_address:
        ip_address = ip_address.split(',')[0].strip()
    else:
        ip_address = request.META.get('REMOTE_ADDR')
    
    user_agent = request.META.get('HTTP_USER_AGENT', '')
    
    # Create attendance log
    attendance_log = AttendanceLog.objects.create(
        enrollment=enrollment,
        action=action,
        ip_address=ip_address,
        user_agent=user_agent,
        session_id=serializer.validated_data.get('session_id', ''),
        connection_quality=serializer.validated_data.get('connection_quality', ''),
        device_info=serializer.validated_data.get('device_info', {})
    )
    
    # Update enrollment based on action
    if action == 'joined':
        enrollment.joined_at = timezone.now()
        if enrollment.status == 'enrolled':
            enrollment.mark_as_attended()
    elif action == 'left':
        enrollment.left_at = timezone.now()
        enrollment.calculate_attendance_duration()
        enrollment.calculate_completion_percentage()
    
    response_serializer = AttendanceLogSerializer(attendance_log, context={'request': request})
    return Response({
        'success': True,
        'attendance_log': response_serializer.data
    }, status=status.HTTP_201_CREATED)


@api_view(['GET'])
@permission_classes([permissions.IsAuthenticated, IsAdminOnly])
def enrollment_stats(request):
    """Get enrollment statistics - Platform-aware"""
    
    # Get platform from request
    platform = getattr(request, 'platform', None)
    
    # Base queryset
    queryset = Enrollment.objects.all()
    
    # Filter by platform if not superuser
    if platform and not request.user.is_superuser:
        queryset = queryset.filter(platform=platform)
    
    stats = {
        'total_enrollments': queryset.count(),
        'active_enrollments': queryset.filter(
            status__in=['enrolled', 'attended']
        ).count(),
        'completed_enrollments': queryset.filter(
            status='attended'
        ).count(),
        'cancelled_enrollments': queryset.filter(
            status='cancelled'
        ).count(),
        'total_revenue': queryset.aggregate(
            total=Sum('payment_amount')
        )['total'] or 0,
        'average_completion_rate': queryset.filter(
            status='attended'
        ).aggregate(
            avg=Avg('completion_percentage')
        )['avg'] or 0,
        'certificates_issued': Certificate.objects.filter(
            enrollment__platform=platform
        ).count() if platform else Certificate.objects.count(),
        'feedback_submitted': queryset.filter(
            feedback_submitted=True
        ).count(),
    }
    
    if platform:
        stats['platform'] = {
            'id': platform.id,
            'name': platform.name,
            'platform_id': platform.platform_id
        }
    
    serializer = EnrollmentStatsSerializer(stats)
    return Response({
        'success': True,
        'stats': serializer.data
    })


@api_view(['GET'])
@permission_classes([permissions.IsAuthenticated])
def user_enrollment_stats(request):
    """Get user's enrollment statistics - Platform-aware"""
    
    user = request.user
    platform = getattr(request, 'platform', None)
    
    # Base queryset
    enrollments = Enrollment.objects.filter(user=user)
    
    # Filter by platform if available
    if platform:
        enrollments = enrollments.filter(platform=platform)
    
    # Calculate favorite categories
    favorite_categories = list(
        enrollments.values('webinar__category__name').annotate(
            count=Count('webinar__category')
        ).order_by('-count')[:3].values_list('webinar__category__name', flat=True)
    )
    
    # Calculate total learning hours
    total_minutes = enrollments.aggregate(
        total=Sum('attendance_duration')
    )['total'] or 0
    total_hours = total_minutes // 60
    
    stats = {
        'total_enrollments': enrollments.count(),
        'attended_webinars': enrollments.filter(status='attended').count(),
        'missed_webinars': enrollments.filter(status='missed').count(),
        'certificates_earned': Certificate.objects.filter(
            enrollment__user=user,
            enrollment__platform=platform
        ).count() if platform else Certificate.objects.filter(enrollment__user=user).count(),
        'total_learning_hours': total_hours,
        'favorite_categories': favorite_categories,
        'average_completion_rate': enrollments.filter(
            status='attended'
        ).aggregate(
            avg=Avg('completion_percentage')
        )['avg'] or 0,
    }
    
    serializer = UserEnrollmentStatsSerializer(stats)
    return Response({
        'success': True,
        'stats': serializer.data
    })


@api_view(['POST'])
@permission_classes([permissions.IsAuthenticated])
def leave_waitlist(request, waitlist_id):
    """Leave waitlist"""
    
    try:
        waitlist_entry = WaitlistEntry.objects.get(
            id=waitlist_id,
            user=request.user,
            is_active=True
        )
    except WaitlistEntry.DoesNotExist:
        return Response({
            'success': False,
            'error': 'Waitlist entry not found'
        }, status=status.HTTP_404_NOT_FOUND)
    
    waitlist_entry.is_active = False
    waitlist_entry.save()
    
    return Response({
        'success': True,
        'message': 'Successfully left waitlist'
    }, status=status.HTTP_200_OK)
