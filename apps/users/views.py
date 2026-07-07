from rest_framework import generics, permissions, status, filters
from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response
from django_filters.rest_framework import DjangoFilterBackend
from django.db.models import Q

from .models import User, UserProfile
from .serializers import (
    UserSerializer, 
    UserDetailSerializer, 
    UserUpdateSerializer,
    UserListSerializer,
    UserProfileSerializer
)
from .permissions import IsOwnerOrAdmin


class UserListView(generics.ListAPIView):
    """
    List users with platform filtering
    - Admins: See all users
    - Platform users: See shared users + platform-specific users
    """
    
    serializer_class = UserListSerializer
    permission_classes = [permissions.IsAuthenticated, permissions.IsAdminUser]
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_fields = ['role', 'is_active', 'is_verified']
    search_fields = ['first_name', 'last_name', 'email']
    ordering_fields = ['created_at', 'updated_at', 'first_name', 'last_name']
    ordering = ['-created_at']
    
    def get_queryset(self):
        queryset = User.objects.select_related('profile', 'platform')
        
        # Platform-aware filtering
        platform = getattr(self.request, 'platform', None)
        
        if platform and not self.request.user.is_superuser:
            # Show shared users + platform-specific users
            queryset = queryset.filter(
                Q(platform=platform) | Q(platform__isnull=True)
            )
        
        return queryset


class UserDetailView(generics.RetrieveAPIView):
    """Get user details"""
    
    serializer_class = UserDetailSerializer
    permission_classes = [permissions.IsAuthenticated, IsOwnerOrAdmin]
    
    def get_queryset(self):
        return User.objects.select_related('profile', 'platform')


class UserProfileUpdateView(generics.RetrieveUpdateAPIView):
    """Get and update user profile"""
    
    serializer_class = UserUpdateSerializer
    permission_classes = [permissions.IsAuthenticated]
    
    def get_object(self):
        return self.request.user


class UserPublicProfileView(generics.RetrieveAPIView):
    """Get public user profile"""
    
    serializer_class = UserDetailSerializer
    permission_classes = [permissions.AllowAny]
    lookup_field = 'id'
    
    def get_queryset(self):
        queryset = User.objects.select_related('profile', 'platform').filter(is_active=True)
        
        # Platform-aware filtering for public profiles
        platform = getattr(self.request, 'platform', None)
        
        if platform:
            # Show shared users + platform-specific users
            queryset = queryset.filter(
                Q(platform=platform) | Q(platform__isnull=True)
            )
        
        return queryset


@api_view(['GET'])
@permission_classes([permissions.IsAuthenticated])
def current_user(request):
    """Get current authenticated user"""
    
    serializer = UserDetailSerializer(request.user, context={'request': request})
    return Response({
        'success': True,
        'user': serializer.data
    })


@api_view(['GET'])
@permission_classes([permissions.IsAuthenticated, permissions.IsAdminUser])
def user_stats(request):
    """Get user statistics (admin only) - Platform-aware"""
    
    platform = getattr(request, 'platform', None)
    
    # Base queryset
    queryset = User.objects.all()
    
    # Filter by platform if not superuser
    if platform and not request.user.is_superuser:
        queryset = queryset.filter(
            Q(platform=platform) | Q(platform__isnull=True)
        )
    
    stats = {
        'total_users': queryset.count(),
        'active_users': queryset.filter(is_active=True).count(),
        'verified_users': queryset.filter(is_verified=True).count(),
        'instructors': queryset.filter(role='instructor').count(),
        'attendees': queryset.filter(role='attendee', platform=platform).count() if platform else queryset.filter(role='attendee').count(),
        'admins': queryset.filter(role='admin').count(),
        'recent_users': queryset.filter(is_active=True).order_by('-created_at')[:5].count(),
    }
    
    if platform:
        stats['platform'] = {
            'id': platform.id,
            'name': platform.name,
            'platform_id': platform.platform_id
        }
    
    return Response({
        'success': True,
        'stats': stats
    })


@api_view(['POST'])
@permission_classes([permissions.IsAuthenticated])
def update_user_role(request):
    """Update user role (admin only)"""
    
    if not request.user.is_staff and request.user.role != 'admin':
        return Response(
            {'success': False, 'error': 'Permission denied'}, 
            status=status.HTTP_403_FORBIDDEN
        )
    
    user_id = request.data.get('user_id')
    new_role = request.data.get('role')
    
    if not user_id or not new_role:
        return Response(
            {'success': False, 'error': 'user_id and role are required'}, 
            status=status.HTTP_400_BAD_REQUEST
        )
    
    try:
        user = User.objects.get(id=user_id)
        old_role = user.role
        user.role = new_role
        user.save()  # Will trigger platform logic in save() method
        
        return Response({
            'success': True,
            'message': f'User role updated from {old_role} to {new_role}',
            'user': UserSerializer(user, context={'request': request}).data
        })
    except User.DoesNotExist:
        return Response(
            {'success': False, 'error': 'User not found'}, 
            status=status.HTTP_404_NOT_FOUND
        )


@api_view(['GET'])
@permission_classes([permissions.AllowAny])
def user_by_role(request, role):
    """Get users by role - Platform-aware"""
    
    if role not in ['instructor', 'attendee', 'admin']:
        return Response(
            {'success': False, 'error': 'Invalid role'}, 
            status=status.HTTP_400_BAD_REQUEST
        )
    
    queryset = User.objects.filter(role=role, is_active=True).select_related('profile', 'platform')
    
    # Platform filtering
    platform = getattr(request, 'platform', None)
    
    if platform:
        if role == 'attendee':
            # Attendees: only from this platform
            queryset = queryset.filter(platform=platform)
        else:
            # Instructors/Admins: shared (platform=NULL)
            queryset = queryset.filter(platform__isnull=True)
    
    serializer = UserListSerializer(queryset, many=True, context={'request': request})
    
    return Response({
        'success': True,
        'role': role,
        'count': queryset.count(),
        'users': serializer.data
    })
