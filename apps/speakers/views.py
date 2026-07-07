import django_filters
from rest_framework import generics, permissions, status, filters
from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response
from rest_framework.parsers import MultiPartParser, FormParser, JSONParser
from django_filters.rest_framework import DjangoFilterBackend
from django.db.models import Count, Avg, Q
from django.utils import timezone
from django.shortcuts import get_object_or_404
from django.db import transaction, IntegrityError
from django.core.exceptions import ValidationError
from datetime import datetime, timedelta
from apps.users.models import User

from .models import Speaker
from .serializers import (
    SpeakerSerializer,
    SpeakerCreateSerializer,
    SpeakerUpdateSerializer,
    SpeakerListSerializer,
    SpeakerPublicSerializer
)
from apps.users.permissions import IsOwnerOrAdmin, IsAdminOrReadOnly


class SpeakerFilterSet(django_filters.FilterSet):
    """Custom filterset for Speaker model - only model fields"""
    
    class Meta:
        model = Speaker
        fields = {
            'title': ['icontains'],
            'company': ['icontains'],
            'is_verified': ['exact'],
            'is_active': ['exact'],
            'total_sessions': ['gte', 'lte'],
        }


class SpeakerListView(generics.ListAPIView):
    """List all speakers with filtering"""
    
    serializer_class = SpeakerListSerializer
    permission_classes = [permissions.AllowAny]
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_class = SpeakerFilterSet
    search_fields = [
        'user__first_name', 'user__last_name', 'title', 'bio', 'company'
    ]
    ordering_fields = [
        'total_sessions', 'created_at', 'user__first_name'
    ]
    ordering = ['-total_sessions', '-created_at']
    
    def get_queryset(self):
        return Speaker.objects.select_related('user').filter(
            user__is_active=True,
            user__role='instructor'
        )


@api_view(['GET'])
@permission_classes([permissions.IsAuthenticated])
def current_speaker(request):
    """Get current speaker profile with proper error handling"""
    
    try:
        speaker = Speaker.objects.select_related('user').get(user=request.user)
        serializer = SpeakerSerializer(speaker, context={'request': request})
        return Response({
            'success': True,
            'data': serializer.data
        })
    except Speaker.DoesNotExist:
        # Only create if user is instructor
        if request.user.role == 'instructor':
            try:
                with transaction.atomic():
                    speaker = Speaker.objects.create(user=request.user)
                    serializer = SpeakerSerializer(speaker, context={'request': request})
                    return Response({
                        'success': True,
                        'data': serializer.data
                    }, status=status.HTTP_201_CREATED)
            except IntegrityError:
                # Handle race condition
                speaker = Speaker.objects.get(user=request.user)
                serializer = SpeakerSerializer(speaker, context={'request': request})
                return Response({
                    'success': True,
                    'data': serializer.data
                })
        else:
            return Response({
                'success': False,
                'message': 'Speaker profile can only be created for instructor users',
                'errors': [{'user': 'Only instructors can create speaker profiles'}]
            }, status=status.HTTP_403_FORBIDDEN)


class SpeakerCreateView(generics.CreateAPIView):
    """Create speaker profile with user creation"""
    
    serializer_class = SpeakerCreateSerializer
    permission_classes = [permissions.AllowAny]
    parser_classes = [MultiPartParser, FormParser, JSONParser]
    
    def create(self, request, *args, **kwargs):
        """Create speaker with user creation and return FULL speaker data"""
        
        serializer = self.get_serializer(data=request.data)
        
        if serializer.is_valid():
            try:
                with transaction.atomic():
                    # Create speaker (serializer handles user creation)
                    speaker = serializer.save()
                    
                    # Mark user as verified on creation
                    user = speaker.user
                    user.is_verified = True
                    user.save()
                    
                    # Also mark speaker as verified
                    speaker.is_verified = True
                    speaker.save()
                    
                    # Refresh the speaker from database to get all relations
                    speaker.refresh_from_db()
                    
                    # Return FULL speaker data using SpeakerSerializer
                    full_serializer = SpeakerSerializer(speaker, context={'request': request})
                    
                    return Response({
                        'success': True,
                        'message': 'Speaker profile created successfully',
                        'data': full_serializer.data
                    }, status=status.HTTP_201_CREATED)
                    
            except IntegrityError as e:
                return Response({
                    'success': False,
                    'message': 'Database error occurred',
                    'errors': [{'database': f'Integrity error: {str(e)}'}]
                }, status=status.HTTP_400_BAD_REQUEST)
        else:
            # Handle validation errors in the expected format
            errors = []
            for field, messages in serializer.errors.items():
                if isinstance(messages, list):
                    for message in messages:
                        errors.append({field: message})
                else:
                    errors.append({field: str(messages)})
            
            return Response({
                'success': False,
                'message': 'Validation failed',
                'errors': errors
            }, status=status.HTTP_400_BAD_REQUEST)


class SpeakerDetailView(generics.RetrieveUpdateDestroyAPIView):
    """Speaker detail view with full profile"""
    
    queryset = Speaker.objects.select_related('user')
    permission_classes = [permissions.IsAuthenticated, IsOwnerOrAdmin]
    parser_classes = [MultiPartParser, FormParser, JSONParser] 
    
    def get_serializer_class(self):
        if self.request.method in ['PUT', 'PATCH']:
            return SpeakerUpdateSerializer
        return SpeakerSerializer
    
    def get_permissions(self):
        if self.request.method == 'GET':
            return [permissions.AllowAny()]
        return super().get_permissions()
    
    def update(self, request, *args, **kwargs):
        """Update speaker with proper response format"""
        partial = kwargs.pop('partial', False)
        instance = self.get_object()
        serializer = self.get_serializer(instance, data=request.data, partial=partial)
        
        if serializer.is_valid():
            self.perform_update(serializer)
            # Return full speaker data after update
            full_serializer = SpeakerSerializer(instance, context={"request": request})
            return Response({
                'success': True,
                'message': 'Profile updated successfully',
                'data': full_serializer.data
            })
        else:
            # Handle validation errors
            errors = []
            for field, messages in serializer.errors.items():
                if isinstance(messages, list):
                    for message in messages:
                        errors.append({field: message})
                else:
                    errors.append({field: str(messages)})
            
            return Response({
                'success': False,
                'message': 'Validation failed',
                'errors': errors
            }, status=status.HTTP_400_BAD_REQUEST)


class SpeakerPublicProfileView(generics.RetrieveAPIView):
    """Public speaker profile (limited fields)"""
    
    queryset = Speaker.objects.select_related('user').filter(user__is_active=True)
    serializer_class = SpeakerPublicSerializer
    permission_classes = [permissions.AllowAny]
    lookup_field = 'id'
    
    def retrieve(self, request, *args, **kwargs):
        """Return public profile with consistent response format"""
        instance = self.get_object()
        serializer = self.get_serializer(instance, context={'request': request})
        return Response({
            'success': True,
            'data': serializer.data
        })


class CurrentSpeakerView(generics.RetrieveUpdateAPIView):
    """Get/update current speaker profile"""
    
    permission_classes = [permissions.IsAuthenticated]
    parser_classes = [MultiPartParser, FormParser, JSONParser] 
    
    def get_serializer_class(self):
        if self.request.method in ['PUT', 'PATCH']:
            return SpeakerUpdateSerializer
        return SpeakerSerializer
    
    def get_object(self):
        # Get or create speaker profile for current user
        speaker_profile, created = Speaker.objects.get_or_create(
            user=self.request.user,
            defaults={'user': self.request.user}
        )
        return speaker_profile
    
    def retrieve(self, request, *args, **kwargs):
        """Get current user's speaker profile"""
        instance = self.get_object()
        serializer = self.get_serializer(instance, context={'request': request})
        return Response({
            'success': True,
            'data': serializer.data
        })
    
    def update(self, request, *args, **kwargs):
        """Update current user's speaker profile"""
        partial = kwargs.pop('partial', False)
        instance = self.get_object()
        serializer = self.get_serializer(instance, data=request.data, partial=partial)
        
        if serializer.is_valid():
            self.perform_update(serializer)
            # Return full speaker data after update
            full_serializer = SpeakerSerializer(instance, context={'request': request})
            return Response({
                'success': True,
                'message': 'Profile updated successfully',
                'data': full_serializer.data
            })
        else:
            # Handle validation errors
            errors = []
            for field, messages in serializer.errors.items():
                if isinstance(messages, list):
                    for message in messages:
                        errors.append({field: message})
                else:
                    errors.append({field: str(messages)})
            
            return Response({
                'success': False,
                'message': 'Validation failed',
                'errors': errors
            }, status=status.HTTP_400_BAD_REQUEST)


@api_view(['GET'])
@permission_classes([permissions.AllowAny])
def featured_speakers(request):
    """Get featured speakers"""
    
    speakers = Speaker.objects.filter(
        is_verified=True,
        is_active=True,
        user__is_active=True
    ).select_related('user').order_by('-total_sessions')[:6]
    
    serializer = SpeakerListSerializer(speakers, many=True, context={'request': request})
    return Response({
        'success': True,
        'data': serializer.data
    })


@api_view(['GET'])
@permission_classes([permissions.AllowAny])
def search_speakers(request):
    """Advanced speaker search with filters"""
    
    query = request.GET.get('q', '')
    is_verified = request.GET.get('is_verified')
    is_active = request.GET.get('is_active')
    company = request.GET.get('company')
    
    speakers = Speaker.objects.filter(user__is_active=True)
    
    if query:
        speakers = speakers.filter(
            Q(user__first_name__icontains=query) |
            Q(user__last_name__icontains=query) |
            Q(title__icontains=query) |
            Q(bio__icontains=query) |
            Q(company__icontains=query)
        )
    
    if is_verified is not None:
        speakers = speakers.filter(is_verified=is_verified.lower() == 'true')
    
    if is_active is not None:
        speakers = speakers.filter(is_active=is_active.lower() == 'true')
    
    if company:
        speakers = speakers.filter(company__icontains=company)
    
    speakers = speakers.select_related('user').order_by('-total_sessions')
    serializer = SpeakerListSerializer(speakers, many=True, context={'request': request})
    
    return Response({
        'success': True,
        'data': serializer.data,
        'count': speakers.count()
    })

@api_view(['GET'])
@permission_classes([permissions.IsAuthenticated, permissions.IsAdminUser])
def admin_speaker_stats(request):
    """Get comprehensive speaker statistics (admin only)"""

    # Basic counts
    total_speakers = Speaker.objects.count()
    verified_speakers = Speaker.objects.filter(is_verified=True).count()
    active_speakers = Speaker.objects.filter(is_active=True).count()
    inactive_speakers = Speaker.objects.filter(is_active=False).count()

    # Number of speakers who have conducted at least one webinar
    speakers_with_webinars = Speaker.objects.annotate(
        webinar_count=Count('webinars')  # ✅ FIXED: plural
    ).filter(webinar_count__gt=0).count()

    # Total webinars by all speakers
    total_webinars = Speaker.objects.aggregate(
        total_webinars=Count('webinars')  # ✅ FIXED: plural
    )['total_webinars'] or 0

    # Recent speakers (created in last 30 days)
    recent_threshold = timezone.now() - timedelta(days=30)
    recent_speakers = Speaker.objects.filter(created_at__gte=recent_threshold).count()

    # Additional helpful stats
    avg_webinars_per_speaker = total_webinars / total_speakers if total_speakers > 0 else 0

    stats = {
        'total_speakers': total_speakers,
        'verified_speakers': verified_speakers,
        'active_speakers': active_speakers,
        'inactive_speakers': inactive_speakers,
        'speakers_with_webinars': speakers_with_webinars,
        'speakers_without_webinars': total_speakers - speakers_with_webinars,
        'total_webinars': total_webinars,
        'avg_webinars_per_speaker': round(avg_webinars_per_speaker, 2),
        'recent_speakers_last_30_days': recent_speakers,
        'verification_rate': round((verified_speakers / total_speakers * 100) if total_speakers > 0 else 0, 2),
    }

    return Response({
        'success': True,
        'data': stats
    })
