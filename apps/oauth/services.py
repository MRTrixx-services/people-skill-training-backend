import requests
import secrets
import base64
from datetime import datetime, timedelta
from django.conf import settings
from django.utils import timezone
from django.core.exceptions import ValidationError
from urllib.parse import urlencode, parse_qs, urlparse
from rest_framework_simplejwt.tokens import RefreshToken

from apps.users.models import User
from .models import OAuthProvider, SocialAccount, OAuthState, LoginAttempt


class OAuthService:
    """Service for handling OAuth authentication"""
    
    def __init__(self, provider_name):
        try:
            self.provider = OAuthProvider.objects.get(name=provider_name, is_active=True)
        except OAuthProvider.DoesNotExist:
            raise ValidationError(f"OAuth provider '{provider_name}' not found or inactive")
    
    def generate_authorization_url(self, redirect_uri, user=None, **kwargs):
        """Generate OAuth authorization URL"""
        
        # Generate secure state
        state = secrets.token_urlsafe(32)
        
        # Store state for verification
        expires_at = timezone.now() + timedelta(minutes=10)  # 10 minute expiry
        OAuthState.objects.create(
            state=state,
            provider=self.provider,
            redirect_uri=redirect_uri,
            user=user,
            context_data=kwargs,
            expires_at=expires_at
        )
        
        # Build authorization URL
        params = {
            'client_id': self.provider.client_id,
            'redirect_uri': redirect_uri,
            'scope': self.provider.scope,
            'state': state,
            'response_type': 'code',
        }
        
        # Provider-specific parameters
        if self.provider.name == 'google':
            params['access_type'] = 'offline'
            params['prompt'] = 'consent'
        elif self.provider.name == 'microsoft':
            params['response_mode'] = 'query'
        
        # Add any additional parameters
        params.update(kwargs)
        
        return f"{self.provider.authorization_url}?{urlencode(params)}"
    
    def exchange_code_for_token(self, code, redirect_uri, state):
        """Exchange authorization code for access token"""
        
        # Verify state
        try:
            oauth_state = OAuthState.objects.get(state=state, is_used=False)
            if not oauth_state.is_valid():
                raise ValidationError("OAuth state expired or invalid")
            
            # Mark state as used
            oauth_state.is_used = True
            oauth_state.save()
            
        except OAuthState.DoesNotExist:
            raise ValidationError("Invalid OAuth state")
        
        # Prepare token request
        headers = {
            'Content-Type': 'application/x-www-form-urlencoded',
            'Accept': 'application/json',
        }
        
        data = {
            'client_id': self.provider.client_id,
            'client_secret': self.provider.client_secret,
            'code': code,
            'redirect_uri': redirect_uri,
            'grant_type': 'authorization_code',
        }
        
        # Provider-specific authentication
        if self.provider.name in ['github']:
            headers['Accept'] = 'application/vnd.github.v3+json'
        elif self.provider.name in ['linkedin']:
            # LinkedIn uses basic auth
            credentials = f"{self.provider.client_id}:{self.provider.client_secret}"
            encoded_credentials = base64.b64encode(credentials.encode()).decode()
            headers['Authorization'] = f'Basic {encoded_credentials}'
        
        # Make token request
        response = requests.post(self.provider.token_url, headers=headers, data=data)
        
        if response.status_code != 200:
            raise ValidationError(f"Token exchange failed: {response.text}")
        
        token_data = response.json()
        
        if 'access_token' not in token_data:
            raise ValidationError("No access token received")
        
        return token_data, oauth_state
    
    def get_user_info(self, access_token):
        """Get user information from OAuth provider"""
        
        headers = {
            'Authorization': f'Bearer {access_token}',
            'Accept': 'application/json',
        }
        
        # Provider-specific headers
        if self.provider.name == 'github':
            headers['Accept'] = 'application/vnd.github.v3+json'
        
        response = requests.get(self.provider.user_info_url, headers=headers)
        
        if response.status_code != 200:
            raise ValidationError(f"Failed to get user info: {response.text}")
        
        user_data = response.json()
        
        # Normalize user data based on provider
        return self._normalize_user_data(user_data)
    
    def _normalize_user_data(self, raw_data):
        """Normalize user data from different providers"""
        
        normalized = {
            'provider_user_id': '',
            'email': '',
            'first_name': '',
            'last_name': '',
            'avatar_url': '',
            'profile_url': '',
            'raw_data': raw_data
        }
        
        if self.provider.name == 'google':
            normalized.update({
                'provider_user_id': raw_data.get('sub', ''),
                'email': raw_data.get('email', ''),
                'first_name': raw_data.get('given_name', ''),
                'last_name': raw_data.get('family_name', ''),
                'avatar_url': raw_data.get('picture', ''),
                'profile_url': raw_data.get('profile', ''),
            })
        
        elif self.provider.name == 'facebook':
            normalized.update({
                'provider_user_id': raw_data.get('id', ''),
                'email': raw_data.get('email', ''),
                'first_name': raw_data.get('first_name', ''),
                'last_name': raw_data.get('last_name', ''),
                'avatar_url': raw_data.get('picture', {}).get('data', {}).get('url', ''),
                'profile_url': raw_data.get('link', ''),
            })
        
        elif self.provider.name == 'linkedin':
            normalized.update({
                'provider_user_id': raw_data.get('id', ''),
                'email': raw_data.get('emailAddress', ''),
                'first_name': raw_data.get('firstName', ''),
                'last_name': raw_data.get('lastName', ''),
                'avatar_url': raw_data.get('pictureUrl', ''),
                'profile_url': raw_data.get('publicProfileUrl', ''),
            })
        
        elif self.provider.name == 'github':
            normalized.update({
                'provider_user_id': str(raw_data.get('id', '')),
                'email': raw_data.get('email', ''),
                'first_name': raw_data.get('name', '').split(' ')[0] if raw_data.get('name') else '',
                'last_name': ' '.join(raw_data.get('name', '').split(' ')[1:]) if raw_data.get('name') else '',
                'avatar_url': raw_data.get('avatar_url', ''),
                'profile_url': raw_data.get('html_url', ''),
            })
        
        elif self.provider.name == 'microsoft':
            normalized.update({
                'provider_user_id': raw_data.get('id', ''),
                'email': raw_data.get('mail', '') or raw_data.get('userPrincipalName', ''),
                'first_name': raw_data.get('givenName', ''),
                'last_name': raw_data.get('surname', ''),
                'avatar_url': '',  # Microsoft Graph requires separate API call
                'profile_url': '',
            })
        
        return normalized
    
    def authenticate_or_create_user(self, token_data, user_info, request=None):
        """Authenticate existing user or create new user from OAuth data"""
        
        # Calculate token expiry
        expires_at = None
        if 'expires_in' in token_data:
            expires_at = timezone.now() + timedelta(seconds=token_data['expires_in'])
        
        # Try to find existing social account
        try:
            social_account = SocialAccount.objects.get(
                provider=self.provider,
                provider_user_id=user_info['provider_user_id']
            )
            
            # Update token and user info
            social_account.access_token = token_data['access_token']
            social_account.refresh_token = token_data.get('refresh_token', social_account.refresh_token)
            social_account.token_expires_at = expires_at
            social_account.email = user_info['email']
            social_account.first_name = user_info['first_name']
            social_account.last_name = user_info['last_name']
            social_account.avatar_url = user_info['avatar_url']
            social_account.profile_url = user_info['profile_url']
            social_account.extra_data = user_info['raw_data']
            social_account.last_login = timezone.now()
            social_account.save()
            
            user = social_account.user
            
            # Log successful login
            self._log_login_attempt(
                email=user.email,
                status='success',
                request=request
            )
            
            return user, social_account, False  # existing user
        
        except SocialAccount.DoesNotExist:
            # Try to find user by email
            user = None
            if user_info['email']:
                try:
                    user = User.objects.get(email=user_info['email'])
                except User.DoesNotExist:
                    pass
            
            # Create new user if not found
            if not user:
                user = User.objects.create_user(
                    email=user_info['email'],
                    first_name=user_info['first_name'],
                    last_name=user_info['last_name'],
                    is_verified=True,  # OAuth users are pre-verified
                    role='attendee'  # Default role
                )
                
                # Download and set avatar if available
                if user_info['avatar_url']:
                    try:
                        self._download_avatar(user, user_info['avatar_url'])
                    except Exception as e:
                        print(f"Failed to download avatar: {e}")
            
            # Create social account
            social_account = SocialAccount.objects.create(
                user=user,
                provider=self.provider,
                provider_user_id=user_info['provider_user_id'],
                email=user_info['email'],
                first_name=user_info['first_name'],
                last_name=user_info['last_name'],
                avatar_url=user_info['avatar_url'],
                profile_url=user_info['profile_url'],
                access_token=token_data['access_token'],
                refresh_token=token_data.get('refresh_token', ''),
                token_expires_at=expires_at,
                extra_data=user_info['raw_data'],
                is_primary=not user.social_accounts.exists(),  # First social account is primary
                last_login=timezone.now()
            )
            
            # Log successful login
            self._log_login_attempt(
                email=user.email,
                status='success',
                request=request
            )
            
            return user, social_account, True  # new user
    
    def _download_avatar(self, user, avatar_url):
        """Download and set user avatar from URL"""
        try:
            import requests
            from django.core.files.base import ContentFile
            from django.core.files.storage import default_storage
            import os
            
            response = requests.get(avatar_url, timeout=10)
            if response.status_code == 200:
                # Generate filename
                filename = f"avatars/oauth_{user.id}_{self.provider.name}.jpg"
                
                # Save file
                file_content = ContentFile(response.content)
                filename = default_storage.save(filename, file_content)
                
                # Update user avatar
                user.avatar = filename
                user.save()
                
        except Exception as e:
            print(f"Error downloading avatar: {e}")
    
    def _log_login_attempt(self, email, status, request=None):
        """Log login attempt for security tracking"""
        
        ip_address = '127.0.0.1'
        user_agent = ''
        
        if request:
            # Get client IP
            x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
            if x_forwarded_for:
                ip_address = x_forwarded_for.split(',')[0].strip()
            else:
                ip_address = request.META.get('REMOTE_ADDR', '127.0.0.1')
            
            user_agent = request.META.get('HTTP_USER_AGENT', '')
        
        LoginAttempt.objects.create(
            email=email,
            attempt_type='oauth',
            status=status,
            provider=self.provider,
            ip_address=ip_address,
            user_agent=user_agent
        )
    
    def refresh_token(self, social_account):
        """Refresh OAuth token"""
        
        if not social_account.refresh_token:
            raise ValidationError("No refresh token available")
        
        headers = {
            'Content-Type': 'application/x-www-form-urlencoded',
            'Accept': 'application/json',
        }
        
        data = {
            'client_id': self.provider.client_id,
            'client_secret': self.provider.client_secret,
            'refresh_token': social_account.refresh_token,
            'grant_type': 'refresh_token',
        }
        
        response = requests.post(self.provider.token_url, headers=headers, data=data)
        
        if response.status_code != 200:
            raise ValidationError(f"Token refresh failed: {response.text}")
        
        token_data = response.json()
        
        # Update social account
        social_account.access_token = token_data['access_token']
        if 'refresh_token' in token_data:
            social_account.refresh_token = token_data['refresh_token']
        
        if 'expires_in' in token_data:
            social_account.token_expires_at = timezone.now() + timedelta(seconds=token_data['expires_in'])
        
        social_account.save()
        
        return social_account


class OAuthProviderManager:
    """Manager for OAuth provider configurations"""
    
    @staticmethod
    def get_active_providers():
        """Get all active OAuth providers"""
        return OAuthProvider.objects.filter(is_active=True).order_by('display_name')
    
    @staticmethod
    def setup_default_providers():
        """Setup default OAuth providers"""
        
        providers = [
            {
                'name': 'google',
                'display_name': 'Google',
                'authorization_url': 'https://accounts.google.com/o/oauth2/v2/auth',
                'token_url': 'https://oauth2.googleapis.com/token',
                'user_info_url': 'https://www.googleapis.com/oauth2/v2/userinfo',
                'scope': 'openid email profile',
                'button_color': '#4285f4',
                'icon_class': 'fab fa-google',
            },
            {
                'name': 'facebook',
                'display_name': 'Facebook',
                'authorization_url': 'https://www.facebook.com/v18.0/dialog/oauth',
                'token_url': 'https://graph.facebook.com/v18.0/oauth/access_token',
                'user_info_url': 'https://graph.facebook.com/me?fields=id,name,email,first_name,last_name,picture',
                'scope': 'email public_profile',
                'button_color': '#1877f2',
                'icon_class': 'fab fa-facebook-f',
            },
            {
                'name': 'linkedin',
                'display_name': 'LinkedIn',
                'authorization_url': 'https://www.linkedin.com/oauth/v2/authorization',
                'token_url': 'https://www.linkedin.com/oauth/v2/accessToken',
                'user_info_url': 'https://api.linkedin.com/v2/people/~:(id,firstName,lastName,emailAddress,pictureUrl,publicProfileUrl)',
                'scope': 'r_liteprofile r_emailaddress',
                'button_color': '#0077b5',
                'icon_class': 'fab fa-linkedin-in',
            },
            {
                'name': 'github',
                'display_name': 'GitHub',
                'authorization_url': 'https://github.com/login/oauth/authorize',
                'token_url': 'https://github.com/login/oauth/access_token',
                'user_info_url': 'https://api.github.com/user',
                'scope': 'user:email',
                'button_color': '#333333',
                'icon_class': 'fab fa-github',
            },
            {
                'name': 'microsoft',
                'display_name': 'Microsoft',
                'authorization_url': 'https://login.microsoftonline.com/common/oauth2/v2.0/authorize',
                'token_url': 'https://login.microsoftonline.com/common/oauth2/v2.0/token',
                'user_info_url': 'https://graph.microsoft.com/v1.0/me',
                'scope': 'openid email profile User.Read',
                'button_color': '#00a1f1',
                'icon_class': 'fab fa-microsoft',
            },
        ]
        
        for provider_data in providers:
            provider, created = OAuthProvider.objects.get_or_create(
                name=provider_data['name'],
                defaults=provider_data
            )
            if created:
                print(f"Created OAuth provider: {provider.display_name}")
