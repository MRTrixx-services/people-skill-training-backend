from django.utils.deprecation import MiddlewareMixin
from django.http import JsonResponse
from django.utils import timezone
from .models import Platform, PlatformAPILog
import time
import logging

logger = logging.getLogger(__name__)


class PlatformAPIKeyMiddleware(MiddlewareMixin):
    """
    Multi-platform authentication using API keys
    - Validates API key and attaches platform to request
    - Excludes admin, static, and media paths
    - Logs all API requests
    """
    
    # ✅ Paths that don't require API key at all
    EXCLUDED_PATHS = [
        '/admin/',
        '/djadmin/',
        '/static/',
        '/media/',
        '/favicon.ico',
        '/api/docs/',
        '/swagger/',
        '/redoc/',
        '/api/platforms/create/',  # Platform creation endpoint
    ]
    
    def process_request(self, request):
        """Process incoming request and attach platform"""
        
        # ✅ Skip completely excluded paths (no API key needed)
        if self._is_excluded_path(request.path):
            # Set default platform for admin paths
            if request.path.startswith(('/admin/', '/djadmin/')):
                try:
                    request.platform = Platform.objects.get(
                        is_default=True, 
                        is_active=True
                    )
                except Platform.DoesNotExist:
                    request.platform = None
            else:
                request.platform = None
            return None
        
        # ✅ For all /api/ paths, API key is required
        api_key = self._get_api_key(request)
        
        if not api_key:
            return self._error_response(
                'API key is required',
                'MISSING_API_KEY',
                'Please provide X-Platform-API-Key header',
                401
            )
        
        # Validate API key format
        if not api_key.startswith('pk_'):
            return self._error_response(
                'Invalid API key format',
                'INVALID_API_KEY_FORMAT',
                'API key must start with pk_',
                401
            )
        
        # Find platform by API key
        try:
            platform = Platform.objects.select_related().get(
                api_key=api_key,
                is_active=True
            )
        except Platform.DoesNotExist:
            logger.warning(f"Invalid API key attempted: {api_key[:10]}...")
            return self._error_response(
                'Invalid API key',
                'INVALID_API_KEY',
                'The provided API key is not valid or inactive',
                401
            )
        
        # Check maintenance mode
        if platform.maintenance_mode:
            return self._error_response(
                'Platform is under maintenance',
                'MAINTENANCE_MODE',
                f'{platform.name} is currently under maintenance. Please try again later.',
                503
            )
        
        # Check IP whitelist (if configured)
        if platform.allowed_ip_addresses:
            client_ip = self._get_client_ip(request)
            if client_ip not in platform.allowed_ip_addresses:
                logger.warning(f"IP not allowed for {platform.name}: {client_ip}")
                return self._error_response(
                    'IP address not allowed',
                    'IP_NOT_ALLOWED',
                    f'Your IP ({client_ip}) is not authorized for this platform',
                    403
                )
        
        # ✅ Attach platform to request (available in views and serializers)
        request.platform = platform
        
        # Store request start time for performance logging
        request._platform_request_start = time.time()
        
        # Update last used timestamp (non-blocking)
        Platform.objects.filter(pk=platform.pk).update(
            last_used_at=timezone.now()
        )
        
        logger.debug(f"✅ Request authenticated for platform: {platform.name}")
        return None
    
    def process_response(self, request, response):
        """Log API request after response"""
        
        # Only log if platform was identified and timing was recorded
        if not (hasattr(request, 'platform') and 
                hasattr(request, '_platform_request_start')):
            return response
        
        try:
            # Calculate response time
            response_time_ms = int(
                (time.time() - request._platform_request_start) * 1000
            )
            
            # Prepare log data
            log_data = {
                'platform': request.platform,
                'endpoint': request.path[:500],
                'method': request.method,
                'ip_address': self._get_client_ip(request),
                'user_agent': request.META.get('HTTP_USER_AGENT', '')[:500],
                'status_code': response.status_code,
                'response_time_ms': response_time_ms,
                'authenticated_user': None,
                'error_message': ''
            }
            
            # Add authenticated user if available
            if hasattr(request, 'user') and request.user.is_authenticated:
                log_data['authenticated_user'] = request.user
            
            # Add error message for failed requests
            if response.status_code >= 400:
                try:
                    log_data['error_message'] = str(response.content[:1000])
                except:
                    log_data['error_message'] = 'Error content unavailable'
            
            # Create log entry
            PlatformAPILog.objects.create(**log_data)
            
        except Exception as e:
            # Don't fail the request if logging fails
            logger.error(f"Failed to log API request: {e}")
        
        # Add platform info to response headers (for debugging)
        if hasattr(request, 'platform') and request.platform:
            response['X-Platform-ID'] = request.platform.platform_id
            response['X-Platform-Name'] = request.platform.name
        
        return response
    
    def _is_excluded_path(self, path):
        """Check if path is excluded from API key requirement"""
        return any(path.startswith(excluded) for excluded in self.EXCLUDED_PATHS)
    
    def _get_api_key(self, request):
        """Extract API key from request headers or query params"""
        return (
            request.headers.get('X-Platform-API-Key') or 
            request.headers.get('X-Api-Key') or
            request.GET.get('api_key')  # For testing only
        )
    
    @staticmethod
    def _get_client_ip(request):
        """Get real client IP address"""
        x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
        if x_forwarded_for:
            ip = x_forwarded_for.split(',')[0].strip()
        else:
            ip = request.META.get('REMOTE_ADDR', '127.0.0.1')
        return ip
    
    @staticmethod
    def _error_response(error, error_code, message, status_code):
        """Generate consistent error response"""
        return JsonResponse({
            'success': False,
            'error': error,
            'error_code': error_code,
            'message': message
        }, status=status_code)
