from rest_framework import generics, permissions, status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response
from rest_framework_simplejwt.tokens import RefreshToken
from django.shortcuts import get_object_or_404
from django.core.exceptions import ValidationError

from apps.users.permissions import IsAdminOrReadOnly
from .models import OAuthProvider, SocialAccount, LoginAttempt
from .serializers import (
    OAuthProviderSerializer,
    OAuthProviderAdminSerializer,
    SocialAccountSerializer,
    LoginAttemptSerializer,
    OAuthAuthorizationSerializer,
    OAuthCallbackSerializer,
    OAuthLoginResponseSerializer
)
from .services import OAuthService, OAuthProviderManager


class OAuthProviderListView(generics.ListAPIView):
    """List available OAuth providers"""
    
    queryset = OAuthProvider.objects.filter(is_active=True)
    serializer_class = OAuthProviderSerializer
    permission_classes = [permissions.AllowAny]


class OAuthProviderAdminView(generics.ListCreateAPIView):
    """Admin view for OAuth providers"""
    
    queryset = OAuthProvider.objects.all()
    serializer_class = OAuthProviderAdminSerializer
    permission_classes = [permissions.IsAuthenticated, IsAdminOrReadOnly]


class OAuthProviderAdminDetailView(generics.RetrieveUpdateDestroyAPIView):
    """Admin detail view for OAuth providers"""
    
    queryset = OAuthProvider.objects.all()
    serializer_class = OAuthProviderAdminSerializer
    permission_classes = [permissions.IsAuthenticated, IsAdminOrReadOnly]


@api_view(['POST'])
@permission_classes([permissions.AllowAny])
def get_authorization_url(request):
    """Get OAuth authorization URL"""
    
    serializer = OAuthAuthorizationSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)
    
    provider_name = serializer.validated_data['provider']
    redirect_uri = serializer.validated_data['redirect_uri']
    state = serializer.validated_data.get('state')
    
    try:
        oauth_service = OAuthService(provider_name)
        auth_url = oauth_service.generate_authorization_url(
            redirect_uri=redirect_uri,
            user=request.user if request.user.is_authenticated else None,
            state=state
        )
        
        return Response({
            'authorization_url': auth_url,
            'provider': provider_name
        })
    
    except ValidationError as e:
        return Response({
            'error': str(e)
        }, status=status.HTTP_400_BAD_REQUEST)


@api_view(['POST'])
@permission_classes([permissions.AllowAny])
def oauth_callback(request):
    """Handle OAuth callback"""
    
    serializer = OAuthCallbackSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)
    
    provider_name = serializer.validated_data['provider']
    code = serializer.validated_data['code']
    state = serializer.validated_data['state']
    redirect_uri = serializer.validated_data['redirect_uri']
    
    try:
        oauth_service = OAuthService(provider_name)
        
        # Exchange code for token
        token_data, oauth_state = oauth_service.exchange_code_for_token(
            code=code,
            redirect_uri=redirect_uri,
            state=state
        )
        
        # Get user info
        user_info = oauth_service.get_user_info(token_data['access_token'])
        
        # Authenticate or create user
        user, social_account, is_new_user = oauth_service.authenticate_or_create_user(
            token_data=token_data,
            user_info=user_info,
            request=request
        )
        
        # Generate JWT tokens
        refresh = RefreshToken.for_user(user)
        
        # Prepare response
        response_data = {
            'access_token': str(refresh.access_token),
            'refresh_token': str(refresh),
            'user': {
                'id': user.id,
                'email': user.email,
                'first_name': user.first_name,
                'last_name': user.last_name,
                'role': user.role,
                'avatar': user.avatar.url if user.avatar else None,
                'is_verified': user.is_verified,
            },
            'is_new_user': is_new_user,
            'social_account': SocialAccountSerializer(social_account).data
        }
        
        response_serializer = OAuthLoginResponseSerializer(response_data)
        
        return Response(response_serializer.data, status=status.HTTP_200_OK)
    
    except ValidationError as e:
        return Response({
            'error': str(e)
        }, status=status.HTTP_400_BAD_REQUEST)
    
    except Exception as e:
        return Response({
            'error': 'OAuth authentication failed'
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class UserSocialAccountsView(generics.ListAPIView):
    """List user's connected social accounts"""
    
    serializer_class = SocialAccountSerializer
    permission_classes = [permissions.IsAuthenticated]
    
    def get_queryset(self):
        return SocialAccount.objects.filter(user=self.request.user)


@api_view(['POST'])
@permission_classes([permissions.IsAuthenticated])
def disconnect_social_account(request, account_id):
    """Disconnect a social account"""
    
    social_account = get_object_or_404(
        SocialAccount, 
        id=account_id, 
        user=request.user
    )
    
    # Check if this is the only login method
    if not request.user.has_usable_password() and request.user.social_accounts.count() == 1:
        return Response({
            'error': 'Cannot disconnect the only login method. Please set a password first.'
        }, status=status.HTTP_400_BAD_REQUEST)
    
    provider_name = social_account.provider.display_name
    social_account.delete()
    
    return Response({
        'message': f'Successfully disconnected from {provider_name}'
    })


@api_view(['POST'])
@permission_classes([permissions.IsAuthenticated])
def set_primary_social_account(request, account_id):
    """Set a social account as primary"""
    
    social_account = get_object_or_404(
        SocialAccount,
        id=account_id,
        user=request.user
    )
    
    # Remove primary status from other accounts
    SocialAccount.objects.filter(user=request.user).update(is_primary=False)
    
    # Set this account as primary
    social_account.is_primary = True
    social_account.save()
    
    return Response({
        'message': f'{social_account.provider.display_name} set as primary login method'
    })


class LoginAttemptListView(generics.ListAPIView):
    """List login attempts (admin only)"""
    
    queryset = LoginAttempt.objects.all()
    serializer_class = LoginAttemptSerializer
    permission_classes = [permissions.IsAuthenticated, IsAdminOrReadOnly]
    ordering = ['-created_at']
    
    def get_queryset(self):
        queryset = super().get_queryset()
        
        # Filter by email if provided
        email = self.request.query_params.get('email')
        if email:
            queryset = queryset.filter(email__icontains=email)
        
        # Filter by status if provided
        status_filter = self.request.query_params.get('status')
        if status_filter:
            queryset = queryset.filter(status=status_filter)
        
        # Filter by provider if provided
        provider = self.request.query_params.get('provider')
        if provider:
            queryset = queryset.filter(provider__name=provider)
        
        return queryset


@api_view(['GET'])
@permission_classes([permissions.IsAuthenticated])
def user_login_history(request):
    """Get current user's login history"""
    
    attempts = LoginAttempt.objects.filter(
        email=request.user.email
    ).order_by('-created_at')[:20]  # Last 20 attempts
    
    serializer = LoginAttemptSerializer(attempts, many=True)
    
    return Response({
        'login_history': serializer.data
    })


@api_view(['POST'])
@permission_classes([permissions.IsAuthenticated, IsAdminOrReadOnly])
def setup_default_providers(request):
    """Setup default OAuth providers (admin only)"""
    
    try:
        OAuthProviderManager.setup_default_providers()
        
        return Response({
            'message': 'Default OAuth providers setup completed'
        })
    
    except Exception as e:
        return Response({
            'error': f'Failed to setup providers: {str(e)}'
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
