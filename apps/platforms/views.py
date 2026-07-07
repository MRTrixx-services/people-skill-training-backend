from rest_framework import generics, permissions, status
from rest_framework.decorators import api_view, permission_classes, parser_classes
from rest_framework.response import Response
from rest_framework.parsers import MultiPartParser, FormParser
from django.shortcuts import get_object_or_404
from .models import Platform, PlatformStats, PlatformAPILog
from .serializers import (
    PlatformListSerializer, PlatformDetailSerializer,
    PlatformCreateSerializer, PlatformConfigSerializer,
    PlatformStatsSerializer, PlatformAPILogSerializer
)
from .utils import calculate_platform_stats
import logging

logger = logging.getLogger(__name__)

# ====================================================================
# EXISTING VIEWS (UNCHANGED)
# ====================================================================

@api_view(['POST'])
@permission_classes([permissions.IsAdminUser])
def create_platform(request):
    """
    Create new platform and return API key
    Only shown once - must be saved securely
    """
    serializer = PlatformCreateSerializer(data=request.data)
    
    if not serializer.is_valid():
        return Response({
            'success': False,
            'errors': serializer.errors
        }, status=status.HTTP_400_BAD_REQUEST)
    
    platform = serializer.save()
    
    # Return the API key (only shown once!)
    return Response({
        'success': True,
        'message': 'Platform created successfully',
        'platform': {
            'id': platform.id,
            'platform_id': platform.platform_id,
            'name': platform.name,
            'api_key': platform.api_key,  # ⚠️ Only shown on creation!
        },
        'warning': '⚠️ IMPORTANT: Save this API key securely. It will NOT be shown again!'
    }, status=status.HTTP_201_CREATED)

@api_view(['GET'])
@permission_classes([permissions.IsAdminUser])
def list_platforms(request):
    """List all platforms (admin only)"""
    platforms = Platform.objects.all().order_by('-created_at')
    serializer = PlatformListSerializer(platforms, many=True)
    
    return Response({
        'success': True,
        'count': platforms.count(),
        'platforms': serializer.data
    })

@api_view(['GET'])
@permission_classes([permissions.IsAdminUser])
def get_platform_detail(request, pk):
    """Get platform details (admin only)"""
    platform = get_object_or_404(Platform, pk=pk)
    serializer = PlatformDetailSerializer(platform)
    
    return Response({
        'success': True,
        'platform': serializer.data
    })

@api_view(['PUT', 'PATCH'])
@permission_classes([permissions.IsAdminUser])
def update_platform(request, pk):
    """Update platform (admin only)"""
    platform = get_object_or_404(Platform, pk=pk)
    serializer = PlatformCreateSerializer(
        platform, 
        data=request.data, 
        partial=request.method == 'PATCH'
    )
    
    if not serializer.is_valid():
        return Response({
            'success': False,
            'errors': serializer.errors
        }, status=status.HTTP_400_BAD_REQUEST)
    
    serializer.save()
    
    return Response({
        'success': True,
        'message': 'Platform updated successfully',
        'platform': PlatformDetailSerializer(platform).data
    })

@api_view(['DELETE'])
@permission_classes([permissions.IsAdminUser])
def delete_platform(request, pk):
    """Delete platform (admin only)"""
    platform = get_object_or_404(Platform, pk=pk)
    
    # Prevent deletion if platform has users
    if platform.user_count > 0:
        return Response({
            'success': False,
            'error': 'Cannot delete platform with existing users',
            'user_count': platform.user_count
        }, status=status.HTTP_400_BAD_REQUEST)
    
    platform_name = platform.name
    platform.delete()
    
    return Response({
        'success': True,
        'message': f'Platform "{platform_name}" deleted successfully'
    })

@api_view(['POST'])
@permission_classes([permissions.IsAdminUser])
def regenerate_api_key(request, pk):
    """Regenerate API key for platform"""
    platform = get_object_or_404(Platform, pk=pk)
    
    # Require confirmation
    confirm = request.data.get('confirm', False)
    if not confirm:
        return Response({
            'success': False,
            'error': 'Please confirm API key regeneration',
            'message': 'This will INVALIDATE the current API key. Set "confirm": true to proceed.',
            'current_key_prefix': platform.api_key[:10] + '...'
        }, status=status.HTTP_400_BAD_REQUEST)
    
    # Regenerate
    old_key_prefix = platform.api_key[:10]
    new_api_key = platform.regenerate_api_key()
    
    return Response({
        'success': True,
        'message': 'API key regenerated successfully',
        'platform_id': platform.platform_id,
        'old_key_prefix': old_key_prefix + '...',
        'new_api_key': new_api_key,
        'warning': '⚠️ IMPORTANT: Save this API key securely. The old key is now INVALID!'
    })

@api_view(['GET'])
@permission_classes([permissions.AllowAny])
def get_platform_config(request):
    """
    Get current platform configuration
    Requires valid API key in header
    Public endpoint for frontend to fetch platform settings
    """
    platform = getattr(request, 'platform', None)
    
    if not platform:
        return Response({
            'success': False,
            'error': 'Platform not identified',
            'message': 'Please provide a valid X-Platform-API-Key header'
        }, status=status.HTTP_401_UNAUTHORIZED)
    
    serializer = PlatformConfigSerializer(platform)
    return Response({
        'success': True,
        'platform': serializer.data
    })

@api_view(['GET'])
@permission_classes([permissions.IsAdminUser])
def get_platform_stats(request, pk):
    """Get statistics for a specific platform"""
    platform = get_object_or_404(Platform, pk=pk)
    
    # Recalculate stats
    stats = calculate_platform_stats(platform)
    
    serializer = PlatformStatsSerializer(stats)
    return Response({
        'success': True,
        'platform': {
            'id': platform.id,
            'name': platform.name,
            'platform_id': platform.platform_id
        },
        'stats': serializer.data
    })

@api_view(['POST'])
@permission_classes([permissions.IsAdminUser])
def recalculate_all_stats(request):
    """Recalculate statistics for all platforms"""
    platforms = Platform.objects.filter(is_active=True)
    
    results = []
    for platform in platforms:
        stats = calculate_platform_stats(platform)
        results.append({
            'platform_id': platform.platform_id,
            'name': platform.name,
            'total_users': stats.total_users,
            'total_revenue': float(stats.total_revenue)
        })
    
    return Response({
        'success': True,
        'message': f'Stats recalculated for {len(results)} platforms',
        'results': results
    })

@api_view(['GET'])
@permission_classes([permissions.IsAdminUser])
def get_platform_api_logs(request, pk):
    """Get API logs for a platform"""
    platform = get_object_or_404(Platform, pk=pk)
    
    # Get query parameters
    limit = int(request.GET.get('limit', 100))
    endpoint = request.GET.get('endpoint')
    method = request.GET.get('method')
    
    # Build query
    logs = platform.api_logs.all()
    
    if endpoint:
        logs = logs.filter(endpoint__icontains=endpoint)
    if method:
        logs = logs.filter(method=method.upper())
    
    # Limit results
    logs = logs[:limit]
    
    serializer = PlatformAPILogSerializer(logs, many=True)
    
    return Response({
        'success': True,
        'platform': platform.name,
        'total_requests': platform.api_logs.count(),
        'showing': len(logs),
        'logs': serializer.data
    })

@api_view(['POST'])
@permission_classes([permissions.IsAdminUser])
def toggle_platform_maintenance(request, pk):
    """Toggle maintenance mode for platform"""
    platform = get_object_or_404(Platform, pk=pk)
    platform.maintenance_mode = not platform.maintenance_mode
    platform.save(update_fields=['maintenance_mode'])
    
    return Response({
        'success': True,
        'message': f'Maintenance mode {"ENABLED" if platform.maintenance_mode else "DISABLED"}',
        'platform_id': platform.platform_id,
        'maintenance_mode': platform.maintenance_mode
    })

@api_view(['POST'])
@permission_classes([permissions.IsAdminUser])
def toggle_platform_status(request, pk):
    """Activate/deactivate platform"""
    platform = get_object_or_404(Platform, pk=pk)
    platform.is_active = not platform.is_active
    platform.save(update_fields=['is_active'])
    
    return Response({
        'success': True,
        'message': f'Platform {"ACTIVATED" if platform.is_active else "DEACTIVATED"}',
        'platform_id': platform.platform_id,
        'is_active': platform.is_active
    })

@api_view(['POST'])
@permission_classes([permissions.IsAdminUser])
def set_default_platform(request, pk):
    """Set platform as default"""
    platform = get_object_or_404(Platform, pk=pk)
    
    # Remove default from all platforms
    Platform.objects.update(is_default=False)
    
    # Set this platform as default
    platform.is_default = True
    platform.save(update_fields=['is_default'])
    
    return Response({
        'success': True,
        'message': f'{platform.name} set as default platform',
        'platform_id': platform.platform_id
    })

# ====================================================================
# NEW: ADMIN SETTINGS API VIEWS (EXACT MATCH TO FRONTEND)
# ====================================================================

@api_view(['GET'])
@permission_classes([permissions.IsAdminUser])
def get_current_platform_settings(request):
    """
    GET /api/platforms/settings/current/
    ✅ FIXED - SAFE favicon handling
    """
    try:
        # Get the default/active platform or first active platform
        platform = Platform.objects.filter(
            is_active=True,
            is_default=True
        ).first()
        
        if not platform:
            platform = Platform.objects.filter(is_active=True).first()
        
        if not platform:
            return Response({
                'success': False,
                'error': 'No active platform found'
            }, status=status.HTTP_404_NOT_FOUND)

        # Use existing serializer
        serializer = PlatformDetailSerializer(platform)
        data = serializer.data
        
        # ✅ FIXED: SAFE favicon handling
        favicon_url = platform.favicon.url if platform.favicon else None
        
        # ✅ FIXED: SAFE payment gateways
        payment_gateways = []
        try:
            payment_gateways = platform.get_active_payment_gateways()
            payment_gateways = [
                {
                    'id': gw.id,
                    'gateway_id': getattr(gw, 'gateway_id', 'unknown'),
                    'name': getattr(gw, 'name', 'Unknown'),
                    'is_active': gw.is_active,
                    'is_configured': getattr(gw, 'is_configured', False)
                }
                for gw in payment_gateways
            ]
        except Exception as e:
            logger.warning(f"Payment gateways error: {e}")
        
        # Update with computed fields
        data.update({
            'logo_url': getattr(platform, 'logo_url', None),
            'favicon_url': favicon_url,  # ✅ FIXED
            'has_email_config': getattr(platform, 'has_email_config', False),
            'email_config_summary': getattr(platform, 'get_email_config_summary', lambda: {})(),
            'payment_gateways': payment_gateways  # ✅ FIXED
        })
        
        return Response({
            'success': True,
            'platform': data
        })
        
    except Exception as e:
        logger.error(f"Get current settings failed: {e}")
        return Response({
            'success': False,
            'error': 'Failed to load platform settings'
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['PATCH'])
@permission_classes([permissions.IsAdminUser])
def update_platform_settings(request):
    """
    PATCH /api/platforms/settings/update/
    Updates platform settings (general, email, etc.)
    Matches frontend platformService.updatePlatform()
    """
    try:
        # Get current platform (same logic as get_current_platform_settings)
        platform = Platform.objects.filter(
            is_active=True,
            is_default=True
        ).first() or Platform.objects.filter(is_active=True).first()
        
        if not platform:
            return Response({
                'success': False,
                'error': 'No active platform found'
            }, status=status.HTTP_404_NOT_FOUND)

        data = request.data
        
        # Update general settings
        update_fields = [
            'name', 'description', 'domain', 'support_email', 'contact_email',
            'contact_phone', 'address', 'primary_color', 'secondary_color',
            'accent_color', 'maintenance_mode', 'requires_email_verification', 'is_active'
        ]
        
        updated = False
        for field in update_fields:
            if field in data:
                setattr(platform, field, data[field])
                updated = True
        
        if updated:
            platform.save()
        
        return Response({
            'success': True,
            'message': 'Platform settings updated successfully',
            'platform_id': platform.platform_id
        })
        
    except Exception as e:
        logger.error(f"Update settings failed: {e}")
        return Response({
            'success': False,
            'error': str(e)
        }, status=status.HTTP_400_BAD_REQUEST)


@api_view(['POST'])
@permission_classes([permissions.IsAdminUser])
def test_email_connection_view(request):
    """
    POST /api/platforms/settings/test-email/
    Tests email configuration
    Matches frontend platformService.testEmailConnection()
    """
    try:
        platform = Platform.objects.filter(
            is_active=True,
            is_default=True
        ).first() or Platform.objects.filter(is_active=True).first()
        
        if not platform:
            return Response({
                'success': False,
                'error': 'No active platform found'
            }, status=status.HTTP_404_NOT_FOUND)

        success, message = platform.test_email_connection()
        
        return Response({
            'success': success,
            'message': message
        })
        
    except Exception as e:
        logger.error(f"Email test failed: {e}")
        return Response({
            'success': False,
            'message': f'Connection test failed: {str(e)}'
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['POST'])
@permission_classes([permissions.IsAdminUser])
@parser_classes([MultiPartParser, FormParser])
def upload_logo(request):
    """
    POST /api/platforms/settings/upload-logo/
    Uploads platform logo
    Matches frontend platformService.uploadLogo()
    """
    try:
        platform = Platform.objects.filter(
            is_active=True,
            is_default=True
        ).first() or Platform.objects.filter(is_active=True).first()
        
        if not platform:
            return Response({
                'success': False,
                'error': 'No active platform found'
            }, status=status.HTTP_404_NOT_FOUND)

        if 'logo' not in request.FILES:
            return Response({
                'success': False,
                'error': 'No logo file provided'
            }, status=status.HTTP_400_BAD_REQUEST)

        logo_file = request.FILES['logo']
        
        # Validate file (same as frontend)
        if logo_file.size > 2 * 1024 * 1024:  # 2MB
            return Response({
                'success': False,
                'error': 'Logo file too large (max 2MB)'
            }, status=status.HTTP_400_BAD_REQUEST)

        allowed_types = ['image/png', 'image/jpeg', 'image/jpg', 'image/svg+xml']
        if logo_file.content_type not in allowed_types:
            return Response({
                'success': False,
                'error': 'Invalid file type. Use PNG, JPG, or SVG'
            }, status=status.HTTP_400_BAD_REQUEST)

        # Save logo using custom upload path
        platform.logo = logo_file
        platform.save()
        
        return Response({
            'success': True,
            'message': 'Logo uploaded successfully',
            'url': platform.logo_url
        })
        
    except Exception as e:
        logger.error(f"Logo upload failed: {e}")
        return Response({
            'success': False,
            'error': 'Upload failed'
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

@api_view(['POST'])
@permission_classes([permissions.IsAdminUser])
@parser_classes([MultiPartParser, FormParser])
def upload_favicon(request):
    """
    POST /api/platforms/settings/upload-favicon/
    """
    try:
        platform = Platform.objects.filter(
            is_active=True,
            is_default=True
        ).first() or Platform.objects.filter(is_active=True).first()
        
        if not platform:
            return Response({
                'success': False,
                'error': 'No active platform found'
            }, status=status.HTTP_404_NOT_FOUND)

        if 'favicon' not in request.FILES:
            return Response({
                'success': False,
                'error': 'No favicon file provided'
            }, status=status.HTTP_400_BAD_REQUEST)

        favicon_file = request.FILES['favicon']
        
        # Validate file
        if favicon_file.size > 1 * 1024 * 1024:  # 1MB
            return Response({
                'success': False,
                'error': 'Favicon file too large (max 1MB)'
            }, status=status.HTTP_400_BAD_REQUEST)

        allowed_types = ['image/x-icon', 'image/png']
        if favicon_file.content_type not in allowed_types:
            return Response({
                'success': False,
                'error': 'Invalid file type. Use ICO or PNG'
            }, status=status.HTTP_400_BAD_REQUEST)

        # Save favicon
        platform.favicon = favicon_file
        platform.save()
        
        # ✅ FIXED: Safe favicon URL
        favicon_url = platform.favicon.url if platform.favicon else None
        
        return Response({
            'success': True,
            'message': 'Favicon uploaded successfully',
            'url': favicon_url  # ✅ FIXED
        })
        
    except Exception as e:
        logger.error(f"Favicon upload failed: {e}")
        return Response({
            'success': False,
            'error': 'Upload failed'
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
