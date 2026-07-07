# apps/webinars/views.py - ENHANCED with conditional access control and performance optimization
from rest_framework import generics, permissions, status, filters
from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response
from rest_framework.pagination import PageNumberPagination
from django_filters.rest_framework import DjangoFilterBackend
from django.db.models import Count, Q, Avg, Sum, Prefetch
from django.utils import timezone
from django.shortcuts import get_object_or_404
import logging

from apps.users.permissions import IsInstructorOrAdmin, IsAdminOnly
from .models import Category, Webinar, WebinarResource, WebinarReview, WebinarAnalytics
from .serializers import (
    CategorySerializer,
    WebinarListSerializer,
    WebinarDetailSerializer,
    WebinarCreateUpdateSerializer,
    WebinarResourceSerializer,
    WebinarReviewSerializer,
    WebinarAnalyticsSerializer,
    WebinarStatsSerializer,
    InstructorWebinarStatsSerializer
)
from .filters import WebinarFilter
import json
logger = logging.getLogger(__name__)


class StandardResultsSetPagination(PageNumberPagination):
    """Standard pagination for webinar lists"""
    page_size = 20
    page_size_query_param = 'page_size'
    max_page_size = 100
class WebinarQuerysetMixin:
    """Mixin for optimized webinar querysets"""
    
    def get_optimized_queryset(self):
        """Get optimized queryset with all necessary joins"""
        from apps.webinars.models import WebinarPlatformPrice
        
        return Webinar.objects.select_related(
            'speaker__user',
            'category'
         ).prefetch_related(
            Prefetch(
                'enrollments',
                queryset=self.get_enrollment_queryset(),
                to_attr='cached_enrollments'
            ),
            'enrollments',  # For user_access_types
            'enrollments__user',  # For user data
            # ✅ CHANGED: Updated to use new plural related names
            'zoom_meetings__recordings',  # Changed from zoom_meeting_rel__recordings
            'zoom_webinars__recordings',  # Changed from zoom_webinar_rel__recordings
            # ✅ ADD: Prefetch platform pricing
            Prefetch(
                'platform_prices',
                queryset=WebinarPlatformPrice.objects.select_related('platform').filter(is_active=True)
            )
        )
    
    def get_enrollment_queryset(self):
        """Get enrollment queryset for prefetch"""
        from apps.enrollments.models import Enrollment
        return Enrollment.objects.filter(
            status__in=['enrolled', 'attended', 'completed']
        ).select_related('user')



class CategoryListView(generics.ListCreateAPIView):
    """List and create categories with optimized performance"""
    
    serializer_class = CategorySerializer
    permission_classes = [permissions.AllowAny]  # Read access for all
    pagination_class = None  # No pagination for categories
    
    def get_queryset(self):
        """Optimized queryset with webinar count"""
        return Category.objects.filter(is_active=True).annotate(
            webinar_count=Count('webinar', filter=Q(webinar__status__in=[
                'scheduled', 'live', 'completed', 'available'
            ]))
        ).order_by('name')
    
    def get_permissions(self):
        """Dynamic permissions - only admins can create"""
        if self.request.method == 'POST':
            return [permissions.IsAuthenticated(), IsAdminOnly()]
        return [permissions.AllowAny()]


class CategoryDetailView(generics.RetrieveUpdateDestroyAPIView):
    """Category detail view - admin only for modifications"""
    
    queryset = Category.objects.all()
    serializer_class = CategorySerializer
    permission_classes = [IsAdminOnly]


class WebinarListView(generics.ListAPIView, WebinarQuerysetMixin):
    """Public webinar list with conditional zoom_url access"""
    
    serializer_class = WebinarListSerializer
    permission_classes = [permissions.AllowAny]  # Public access
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_class = WebinarFilter
    search_fields = ['title', 'description', 'speaker__user__first_name', 'speaker__user__last_name']
    ordering_fields = ['scheduled_date', 'created_at', 'title', 'main_price']
    ordering = ['-created_at']
    pagination_class = StandardResultsSetPagination
    
    def get_queryset(self):
        """Public access to all non-draft webinars - Platform-filtered"""
        queryset = self.get_optimized_queryset().exclude(status='draft')
        
        # ✅ ADD PLATFORM FILTERING
        platform = getattr(self.request, 'platform', None)
        if platform:
            # Show webinars with no platforms (available to all) OR webinars assigned to this platform
            queryset = queryset.filter(
                Q(platforms__isnull=True) | Q(platforms=platform)
            )
        
        return queryset.distinct()

    def get_serializer_context(self):
        """Pass request context for conditional access"""
        context = super().get_serializer_context()
        context['request'] = self.request  # This is key for conditional access
        return context


class WebinarDetailView(generics.RetrieveAPIView, WebinarQuerysetMixin):
    """Public webinar detail with conditional zoom_url access"""
    
    serializer_class = WebinarDetailSerializer
    permission_classes = [permissions.AllowAny]  # Public access
    lookup_field = 'webinar_id'
    lookup_url_kwarg = 'webinar_id'
    
    def get_queryset(self):
        """Optimized queryset for detail view"""
        return self.get_optimized_queryset()
    
    def get_serializer_context(self):
        """Pass request context for conditional access"""
        context = super().get_serializer_context()
        context['request'] = self.request  # This enables conditional access in serializers
        return context
    
    def retrieve(self, request, *args, **kwargs):
        """Enhanced retrieve with additional user-specific data"""
        instance = self.get_object()
        serializer = self.get_serializer(instance)
        data = serializer.data
        
        # Add user-specific metadata (already handled by serializer)
        user = request.user
        if user.is_authenticated:
            # Additional context that might be useful
            data['user_context'] = {
                'is_owner': user == instance.speaker.user,
                'is_admin': user.is_staff or user.is_superuser,
                'enrollment_count': instance.enrollments.filter(user=user).count()
            }
        
        return Response(data)

class WebinarCreateView(generics.CreateAPIView):
    """Create webinar with conditional Zoom integration"""
    
    serializer_class = WebinarCreateUpdateSerializer
    permission_classes = [permissions.IsAuthenticated, IsInstructorOrAdmin]
        
   
    def _get_zoom_integration_status(self, webinar):
        """Get Zoom integration status with enhanced details"""
        if webinar.webinar_type == 'live':
            has_meeting = hasattr(webinar, 'zoom_meeting_rel') and webinar.zoom_meeting_rel
            has_webinar = hasattr(webinar, 'zoom_webinar_rel') and webinar.zoom_webinar_rel
            
            integration_data = {
                'integrated': bool(has_meeting or has_webinar),
                'type': 'meeting' if has_meeting else 'webinar' if has_webinar else 'none'
            }
            
            # Add detailed info if meeting exists
            if has_meeting:
                integration_data['is_linked_existing'] = getattr(
                    webinar.zoom_meeting_rel, 'is_linked_existing', False
                )
                integration_data['meeting_id'] = webinar.zoom_meeting_rel.zoom_meeting_id
                integration_data['join_url'] = webinar.zoom_meeting_rel.join_url
                integration_data['start_url'] = webinar.zoom_meeting_rel.start_url  # ADDED
            
            # Add webinar info if exists
            if has_webinar:
                integration_data['webinar_id'] = webinar.zoom_webinar_rel.zoom_webinar_id  # ADDED
                integration_data['join_url'] = webinar.zoom_webinar_rel.join_url  # ADDED
            
            return integration_data
        else:
            # Recorded webinar
            return {
                'integrated': bool(webinar.zoom_url),
                'type': 'direct_url',
                'zoom_url': webinar.zoom_url if webinar.zoom_url else None  # ADDED
            }

    def _get_success_message(self, webinar, zoom_status, linked_existing=False):
        """Get appropriate success message"""
        if webinar.webinar_type == 'live':
            if linked_existing and zoom_status.get('integrated'):
                return 'Live webinar created and linked to existing Zoom meeting'
            elif zoom_status.get('integrated'):
                return f'Live webinar created with Zoom {zoom_status["type"]}'
            return 'Live webinar created (Zoom integration pending)'
        return 'Recorded webinar created and available immediately'
    def _save_platform_pricing(self, webinar, platform_pricing_data):
        """Save platform-specific pricing for webinar"""
        from apps.platforms.models import Platform
        from apps.webinars.models import WebinarPlatformPrice
        
        if not platform_pricing_data or not isinstance(platform_pricing_data, list):
            logger.info("⏭️ No platform pricing data to save")
            return 0
        
        created_count = 0
        for pricing in platform_pricing_data:
            platform_id = pricing.get('platform_id')
            pricing_data = pricing.get('pricing_data', {})
            discount_percentage = pricing.get('discount_percentage', 0)
            is_active = pricing.get('is_active', True)
            
            if not platform_id:
                logger.warning("⚠️ Platform ID missing in pricing data")
                continue
            
            try:
                platform = Platform.objects.get(platform_id=platform_id)
                
                # Only create if there's actual pricing data
                if pricing_data and any(pricing_data.values()):
                    # Update or create platform pricing
                    WebinarPlatformPrice.objects.update_or_create(
                        webinar=webinar,
                        platform=platform,
                        defaults={
                            'pricing_data': pricing_data,
                            'discount_percentage': discount_percentage,
                            'is_active': is_active
                        }
                    )
                    created_count += 1
                    logger.info(f"✅ Saved platform pricing for {platform.name}")
            except Platform.DoesNotExist:
                logger.warning(f"⚠️ Platform {platform_id} not found")
                continue
        
        logger.info(f"✅ Saved {created_count} platform pricing records")
        return created_count

    def create(self, request, *args, **kwargs):
        """Enhanced create with Zoom meeting linking support"""
        webinar_type = request.data.get('webinar_type', 'live')
        logger.info(f"🆕 Creating {webinar_type} webinar")
        
        # Check for existing meeting linking request
        use_existing_meeting = request.data.get('use_existing_meeting') == 'true'
        existing_zoom_meeting_id = request.data.get('existing_zoom_meeting_id')

        platform_pricing_data = request.data.get('platform_pricing', '[]')
        if isinstance(platform_pricing_data, str):
            try:
                platform_pricing_data = json.loads(platform_pricing_data)
            except json.JSONDecodeError:
                logger.warning("Failed to parse platform_pricing JSON")
                platform_pricing_data = []
        
        logger.info(f"📊 Platform pricing data: {platform_pricing_data}")

        if use_existing_meeting and existing_zoom_meeting_id:
            logger.info(f"🔗 Linking request for existing meeting: {existing_zoom_meeting_id}")
        
        serializer = self.get_serializer(data=request.data)
        
        if not serializer.is_valid():
            logger.error(f"❌ Validation failed: {serializer.errors}")
            return Response({
                'success': False,
                'error': 'Validation failed',
                'details': serializer.errors
            }, status=status.HTTP_400_BAD_REQUEST)
        
        try:
            # ✅ DISABLE AUTO-CREATION IF LINKING TO EXISTING
            from django.db import transaction
            
            with transaction.atomic():
                # Save webinar WITHOUT triggering signals yet if linking existing
                if use_existing_meeting and existing_zoom_meeting_id:
                    # Create webinar with signals disabled
                    webinar = serializer.save()
                    logger.info(f"✅ Webinar {webinar.webinar_id} created (signals will be triggered after linking)")
                else:
                    # Normal creation with auto Zoom creation
                    webinar = serializer.save()
                    logger.info(f"✅ Webinar {webinar.webinar_id} created")
                
                pricing_count = self._save_platform_pricing(webinar, platform_pricing_data)
   
                zoom_link_status = None
                relinked_from = None
                
                # Handle Zoom integration for live webinars
                if webinar.webinar_type == 'live':
                    if use_existing_meeting and existing_zoom_meeting_id:
                        # Link to existing meeting (must succeed or rollback)
                        try:
                            from apps.integrations.views import _link_existing_zoom_meeting
                            from apps.integrations.models import ZoomMeeting
                            
                            # Check if meeting was previously linked
                            try:
                                old_link = ZoomMeeting.objects.get(zoom_meeting_id=existing_zoom_meeting_id)
                                relinked_from = {
                                    'webinar_id': old_link.webinar.webinar_id,
                                    'title': old_link.webinar.title
                                }
                            except ZoomMeeting.DoesNotExist:
                                pass
                            
                            zoom_meeting = _link_existing_zoom_meeting(
                                webinar=webinar,
                                meeting_id=existing_zoom_meeting_id,
                                user=request.user,
                                force_relink=True
                            )
                            
                            logger.info(f"✅ Linked to existing meeting {existing_zoom_meeting_id}")
                            zoom_link_status = 'relinked' if relinked_from else 'linked'
                            
                        except Exception as e:
                            error_str = str(e)
                            logger.error(f"❌ Linking failed: {error_str}")
                            logger.exception("Full traceback:")
                            
                            # ❌ ROLLBACK - Don't create webinar if linking fails
                            raise Exception(f"Failed to link existing Zoom meeting: {error_str}")
                    else:
                        # Wait for auto-creation
                        import time
                        time.sleep(1)
                        zoom_link_status = 'auto_created'
                    
                    # Refresh to get latest Zoom data
                    webinar.refresh_from_db()
            
            # Build response (outside transaction since webinar is committed)
            response_serializer = WebinarDetailSerializer(
                webinar, 
                context={'request': request}
            )
            
            zoom_status = self._get_zoom_integration_status(webinar)
            
            # Build appropriate message based on linking status
            if zoom_link_status == 'linked':
                message = f'{webinar_type.capitalize()} webinar created and linked to existing Zoom meeting successfully'
            elif zoom_link_status == 'relinked':
                message = f'{webinar_type.capitalize()} webinar created successfully. Zoom meeting re-linked from previous webinar.'
            else:
                message = self._get_success_message(webinar, zoom_status, use_existing_meeting)
            
            response_data = {
                'success': True,
                'message': message,
                'data': response_serializer.data,
                'zoom_integration': zoom_status,
                'platform_pricing_count': webinar.platform_prices.filter(is_active=True).count()
        
            }
            
            # Add info about relinking
            if zoom_link_status == 'relinked' and relinked_from:
                response_data['info'] = {
                    'code': 'ZOOM_MEETING_RELINKED',
                    'message': 'Zoom meeting was re-linked from another webinar',
                    'previous_webinar': relinked_from,
                    'details': f'Meeting was unlinked from "{relinked_from["title"]}" (ID: {relinked_from["webinar_id"]}) and linked to this webinar.'
                }
            
            return Response(response_data, status=status.HTTP_201_CREATED)
            
        except Exception as e:
            logger.error(f"❌ Creation error: {str(e)}")
            logger.exception("Full traceback:")
            
            # Provide clear error message
            error_message = str(e)
            if 'not found' in error_message.lower():
                error_message = 'Zoom meeting not found. Please verify the meeting ID and try again.'
            elif 'failed to link' in error_message.lower():
                error_message = f'Could not link to Zoom meeting: {error_message}'
            else:
                error_message = f'Failed to create {webinar_type} webinar: {error_message}'
            
            return Response({
                'success': False,
                'error': error_message,
                'details': str(e)
            }, status=status.HTTP_400_BAD_REQUEST)

   
    # def create(self, request, *args, **kwargs):
    #     """Enhanced create with Zoom meeting linking support"""
    #     webinar_type = request.data.get('webinar_type', 'live')
    #     logger.info(f"🆕 Creating {webinar_type} webinar")
        
    #     # Check for existing meeting linking request
    #     use_existing_meeting = request.data.get('use_existing_meeting') == 'true'
    #     existing_zoom_meeting_id = request.data.get('existing_zoom_meeting_id')
        
    #     if use_existing_meeting and existing_zoom_meeting_id:
    #         logger.info(f"🔗 Linking request for existing meeting: {existing_zoom_meeting_id}")
        
    #     serializer = self.get_serializer(data=request.data)
        
    #     if not serializer.is_valid():
    #         logger.error(f"❌ Validation failed: {serializer.errors}")
    #         return Response({
    #             'success': False,
    #             'error': 'Validation failed',
    #             'details': serializer.errors
    #         }, status=status.HTTP_400_BAD_REQUEST)
        
    #     try:
    #         webinar = serializer.save()
    #         logger.info(f"✅ Webinar {webinar.webinar_id} created")
            
    #         # Handle Zoom integration for live webinars
    #         if webinar.webinar_type == 'live':
    #             if use_existing_meeting and existing_zoom_meeting_id:
    #                 # Link to existing meeting
    #                 try:
    #                     from apps.integrations.views import _link_existing_zoom_meeting
                        
    #                     zoom_meeting = _link_existing_zoom_meeting(
    #                         webinar=webinar,
    #                         meeting_id=existing_zoom_meeting_id,
    #                         user=request.user
    #                     )
                        
    #                     logger.info(f"✅ Linked to existing meeting {existing_zoom_meeting_id}")
                        
    #                 except Exception as e:
    #                     logger.error(f"❌ Linking failed: {str(e)}")
    #                     logger.warning("⚠️ Webinar created but linking failed")
    #             else:
    #                 # Wait for auto-creation
    #                 import time
    #                 time.sleep(1)
                
    #             webinar.refresh_from_db()
            
    #         # Build response
    #         response_serializer = WebinarDetailSerializer(
    #             webinar, 
    #             context={'request': request}
    #         )
            
    #         zoom_status = self._get_zoom_integration_status(webinar)
    #         message = self._get_success_message(webinar, zoom_status, use_existing_meeting)
            
    #         return Response({
    #             'success': True,
    #             'message': message,
    #             'data': response_serializer.data,
    #             'zoom_integration': zoom_status,
    #             'linked_existing': use_existing_meeting and existing_zoom_meeting_id
    #         }, status=status.HTTP_201_CREATED)
            
    #     except Exception as e:
    #         logger.error(f"❌ Creation error: {str(e)}")
    #         logger.exception("Full traceback:")
    #         return Response({
    #             'success': False,
    #             'error': f'Failed to create {webinar_type} webinar',
    #             'details': str(e)
    #         }, status=status.HTTP_400_BAD_REQUEST)
    
    # def _get_zoom_integration_status(self, webinar):
    #     """Get Zoom integration status with enhanced details"""
    #     if webinar.webinar_type == 'live':
    #         has_meeting = hasattr(webinar, 'zoom_meeting_rel') and webinar.zoom_meeting_rel
    #         has_webinar = hasattr(webinar, 'zoom_webinar_rel') and webinar.zoom_webinar_rel
            
    #         integration_data = {
    #             'integrated': bool(has_meeting or has_webinar),
    #             'type': 'meeting' if has_meeting else 'webinar' if has_webinar else 'none'
    #         }
            
    #         if has_meeting:
    #             integration_data['is_linked_existing'] = getattr(
    #                 webinar.zoom_meeting_rel, 'is_linked_existing', False
    #             )
    #             integration_data['meeting_id'] = webinar.zoom_meeting_rel.zoom_meeting_id
    #             integration_data['join_url'] = webinar.zoom_meeting_rel.join_url
            
    #         return integration_data
    #     else:
    #         return {
    #             'integrated': bool(webinar.zoom_url),
    #             'type': 'direct_url'
    #         }
    
    # def _get_success_message(self, webinar, zoom_status, linked_existing=False):
    #     """Get appropriate success message"""
    #     if webinar.webinar_type == 'live':
    #         if linked_existing and zoom_status['integrated']:
    #             return 'Live webinar created and linked to existing Zoom meeting'
    #         elif zoom_status['integrated']:
    #             return f'Live webinar created with Zoom {zoom_status["type"]}'
    #         return 'Live webinar created (Zoom integration pending)'
    #     return 'Recorded webinar created and available immediately'

# class WebinarCreateView(generics.CreateAPIView):
#     """Create webinar with conditional Zoom integration"""
    
#     serializer_class = WebinarCreateUpdateSerializer
#     permission_classes = [permissions.IsAuthenticated, IsInstructorOrAdmin]
    
#     def create(self, request, *args, **kwargs):
#         """Enhanced create with detailed response"""
#         webinar_type = request.data.get('webinar_type', 'live')
#         logger.info(f"🆕 Creating {webinar_type} webinar")
        
#         serializer = self.get_serializer(data=request.data)
        
#         if not serializer.is_valid():
#             logger.error(f"❌ Validation failed for {webinar_type} webinar: {serializer.errors}")
#             return Response({
#                 'success': False,
#                 'error': 'Validation failed',
#                 'details': serializer.errors
#             }, status=status.HTTP_400_BAD_REQUEST)
        
#         try:
#             webinar = serializer.save()
#             logger.info(f"✅ {webinar.webinar_type.title()} webinar {webinar.webinar_id} created")
            
#             # Brief delay for live webinar Zoom integration
#             if webinar.webinar_type == 'live':
#                 import time
#                 time.sleep(1)  # Allow Zoom integration to complete
#                 webinar.refresh_from_db()
            
#             # Return detailed response
#             response_serializer = WebinarDetailSerializer(
#                 webinar, 
#                 context={'request': request}
#             )
            
#             # Check integration status
#             zoom_status = self._get_zoom_integration_status(webinar)
            
#             return Response({
#                 'success': True,
#                 'message': self._get_success_message(webinar, zoom_status),
#                 'data': response_serializer.data,
#                 'zoom_integration': zoom_status
#             }, status=status.HTTP_201_CREATED)
            
#         except Exception as e:
#             logger.error(f"❌ Error creating {webinar_type} webinar: {str(e)}")
#             return Response({
#                 'success': False,
#                 'error': f'Failed to create {webinar_type} webinar',
#                 'details': str(e)
#             }, status=status.HTTP_400_BAD_REQUEST)
    
#     def _get_zoom_integration_status(self, webinar):
#         """Get Zoom integration status"""
#         if webinar.webinar_type == 'live':
#             has_meeting = hasattr(webinar, 'zoom_meeting_rel') and webinar.zoom_meeting_rel
#             has_webinar = hasattr(webinar, 'zoom_webinar_rel') and webinar.zoom_webinar_rel
#             return {
#                 'integrated': bool(has_meeting or has_webinar),
#                 'type': 'meeting' if has_meeting else 'webinar' if has_webinar else 'none'
#             }
#         else:
#             return {
#                 'integrated': bool(webinar.zoom_url),
#                 'type': 'direct_url'
#             }
    
#     def _get_success_message(self, webinar, zoom_status):
#         """Get appropriate success message"""
#         if webinar.webinar_type == 'live':
#             if zoom_status['integrated']:
#                 return f'Live webinar created with Zoom {zoom_status["type"]}'
#             return 'Live webinar created (Zoom integration pending)'
#         return 'Recorded webinar created and available immediately'

class WebinarUpdateView(generics.UpdateAPIView):
    """Update webinar with permission checks and conditional sync"""
    
    serializer_class = WebinarCreateUpdateSerializer
    permission_classes = [permissions.IsAuthenticated]
    
    def get_queryset(self):
        """Filter based on user permissions"""
        user = self.request.user
        if user.is_staff or user.is_superuser:
            return Webinar.objects.all()
        
        # User can only update their own webinars
        return Webinar.objects.filter(speaker__user=user)
    
    def update(self, request, *args, **kwargs):
        """Enhanced update with Zoom meeting linking support and recording_data"""
        partial = kwargs.pop('partial', False)
        instance = self.get_object()
        
        logger.info(f"🔄 Updating {instance.webinar_type} webinar: {instance.webinar_id}")
        
        # ✅ Parse platform_pricing from FormData
        platform_pricing_data = request.data.get('platform_pricing', '[]')
        if isinstance(platform_pricing_data, str):
            try:
                platform_pricing_data = json.loads(platform_pricing_data)
            except json.JSONDecodeError:
                logger.warning("Failed to parse platform_pricing JSON")
                platform_pricing_data = []
        
        logger.info(f"📊 Platform pricing data for update: {platform_pricing_data}")
        
        # ✅ NEW: Parse recording_data from FormData (for recorded webinars)
        recording_data = request.data.get('recording_data')
        if recording_data and isinstance(recording_data, str):
            try:
                recording_data = json.loads(recording_data)
                logger.info(f"📹 Recording data parsed: {recording_data.get('topic', 'N/A')} ({recording_data.get('duration')} min)")
            except json.JSONDecodeError:
                logger.warning("Failed to parse recording_data JSON")
                recording_data = None
        
        # Check for existing meeting linking request (only for live webinars)
        use_existing_meeting = request.data.get('use_existing_meeting') == 'true'
        existing_zoom_meeting_id = request.data.get('existing_zoom_meeting_id')

        if use_existing_meeting and existing_zoom_meeting_id and instance.webinar_type == 'live':
            logger.info(f"🔗 Linking request detected for existing meeting: {existing_zoom_meeting_id}")
            
            # Check if webinar already has a Zoom meeting
            current_zoom_meeting = None
            if hasattr(instance, 'zoom_meeting_rel') and instance.zoom_meeting_rel:
                current_zoom_meeting = instance.zoom_meeting_rel
            elif hasattr(instance, 'zoom_webinar_rel') and instance.zoom_webinar_rel:
                current_zoom_meeting = instance.zoom_webinar_rel
            
            # Check if the meeting ID is the same as currently linked
            if current_zoom_meeting:
                current_meeting_id = str(current_zoom_meeting.zoom_meeting_id)
                requested_meeting_id = str(existing_zoom_meeting_id)
                
                logger.info(f"📊 Comparing meetings: current={current_meeting_id}, requested={requested_meeting_id}")
                
                if current_meeting_id == requested_meeting_id:
                    logger.info(f"✅ Same meeting already linked - skipping re-link")
                    pass
                else:
                    logger.warning(f"⚠️ Different meeting requested but not replaced")
                    return Response({
                        'success': False,
                        'error': 'Cannot link to different meeting. Use replace functionality first.',
                        'message': 'Please use the replace meeting modal to change the linked meeting.',
                        'current_meeting_id': current_meeting_id,
                        'requested_meeting_id': requested_meeting_id
                    }, status=status.HTTP_400_BAD_REQUEST)
            else:
                # No existing meeting - link new one
                logger.info(f"🔗 No existing meeting - linking new one: {existing_zoom_meeting_id}")
                try:
                    from apps.integrations.views import _link_existing_zoom_meeting
                    
                    zoom_meeting = _link_existing_zoom_meeting(
                        webinar=instance,
                        meeting_id=existing_zoom_meeting_id,
                        user=request.user
                    )
                    
                    logger.info(f"✅ Successfully linked to existing Zoom meeting {existing_zoom_meeting_id}")
                    
                except Exception as e:
                    logger.error(f"❌ Failed to link existing meeting: {str(e)}")
                    return Response({
                        'success': False,
                        'error': 'Failed to link to existing Zoom meeting',
                        'details': str(e)
                    }, status=status.HTTP_400_BAD_REQUEST)
        
        # Regular update process
        serializer = self.get_serializer(instance, data=request.data, partial=partial)
        
        if not serializer.is_valid():
            logger.error(f"❌ Update validation failed: {serializer.errors}")
            return Response({
                'success': False,
                'error': 'Validation failed',
                'details': serializer.errors
            }, status=status.HTTP_400_BAD_REQUEST)
        
        try:
            # Save webinar
            webinar = serializer.save()
            logger.info(f"✅ Updated webinar {webinar.webinar_id}")

            # ✅ NEW: Handle recording_data for recorded webinars
            if recording_data and webinar.webinar_type == 'recorded':
                logger.info(f"📹 Saving recording_data for recorded webinar")
                webinar.recording_data = recording_data
                webinar.has_recording = True
                
                # Ensure zoom_url is set from recording_data if not already set
                if not webinar.zoom_url and recording_data.get('play_url'):
                    webinar.zoom_url = recording_data['play_url']
                    logger.info(f"📌 Set zoom_url from recording_data: {webinar.zoom_url[:50]}...")
                
                # Update duration from recording if not already set
                if not webinar.duration and recording_data.get('duration'):
                    webinar.duration = recording_data['duration']
                    logger.info(f"⏱️ Set duration from recording_data: {webinar.duration} min")
                
                webinar.save(update_fields=['recording_data', 'has_recording', 'zoom_url', 'duration'])
                logger.info(f"✅ Saved recording_data: {recording_data.get('topic')} ({recording_data.get('file_size_mb')} MB)")

            # Handle platform pricing
            if platform_pricing_data and isinstance(platform_pricing_data, list):
                # Clear existing platform prices
                webinar.platform_prices.all().delete()
                
                # Create new platform prices
                created_count = 0
                for pricing in platform_pricing_data:
                    platform_id = pricing.get('platform_id')
                    pricing_data = pricing.get('pricing_data', {})
                    discount_percentage = pricing.get('discount_percentage', 0)
                    is_active = pricing.get('is_active', True)
                    
                    if platform_id and pricing_data and any(pricing_data.values()):
                        try:
                            from apps.platforms.models import Platform
                            from apps.webinars.models import WebinarPlatformPrice
                            
                            platform = Platform.objects.get(platform_id=platform_id)
                            WebinarPlatformPrice.objects.create(
                                webinar=webinar,
                                platform=platform,
                                pricing_data=pricing_data,
                                discount_percentage=discount_percentage,
                                is_active=is_active
                            )
                            created_count += 1
                            logger.info(f"✅ Created platform pricing for {platform.name}")
                        except Platform.DoesNotExist:
                            logger.warning(f"⚠️ Platform {platform_id} not found")
                            pass
                
                logger.info(f"✅ Updated {created_count} platform pricing records")
            
            # ✅ Refresh with prefetch to include platform prices
            from apps.webinars.models import WebinarPlatformPrice
            
            webinar = Webinar.objects.select_related(
                'speaker', 'speaker__user', 'category'
            ).prefetch_related(
                Prefetch(
                    'platform_prices',
                    queryset=WebinarPlatformPrice.objects.select_related('platform').filter(is_active=True)
                )
            ).get(id=webinar.id)
            
            # Return updated data
            response_serializer = WebinarDetailSerializer(
                webinar, 
                context={'request': request}
            )
            
            zoom_status = self._get_zoom_integration_status(webinar)
            
            # Determine success message
            if use_existing_meeting and existing_zoom_meeting_id:
                message = f'{webinar.webinar_type.title()} webinar updated with linked Zoom meeting'
            elif recording_data:
                message = f'{webinar.webinar_type.title()} webinar updated with recording data'
            else:
                message = f'{webinar.webinar_type.title()} webinar updated successfully'
            
            response_data = {
                'success': True,
                'message': message,
                'data': response_serializer.data,
                'zoom_integration': zoom_status,
                'platform_pricing_count': webinar.platform_prices.filter(is_active=True).count()
            }
            
            # Add recording info to response
            if recording_data:
                response_data['recording_info'] = {
                    'has_recording': True,
                    'recording_id': recording_data.get('recording_id'),
                    'topic': recording_data.get('topic'),
                    'duration': recording_data.get('duration'),
                    'file_size_mb': recording_data.get('file_size_mb'),
                    'recorded_date': recording_data.get('recorded_date'),
                }
            
            if use_existing_meeting and existing_zoom_meeting_id:
                response_data['linked_existing'] = True
            
            return Response(response_data)
            
        except Exception as e:
            logger.error(f"❌ Error updating webinar: {str(e)}")
            logger.exception("Full traceback:")
            return Response({
                'success': False,
                'error': 'Failed to update webinar',
                'details': str(e)
            }, status=status.HTTP_400_BAD_REQUEST)
    
    def _get_zoom_integration_status(self, webinar):
        """Get Zoom integration status"""
        if webinar.webinar_type == 'live':
            has_meeting = hasattr(webinar, 'zoom_meeting_rel') and webinar.zoom_meeting_rel
            has_webinar_zoom = hasattr(webinar, 'zoom_webinar_rel') and webinar.zoom_webinar_rel
            
            integration_data = {
                'integrated': bool(has_meeting or has_webinar_zoom),
                'type': 'meeting' if has_meeting else 'webinar' if has_webinar_zoom else 'none'
            }
            
            # Add linked status if it's a meeting
            if has_meeting:
                integration_data['is_linked_existing'] = getattr(webinar.zoom_meeting_rel, 'is_linked_existing', False)
                integration_data['meeting_id'] = webinar.zoom_meeting_rel.zoom_meeting_id
                integration_data['join_url'] = webinar.zoom_meeting_rel.join_url
            
            return integration_data
        else:
            # ✅ NEW: Add recording info for recorded webinars
            integration_data = {
                'integrated': bool(webinar.zoom_url),
                'type': 'direct_url',
                'has_recording_data': bool(webinar.recording_data)
            }
            
            if webinar.recording_data:
                integration_data['recording_metadata'] = {
                    'recording_id': webinar.recording_data.get('recording_id'),
                    'duration': webinar.recording_data.get('duration'),
                    'file_size_mb': webinar.recording_data.get('file_size_mb'),
                    'file_type': webinar.recording_data.get('file_type'),
                }
            
            return integration_data

class WebinarDeleteView(generics.DestroyAPIView):
    """Delete webinar with automatic cleanup"""
    
    permission_classes = [permissions.IsAuthenticated]
    
    def get_queryset(self):
        """Filter based on user permissions"""
        user = self.request.user
        if user.is_staff or user.is_superuser:
            return Webinar.objects.all()
        
        # User can only delete their own webinars
        return Webinar.objects.filter(speaker__user=user)
    
    def destroy(self, request, *args, **kwargs):
        """Enhanced destroy with cleanup confirmation"""
        instance = self.get_object()
        webinar_id = instance.webinar_id
        webinar_type = instance.webinar_type
        
        try:
            # Automatic cleanup is handled in model's delete method
            self.perform_destroy(instance)
            
            logger.info(f"✅ Deleted {webinar_type} webinar {webinar_id}")
            
            return Response({
                'success': True,
                'message': f'{webinar_type.title()} webinar deleted successfully',
                'webinar_id': webinar_id,
                'cleanup_performed': webinar_type == 'live'
            })
            
        except Exception as e:
            logger.error(f"❌ Error deleting webinar {webinar_id}: {str(e)}")
            return Response({
                'success': False,
                'error': 'Failed to delete webinar',
                'details': str(e)
            }, status=status.HTTP_400_BAD_REQUEST)


class MyWebinarsView(generics.ListAPIView, WebinarQuerysetMixin):
    """List current user's webinars (instructors only)"""
    
    serializer_class = WebinarListSerializer
    permission_classes = [permissions.IsAuthenticated, IsInstructorOrAdmin]
    filter_backends = [DjangoFilterBackend, filters.OrderingFilter]
    filterset_fields = ['status', 'category', 'webinar_type']
    ordering = ['-created_at']
    pagination_class = StandardResultsSetPagination
    
    def get_queryset(self):
        """Get user's webinars with optimization"""
        return self.get_optimized_queryset().filter(
            speaker__user=self.request.user
        )
    
    def get_serializer_context(self):
        """Pass request context for conditional access"""
        context = super().get_serializer_context()
        context['request'] = self.request
        return context
        
class UpcomingWebinarsView(generics.ListAPIView, WebinarQuerysetMixin):
    """Public list of upcoming live webinars - Limited to 8 results"""
    
    serializer_class = WebinarListSerializer
    permission_classes = [permissions.AllowAny]
    pagination_class = None  # Limited queryset, no pagination needed
    
    def get_queryset(self):
        """Get upcoming live webinars - Platform-filtered, max 8 results"""
        queryset = self.get_optimized_queryset().filter(
            webinar_type='live',
            scheduled_date__gt=timezone.now(),
            status='scheduled'
        )
        
        # ✅ Platform filtering
        platform = getattr(self.request, 'platform', None)
        if platform:
            queryset = queryset.filter(
                Q(platforms__isnull=True) | Q(platforms=platform)
            )
        
        # ✅ FIX: Apply distinct() BEFORE the slice - Return 8 results
        return queryset.order_by('scheduled_date').distinct()[:8]
        
    def get_serializer_context(self):
        """Pass request context for conditional access"""
        context = super().get_serializer_context()
        context['request'] = self.request
        return context



class AvailableWebinarsView(generics.ListAPIView, WebinarQuerysetMixin):
    """Public list of available recorded content"""
    
    serializer_class = WebinarListSerializer
    permission_classes = [permissions.AllowAny]
    pagination_class = None  # Limited queryset, no pagination needed
    
    def get_queryset(self):
        """Get available recorded webinars and completed live with recordings"""
        return self.get_optimized_queryset().filter(
            Q(webinar_type='recorded', status='available') |
            Q(webinar_type='live', status='completed', has_recording=True)
        ).order_by('-created_at')[:20]
    
    def get_serializer_context(self):
        """Pass request context for conditional access"""
        context = super().get_serializer_context()
        context['request'] = self.request
        return context


class WebinarResourceListView(generics.ListCreateAPIView):
    """List and create webinar resources with access control"""
    
    serializer_class = WebinarResourceSerializer
    permission_classes = [permissions.IsAuthenticated]
    
    def get_queryset(self):
        """Get resources based on user permissions"""
        webinar_id = self.kwargs['webinar_id']
        webinar = get_object_or_404(Webinar.select_related('speaker__user'), id=webinar_id)
        
        user = self.request.user
        
        # Owner or admin can see all resources
        if user == webinar.speaker.user or user.is_staff or user.is_superuser:
            return webinar.resources.all().order_by('title')
        
        # Check if user has access to webinar
        if webinar.can_user_access_webinar(user):
            return webinar.resources.all().order_by('title')
        
        # Others can only see public resources
        return webinar.resources.filter(is_public=True).order_by('title')
    
    def perform_create(self, serializer):
        """Create resource with permission check"""
        webinar_id = self.kwargs['webinar_id']
        webinar = get_object_or_404(Webinar.select_related('speaker__user'), id=webinar_id)
        
        user = self.request.user
        
        # Only owner or admin can create resources
        if not (user == webinar.speaker.user or user.is_staff or user.is_superuser):
            raise permissions.PermissionDenied("You don't have permission to add resources")
        
        serializer.save(webinar=webinar)


class WebinarReviewListView(generics.ListCreateAPIView):
    """List and create webinar reviews"""
    
    serializer_class = WebinarReviewSerializer
    permission_classes = [permissions.IsAuthenticatedOrReadOnly]
    pagination_class = StandardResultsSetPagination
    
    def get_queryset(self):
        """Get reviews for webinar"""
        webinar_id = self.kwargs['webinar_id']
        return WebinarReview.objects.filter(
            webinar_id=webinar_id
        ).select_related('user').order_by('-created_at')
    
    def perform_create(self, serializer):
        """Create review with validation"""
        webinar_id = self.kwargs['webinar_id']
        webinar = get_object_or_404(Webinar, id=webinar_id)
        user = self.request.user
        
        # Check if user has already reviewed
        if WebinarReview.objects.filter(webinar=webinar, user=user).exists():
            from rest_framework import serializers as drf_serializers
            raise drf_serializers.ValidationError("You have already reviewed this webinar")
        
        # Check if user has access to webinar (attended or enrolled)
        has_access = webinar.can_user_access_webinar(user)
        
        serializer.save(
            webinar=webinar, 
            user=user,
            is_verified_purchase=has_access
        )


# API Views for statistics and bulk operations
# @api_view(['GET'])
# @permission_classes([permissions.IsAuthenticated, IsAdminOnly])
# def webinar_stats(request):
#     """Get comprehensive webinar statistics"""
    
#     now = timezone.now()
    
#     # Use efficient aggregation queries
#     stats = {
#         'total_webinars': Webinar.objects.count(),
#         'live_webinars': Webinar.objects.filter(webinar_type='live').count(),
#         'recorded_webinars': Webinar.objects.filter(webinar_type='recorded').count(),
#         'upcoming_webinars': Webinar.objects.filter(
#             webinar_type='live',
#             scheduled_date__gt=now,
#             status='scheduled'
#         ).count(),
#         'currently_live': Webinar.objects.filter(
#             webinar_type='live',
#             status='live'
#         ).count(),
#         'completed_webinars': Webinar.objects.filter(
#             webinar_type='live',
#             status='completed'
#         ).count(),
#         'available_webinars': Webinar.objects.filter(
#             Q(webinar_type='recorded', status='available') |
#             Q(webinar_type='live', status='completed')
#         ).count(),
#         'with_recordings': Webinar.objects.filter(has_recording=True).count(),
#         'cancelled_webinars': Webinar.objects.filter(status='cancelled').count(),
#     }
    
#     # Get aggregated data
#     enrollment_stats = Webinar.objects.aggregate(
#         total_revenue=Sum('analytics__total_revenue'),
#         avg_rating=Avg('reviews__rating')
#     )
    
#     stats.update({
#         'total_enrollments': 0,  # Calculate from enrollments app if available
#         'total_revenue': enrollment_stats['total_revenue'] or 0,
#         'average_rating': enrollment_stats['avg_rating'] or 0,
#         'popular_categories': list(
#             Category.objects.annotate(
#                 webinar_count=Count('webinar')
#             ).filter(webinar_count__gt=0).order_by('-webinar_count')[:5].values(
#                 'name', 'webinar_count'
#             )
#         ),
#         'zoom_integrated_webinars': Webinar.objects.filter(
#             webinar_type='live'
#         ).filter(
#             Q(zoom_meeting_rel__isnull=False) | 
#             Q(zoom_webinar_rel__isnull=False)
#         ).count(),
#         'auto_converted_webinars': Webinar.objects.filter(
#             webinar_type='live',
#             has_recording=True,
#             auto_convert_to_recorded=True
#         ).count()
#     })
    
#     serializer = WebinarStatsSerializer(stats)
#     return Response(serializer.data)


# apps/webinars/views.py

@api_view(['GET'])
@permission_classes([permissions.IsAuthenticated, IsAdminOnly])
def webinar_stats(request):
    """Get comprehensive webinar statistics"""
    now = timezone.now()
    
    stats = {
        'total_webinars': Webinar.objects.count(),
        'live_webinars': Webinar.objects.filter(webinar_type='live').count(),
        'recorded_webinars': Webinar.objects.filter(webinar_type='recorded').count(),
        'upcoming_webinars': Webinar.objects.filter(
            webinar_type='live',
            scheduled_date__gt=now,
            status='scheduled'
        ).count(),
        'currently_live': Webinar.objects.filter(
            webinar_type='live',
            status='live'
        ).count(),
        'completed_webinars': Webinar.objects.filter(
            webinar_type='live',
            status='completed'
        ).count(),
        'available_webinars': Webinar.objects.filter(
            Q(webinar_type='recorded', status='available') |
            Q(webinar_type='live', status='completed')
        ).count(),
        'with_recordings': Webinar.objects.filter(has_recording=True).count(),
    }
    
    # Get aggregated data
    enrollment_stats = Webinar.objects.aggregate(
        total_revenue=Sum('analytics__total_revenue'),
        avg_rating=Avg('reviews__rating')
    )
    
    stats.update({
        'total_enrollments': 0,  # Calculate from enrollments app if available
        'total_revenue': enrollment_stats['total_revenue'] or 0,
        'average_rating': enrollment_stats['avg_rating'] or 0,
        'popular_categories': list(
            Category.objects.annotate(
                webinar_count=Count('webinar')
            ).filter(webinar_count__gt=0).order_by('-webinar_count')[:5].values(
                'name', 'webinar_count'
            )
        ),
        # ✅ FIXED: Use zoom_meetings instead of zoom_meeting_rel
        'zoom_integrated_webinars': Webinar.objects.filter(
            webinar_type='live'
        ).filter(
            Q(zoom_meetings__isnull=False) | Q(zoom_webinars__isnull=False)
        ).distinct().count(),
        'auto_converted_webinars': Webinar.objects.filter(
            webinar_type='live',
            has_recording=True,
            auto_convert_to_recorded=True
        ).count(),
    })
    
    serializer = WebinarStatsSerializer(stats)
    return Response(serializer.data)


@api_view(['GET'])
@permission_classes([permissions.IsAuthenticated, IsInstructorOrAdmin])
def instructor_webinar_stats(request):
    """Get instructor-specific webinar statistics"""
    user = request.user
    
    # Determine which instructor to get stats for
    instructor_id = request.query_params.get('instructor_id')
    
    if user.is_staff and instructor_id:
        try:
            from apps.users.models import User
            instructor = User.objects.get(id=instructor_id, role='instructor')
        except User.DoesNotExist:
            return Response({'error': 'Instructor not found'}, status=status.HTTP_404_NOT_FOUND)
    elif user.role == 'instructor':
        instructor = user
    else:
        return Response({'error': 'Permission denied'}, status=status.HTTP_403_FORBIDDEN)
    
    # Get instructor's webinars
    webinars = Webinar.objects.filter(speaker__user=instructor)
    
    # Calculate stats efficiently
    stats = {
        'total_webinars': webinars.count(),
        'live_webinars': webinars.filter(webinar_type='live').count(),
        'recorded_webinars': webinars.filter(webinar_type='recorded').count(),
        'upcoming_webinars': webinars.filter(
            webinar_type='live',
            scheduled_date__gt=timezone.now(),
            status='scheduled'
        ).count(),
        'completed_webinars': webinars.filter(
            webinar_type='live',
            status='completed'
        ).count(),
        'available_webinars': webinars.filter(
            Q(webinar_type='recorded', status='available') |
            Q(webinar_type='live', status='completed')
        ).count(),
        'with_recordings': webinars.filter(has_recording=True).count(),
    }
    
    # Get aggregated metrics
    aggregated = webinars.aggregate(
        total_revenue=Sum('analytics__total_revenue'),
        avg_rating=Avg('reviews__rating')
    )
    
    stats.update({
        'total_students': 0,  # Calculate from enrollments if available
        'total_revenue': aggregated['total_revenue'] or 0,
        'average_rating': aggregated['avg_rating'] or 0
    })
    
    serializer = InstructorWebinarStatsSerializer(stats)
    return Response(serializer.data)


# @api_view(['GET'])
# @permission_classes([permissions.IsAuthenticated, IsInstructorOrAdmin])
# def instructor_webinar_stats(request):
#     """Get instructor-specific webinar statistics"""
    
#     user = request.user
    
#     # Determine which instructor to get stats for
#     instructor_id = request.query_params.get('instructor_id')
#     if user.is_staff and instructor_id:
#         try:
#             from apps.users.models import User
#             instructor = User.objects.get(id=instructor_id, role='instructor')
#         except User.DoesNotExist:
#             return Response({
#                 'error': 'Instructor not found'
#             }, status=status.HTTP_404_NOT_FOUND)
#     elif user.role == 'instructor':
#         instructor = user
#     else:
#         return Response({
#             'error': 'Permission denied'
#         }, status=status.HTTP_403_FORBIDDEN)
    
#     # Get instructor's webinars
#     webinars = Webinar.objects.filter(speaker__user=instructor)
    
#     # Calculate stats efficiently
#     stats = {
#         'total_webinars': webinars.count(),
#         'live_webinars': webinars.filter(webinar_type='live').count(),
#         'recorded_webinars': webinars.filter(webinar_type='recorded').count(),
#         'upcoming_webinars': webinars.filter(
#             webinar_type='live',
#             scheduled_date__gt=timezone.now(),
#             status='scheduled'
#         ).count(),
#         'completed_webinars': webinars.filter(
#             webinar_type='live',
#             status='completed'
#         ).count(),
#         'available_webinars': webinars.filter(
#             Q(webinar_type='recorded', status='available') |
#             Q(webinar_type='live', status='completed')
#         ).count(),
#         'with_recordings': webinars.filter(has_recording=True).count(),
#     }
    
#     # Get aggregated metrics
#     aggregated = webinars.aggregate(
#         total_revenue=Sum('analytics__total_revenue'),
#         avg_rating=Avg('reviews__rating')
#     )
    
#     stats.update({
#         'total_students': 0,  # Calculate from enrollments if available
#         'total_revenue': aggregated['total_revenue'] or 0,
#         'average_rating': aggregated['avg_rating'] or 0
#     })
    
#     serializer = InstructorWebinarStatsSerializer(stats)
#     return Response(serializer.data)


@api_view(['POST'])
@permission_classes([permissions.IsAuthenticated])
def sync_webinar_recordings(request, webinar_id):
    """Manually sync recordings for a live webinar"""
    
    try:
        webinar = get_object_or_404(
            Webinar.select_related('speaker__user'),
            webinar_id=webinar_id
        )
        
        # Permission check
        user = request.user
        if not (user == webinar.speaker.user or user.is_staff or user.is_superuser):
            return Response({
                'error': 'Permission denied'
            }, status=status.HTTP_403_FORBIDDEN)
        
        # Type check
        if webinar.webinar_type != 'live':
            return Response({
                'error': f'Recording sync only available for live webinars'
            }, status=status.HTTP_400_BAD_REQUEST)
        
        # Sync recordings
        from apps.integrations.services import ZoomWebinarService
        zoom_service = ZoomWebinarService()
        recordings = zoom_service.sync_recordings(webinar)
        
        # Update webinar
        if recordings:
            webinar.has_recording = True
            webinar.save(update_fields=['has_recording'])
            logger.info(f"✅ Synced {len(recordings)} recordings for {webinar.webinar_id}")
        
        return Response({
            'success': True,
            'message': f'Successfully synced {len(recordings)} recordings',
            'count': len(recordings),
            'webinar_updated': bool(recordings)
        })
        
    except Exception as e:
        logger.error(f"❌ Error syncing recordings: {str(e)}")
        return Response({
            'success': False,
            'error': 'Failed to sync recordings',
            'details': str(e)
        }, status=status.HTTP_400_BAD_REQUEST)


@api_view(['POST'])
@permission_classes([permissions.IsAuthenticated, IsAdminOnly])
def bulk_sync_recordings(request):
    """Bulk sync recordings for multiple webinars"""
    
    try:
        # Get webinars that need recording sync
        webinars_to_sync = Webinar.objects.filter(
            webinar_type='live',
            status='completed',
            has_recording=False,
            auto_convert_to_recorded=True
        ).select_related('speaker__user')[:10]  # Limit batch size
        
        synced_count = 0
        recordings_found = 0
        errors = []
        
        from apps.integrations.services import ZoomWebinarService
        zoom_service = ZoomWebinarService()
        
        for webinar in webinars_to_sync:
            try:
                recordings = zoom_service.sync_recordings(webinar)
                if recordings:
                    recordings_found += len(recordings)
                    webinar.has_recording = True
                    webinar.save(update_fields=['has_recording'])
                synced_count += 1
                
            except Exception as e:
                errors.append(f"Error syncing {webinar.webinar_id}: {str(e)}")
                continue
        
        return Response({
            'success': True,
            'message': f'Bulk sync completed',
            'webinars_processed': synced_count,
            'recordings_found': recordings_found,
            'errors': errors,
            'remaining_count': Webinar.objects.filter(
                webinar_type='live',
                status='completed',
                has_recording=False,
                auto_convert_to_recorded=True
            ).count()
        })
        
    except Exception as e:
        logger.error(f"❌ Bulk sync error: {str(e)}")
        return Response({
            'success': False,
            'error': 'Bulk sync failed',
            'details': str(e)
        }, status=status.HTTP_400_BAD_REQUEST)


@api_view(['POST'])
@permission_classes([permissions.IsAuthenticated, IsAdminOnly])
def update_webinar_analytics(request, webinar_id):
    """Update webinar analytics manually"""
    
    try:
        webinar = get_object_or_404(Webinar, id=webinar_id)
        analytics, created = WebinarAnalytics.objects.get_or_create(webinar=webinar)
        analytics.update_metrics()
        
        action = 'created' if created else 'updated'
        logger.info(f"✅ Analytics {action} for webinar {webinar.webinar_id}")
        
        serializer = WebinarAnalyticsSerializer(analytics)
        return Response({
            'success': True,
            'message': f'Analytics {action} successfully',
            'analytics': serializer.data
        })
        
    except Exception as e:
        logger.error(f"❌ Error updating analytics: {str(e)}")
        return Response({
            'success': False,
            'error': 'Failed to update analytics',
            'details': str(e)
        }, status=status.HTTP_400_BAD_REQUEST)
