from rest_framework import generics, permissions, status, filters
from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response
from django_filters.rest_framework import DjangoFilterBackend
from django.db.models import Avg, Sum, Count, Q
from django.utils import timezone
from datetime import datetime, timedelta

from .models import (
    AttendeeProfile, 
    AttendeeNotificationSettings, 
    AttendeeSecuritySettings,
    AttendeeActivity,
    AttendeeLearningPath
)
from .serializers import (
    AttendeeProfileSerializer,
    AttendeeProfileUpdateSerializer,
    AttendeeListSerializer,
    AttendeeActivitySerializer,
    AttendeeLearningPathSerializer,
    AttendeeStatsSerializer
)
from apps.users.permissions import IsOwnerOrAdmin


class AttendeeListView(generics.ListAPIView):
    """List all attendees (admin only) - Platform-filtered"""
    
    serializer_class = AttendeeListSerializer
    permission_classes = [permissions.IsAuthenticated, permissions.IsAdminUser]
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_fields = ['skill_level', 'language', 'show_profile_publicly']
    search_fields = ['user__first_name', 'user__last_name', 'user__email', 'interests']
    ordering_fields = ['member_since', 'total_enrollments', 'completed_webinars', 'total_hours_learned']
    ordering = ['-member_since']
    
    def get_queryset(self):
        queryset = AttendeeProfile.objects.select_related('user', 'platform').filter(user__is_active=True)
        
        # Platform filtering
        platform = getattr(self.request, 'platform', None)
        
        if platform and not self.request.user.is_superuser:
            # Only show attendees from this platform
            queryset = queryset.filter(platform=platform)
        
        return queryset


class AttendeeDetailView(generics.RetrieveAPIView):
    """Get attendee details - Platform-aware"""
    
    serializer_class = AttendeeProfileSerializer
    permission_classes = [permissions.IsAuthenticated, IsOwnerOrAdmin]
    
    def get_queryset(self):
        queryset = AttendeeProfile.objects.select_related(
            'user', 'platform', 'notification_settings', 'security_settings'
        )
        
        # Platform filtering
        platform = getattr(self.request, 'platform', None)
        
        if platform and not self.request.user.is_superuser:
            queryset = queryset.filter(platform=platform)
        
        return queryset


class AttendeeProfileView(generics.RetrieveUpdateAPIView):
    """Get and update attendee profile"""
    
    serializer_class = AttendeeProfileUpdateSerializer
    permission_classes = [permissions.IsAuthenticated]
    
    def get_object(self):
        # Get platform from request or user
        platform = getattr(self.request, 'platform', None) or self.request.user.platform
        
        if not platform:
            from rest_framework.exceptions import ValidationError
            raise ValidationError({'error': 'No platform associated with user'})
        
        # Get or create attendee profile for current user
        attendee_profile, created = AttendeeProfile.objects.get_or_create(
            user=self.request.user,
            defaults={
                'user': self.request.user,
                'platform': platform
            }
        )
        return attendee_profile
    
    def get_serializer_class(self):
        if self.request.method == 'GET':
            return AttendeeProfileSerializer
        return AttendeeProfileUpdateSerializer


class AttendeePublicProfileView(generics.RetrieveAPIView):
    """Get public attendee profile - Platform-filtered"""
    
    serializer_class = AttendeeProfileSerializer
    permission_classes = [permissions.AllowAny]
    lookup_field = 'id'
    
    def get_queryset(self):
        queryset = AttendeeProfile.objects.select_related('user', 'platform').filter(
            user__is_active=True, 
            show_profile_publicly=True
        )
        
        # Platform filtering
        platform = getattr(self.request, 'platform', None)
        
        if platform:
            queryset = queryset.filter(platform=platform)
        
        return queryset


class AttendeeActivityListView(generics.ListCreateAPIView):
    """List and create attendee activities"""
    
    serializer_class = AttendeeActivitySerializer
    permission_classes = [permissions.IsAuthenticated]
    filter_backends = [DjangoFilterBackend, filters.OrderingFilter]
    filterset_fields = ['activity_type']
    ordering = ['-created_at']
    
    def get_queryset(self):
        if hasattr(self.request.user, 'attendee_profile'):
            return AttendeeActivity.objects.filter(
                attendee=self.request.user.attendee_profile
            )
        return AttendeeActivity.objects.none()
    
    def perform_create(self, serializer):
        if hasattr(self.request.user, 'attendee_profile'):
            serializer.save(
                attendee=self.request.user.attendee_profile,
                ip_address=self.request.META.get('REMOTE_ADDR'),
                user_agent=self.request.META.get('HTTP_USER_AGENT', '')
            )


class AttendeeLearningPathListView(generics.ListCreateAPIView):
    """List and create learning paths"""
    
    serializer_class = AttendeeLearningPathSerializer
    permission_classes = [permissions.IsAuthenticated]
    filter_backends = [DjangoFilterBackend, filters.OrderingFilter]
    filterset_fields = ['status']
    ordering = ['-created_at']
    
    def get_queryset(self):
        if hasattr(self.request.user, 'attendee_profile'):
            return AttendeeLearningPath.objects.filter(
                attendee=self.request.user.attendee_profile
            )
        return AttendeeLearningPath.objects.none()
    
    def perform_create(self, serializer):
        if hasattr(self.request.user, 'attendee_profile'):
            serializer.save(attendee=self.request.user.attendee_profile)


class AttendeeLearningPathDetailView(generics.RetrieveUpdateDestroyAPIView):
    """Learning path detail view"""
    
    serializer_class = AttendeeLearningPathSerializer
    permission_classes = [permissions.IsAuthenticated, IsOwnerOrAdmin]
    
    def get_queryset(self):
        if hasattr(self.request.user, 'attendee_profile'):
            return AttendeeLearningPath.objects.filter(
                attendee=self.request.user.attendee_profile
            )
        return AttendeeLearningPath.objects.none()


@api_view(['GET'])
@permission_classes([permissions.IsAuthenticated])
def current_attendee(request):
    """Get current attendee profile"""
    
    try:
        attendee_profile = AttendeeProfile.objects.select_related(
            'user', 'platform', 'notification_settings', 'security_settings'
        ).get(user=request.user)
        serializer = AttendeeProfileSerializer(attendee_profile, context={'request': request})
        return Response({
            'success': True,
            'attendee': serializer.data
        })
    except AttendeeProfile.DoesNotExist:
        # Create attendee profile if it doesn't exist
        platform = getattr(request, 'platform', None) or request.user.platform
        
        if not platform:
            return Response({
                'success': False,
                'error': 'No platform associated with user'
            }, status=status.HTTP_400_BAD_REQUEST)
        
        attendee_profile = AttendeeProfile.objects.create(
            user=request.user,
            platform=platform
        )
        serializer = AttendeeProfileSerializer(attendee_profile, context={'request': request})
        return Response({
            'success': True,
            'attendee': serializer.data,
            'created': True
        }, status=status.HTTP_201_CREATED)


@api_view(['GET'])
@permission_classes([permissions.IsAuthenticated, permissions.IsAdminUser])
def attendee_stats(request):
    """Get attendee statistics (admin only) - Platform-aware"""
    
    now = timezone.now()
    last_month = now - timedelta(days=30)
    
    # Get platform from request
    platform = getattr(request, 'platform', None)
    
    # Base queryset
    queryset = AttendeeProfile.objects.all()
    
    # Filter by platform if not superuser
    if platform and not request.user.is_superuser:
        queryset = queryset.filter(platform=platform)
    
    # Basic counts
    total_attendees = queryset.count()
    active_attendees = queryset.filter(
        user__is_active=True,
        activities__created_at__gte=last_month
    ).distinct().count()
    new_this_month = queryset.filter(
        created_at__gte=last_month
    ).count()
    
    # Averages (handle division by zero)
    total_enroll = queryset.aggregate(total=Sum('total_enrollments'))['total'] or 0
    total_complete = queryset.aggregate(total=Sum('completed_webinars'))['total'] or 0
    avg_completion_rate = (total_complete / total_enroll * 100) if total_enroll > 0 else 0
    
    # Totals
    total_hours = queryset.aggregate(
        total=Sum('total_hours_learned')
    )['total'] or 0
    
    total_certificates = queryset.aggregate(
        total=Sum('certificates_earned')
    )['total'] or 0
    
    # Top interests
    all_interests = []
    for profile in queryset.exclude(interests=[]):
        all_interests.extend(profile.interests)
    
    from collections import Counter
    interest_counts = Counter(all_interests)
    top_interests = [
        {'name': interest, 'count': count} 
        for interest, count in interest_counts.most_common(10)
    ]
    
    stats = {
        'total_attendees': total_attendees,
        'active_attendees': active_attendees,
        'new_this_month': new_this_month,
        'average_completion_rate': round(avg_completion_rate, 2),
        'total_hours_learned': total_hours,
        'certificates_issued': total_certificates,
        'top_interests': top_interests,
    }
    
    if platform:
        stats['platform'] = {
            'id': platform.id,
            'name': platform.name,
            'platform_id': platform.platform_id
        }
    
    serializer = AttendeeStatsSerializer(stats)
    return Response({
        'success': True,
        'stats': serializer.data
    })


@api_view(['POST'])
@permission_classes([permissions.IsAuthenticated])
def log_attendee_activity(request):
    """Log attendee activity"""
    
    try:
        attendee_profile = request.user.attendee_profile
    except AttendeeProfile.DoesNotExist:
        return Response({
            'success': False,
            'error': 'Attendee profile not found'
        }, status=status.HTTP_404_NOT_FOUND)
    
    activity_type = request.data.get('activity_type')
    description = request.data.get('description', '')
    metadata = request.data.get('metadata', {})
    
    if not activity_type:
        return Response({
            'success': False,
            'error': 'activity_type is required'
        }, status=status.HTTP_400_BAD_REQUEST)
    
    activity = AttendeeActivity.objects.create(
        attendee=attendee_profile,
        activity_type=activity_type,
        description=description,
        metadata=metadata,
        ip_address=request.META.get('REMOTE_ADDR'),
        user_agent=request.META.get('HTTP_USER_AGENT', '')
    )
    
    serializer = AttendeeActivitySerializer(activity)
    return Response({
        'success': True,
        'activity': serializer.data
    }, status=status.HTTP_201_CREATED)

@api_view(['GET'])
@permission_classes([permissions.AllowAny])
def public_attendees(request):
    """Get public attendee profiles - Platform-filtered"""
    
    # Base queryset
    queryset = AttendeeProfile.objects.select_related('user', 'platform').filter(
        user__is_active=True,
        show_profile_publicly=True
    )
    
    # Platform filtering
    platform = getattr(request, 'platform', None)
    
    if platform:
        queryset = queryset.filter(platform=platform)
    
    attendees = queryset.order_by('-total_hours_learned')[:20]
    
    serializer = AttendeeListSerializer(attendees, many=True, context={'request': request})
    return Response({
        'success': True,
        'count': len(attendees),  # ✅ Fixed
        'attendees': serializer.data
    })
