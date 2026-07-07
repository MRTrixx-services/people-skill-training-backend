from rest_framework import generics, permissions, status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response
from django.shortcuts import get_object_or_404
from django.utils import timezone
from django.db.models import Count, Q

from .models import Notification, NotificationTemplate, NotificationPreference
from .serializers import (
    NotificationSerializer, NotificationTemplateSerializer,
    NotificationPreferenceSerializer, NotificationCreateSerializer,
    NotificationStatsSerializer
)
from apps.users.permissions import IsAdminUser


class NotificationListView(generics.ListAPIView):
    """List user's notifications - Platform-filtered"""
    
    serializer_class = NotificationSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        queryset = Notification.objects.filter(
            user=self.request.user
        ).select_related('template', 'webinar', 'platform')
        
        # ✅ Platform filtering
        platform = getattr(self.request, 'platform', None)
        if platform:
            queryset = queryset.filter(platform=platform)
        
        return queryset.order_by('-created_at')


class NotificationDetailView(generics.RetrieveUpdateAPIView):
    """Notification detail - Platform-aware"""
    
    serializer_class = NotificationSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        queryset = Notification.objects.filter(
            user=self.request.user
        ).select_related('template', 'webinar', 'platform')
        
        # ✅ Platform filtering
        platform = getattr(self.request, 'platform', None)
        if platform:
            queryset = queryset.filter(platform=platform)
        
        return queryset

    def patch(self, request, *args, **kwargs):
        """Mark notification as read"""
        notification = self.get_object()
        if 'read' in request.data and request.data['read']:
            notification.status = 'read'
            notification.read_at = timezone.now()
            notification.save()
        return self.partial_update(request, *args, **kwargs)


@api_view(['POST'])
@permission_classes([permissions.IsAuthenticated])
def mark_all_read(request):
    """Mark all notifications as read for the current user - Platform-filtered"""
    
    queryset = Notification.objects.filter(
        user=request.user,
        status__in=['sent', 'pending']
    )
    
    # ✅ Platform filtering
    platform = getattr(request, 'platform', None)
    if platform:
        queryset = queryset.filter(platform=platform)
    
    updated = queryset.update(
        status='read',
        read_at=timezone.now()
    )
    
    return Response({
        'success': True,
        'message': f'{updated} notifications marked as read'
    })


@api_view(['GET'])
@permission_classes([permissions.IsAuthenticated])
def unread_count(request):
    """Get count of unread notifications - Platform-filtered"""
    
    queryset = Notification.objects.filter(
        user=request.user,
        status__in=['sent', 'pending']
    )
    
    # ✅ Platform filtering
    platform = getattr(request, 'platform', None)
    if platform:
        queryset = queryset.filter(platform=platform)
    
    count = queryset.count()
    
    return Response({
        'success': True,
        'unread_count': count
    })


class NotificationPreferenceView(generics.RetrieveUpdateAPIView):
    """Get/update notification preferences"""
    
    serializer_class = NotificationPreferenceSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_object(self):
        preference, created = NotificationPreference.objects.get_or_create(
            user=self.request.user
        )
        return preference


# Admin views
class NotificationTemplateListView(generics.ListCreateAPIView):
    """List/create notification templates - Platform-filtered"""
    
    serializer_class = NotificationTemplateSerializer
    permission_classes = [permissions.IsAuthenticated, IsAdminUser]
    
    def get_queryset(self):
        queryset = NotificationTemplate.objects.all()
        
        # ✅ Platform filtering for admins
        platform = getattr(self.request, 'platform', None)
        if platform and not self.request.user.is_superuser:
            # Show global templates and platform-specific templates
            queryset = queryset.filter(
                Q(platform__isnull=True) | Q(platform=platform)
            )
        
        return queryset.select_related('platform')


class NotificationTemplateDetailView(generics.RetrieveUpdateDestroyAPIView):
    """Template detail view - Platform-aware"""
    
    serializer_class = NotificationTemplateSerializer
    permission_classes = [permissions.IsAuthenticated, IsAdminUser]
    
    def get_queryset(self):
        queryset = NotificationTemplate.objects.all()
        
        # ✅ Platform filtering
        platform = getattr(self.request, 'platform', None)
        if platform and not self.request.user.is_superuser:
            queryset = queryset.filter(
                Q(platform__isnull=True) | Q(platform=platform)
            )
        
        return queryset.select_related('platform')


class AdminNotificationListView(generics.ListCreateAPIView):
    """Admin notification list - Platform-filtered"""
    
    permission_classes = [permissions.IsAuthenticated, IsAdminUser]
    
    def get_serializer_class(self):
        if self.request.method == 'POST':
            return NotificationCreateSerializer
        return NotificationSerializer
    
    def get_queryset(self):
        queryset = Notification.objects.select_related(
            'user', 'template', 'platform', 'webinar'
        )
        
        # ✅ Platform filtering for admins
        platform = getattr(self.request, 'platform', None)
        if platform and not self.request.user.is_superuser:
            queryset = queryset.filter(platform=platform)
        
        return queryset.order_by('-created_at')


@api_view(['POST'])
@permission_classes([permissions.IsAuthenticated, IsAdminUser])
def send_bulk_notification(request):
    """Send notification to multiple users - Platform-aware"""
    
    user_ids = request.data.get('user_ids', [])
    template_id = request.data.get('template_id')
    title = request.data.get('title')
    message = request.data.get('message')
    
    if not all([user_ids, template_id, title, message]):
        return Response({
            'success': False,
            'error': 'user_ids, template_id, title, and message are required'
        }, status=status.HTTP_400_BAD_REQUEST)
    
    try:
        template = NotificationTemplate.objects.get(id=template_id)
    except NotificationTemplate.DoesNotExist:
        return Response({
            'success': False,
            'error': 'Template not found'
        }, status=status.HTTP_404_NOT_FOUND)
    
    # Get platform from request
    platform = getattr(request, 'platform', None)
    
    # Import User model
    from apps.users.models import User
    
    # Filter users by platform if applicable
    users = User.objects.filter(id__in=user_ids)
    if platform and not request.user.is_superuser:
        users = users.filter(platform=platform)
    
    notifications = []
    for user in users:
        notification = Notification(
            user=user,
            template=template,
            title=title,
            message=message,
            status='pending',
            platform=user.platform  # Assign user's platform
        )
        notifications.append(notification)
    
    Notification.objects.bulk_create(notifications)
    
    return Response({
        'success': True,
        'message': f'{len(notifications)} notifications created successfully'
    })


@api_view(['GET'])
@permission_classes([permissions.IsAuthenticated, IsAdminUser])
def notification_stats(request):
    """Get notification statistics - Platform-aware"""
    
    platform = getattr(request, 'platform', None)
    
    # Base queryset
    queryset = Notification.objects.all()
    
    # Platform filtering
    if platform and not request.user.is_superuser:
        queryset = queryset.filter(platform=platform)
    
    stats = {
        'total_notifications': queryset.count(),
        'pending_notifications': queryset.filter(status='pending').count(),
        'sent_notifications': queryset.filter(status='sent').count(),
        'failed_notifications': queryset.filter(status='failed').count(),
        'unread_notifications': queryset.filter(status__in=['sent', 'pending']).count(),
    }
    
    if platform:
        stats['platform'] = {
            'id': platform.id,
            'name': platform.name,
            'platform_id': platform.platform_id
        }
    
    serializer = NotificationStatsSerializer(stats)
    return Response({
        'success': True,
        'stats': serializer.data
    })
