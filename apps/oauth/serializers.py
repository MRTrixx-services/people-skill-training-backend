from rest_framework import serializers
from .models import OAuthProvider, SocialAccount, LoginAttempt


class OAuthProviderSerializer(serializers.ModelSerializer):
    """Serializer for OAuth providers (public info only)"""
    
    class Meta:
        model = OAuthProvider
        fields = [
            'name', 'display_name', 'button_color', 'icon_class', 'is_active'
        ]
        read_only_fields = ['name', 'display_name', 'button_color', 'icon_class', 'is_active']


class OAuthProviderAdminSerializer(serializers.ModelSerializer):
    """Serializer for OAuth providers (admin only)"""
    
    class Meta:
        model = OAuthProvider
        fields = '__all__'
        extra_kwargs = {
            'client_secret': {'write_only': True}
        }


class SocialAccountSerializer(serializers.ModelSerializer):
    """Serializer for user's social accounts"""
    
    provider_name = serializers.CharField(source='provider.display_name', read_only=True)
    provider_icon = serializers.CharField(source='provider.icon_class', read_only=True)
    is_token_expired = serializers.BooleanField(read_only=True)
    
    class Meta:
        model = SocialAccount
        fields = [
            'id', 'provider_name', 'provider_icon', 'email', 'first_name', 
            'last_name', 'avatar_url', 'profile_url', 'is_primary', 
            'is_token_expired', 'created_at', 'last_login'
        ]
        read_only_fields = [
            'id', 'provider_name', 'provider_icon', 'email', 'first_name',
            'last_name', 'avatar_url', 'profile_url', 'is_token_expired',
            'created_at', 'last_login'
        ]


class OAuthAuthorizationSerializer(serializers.Serializer):
    """Serializer for OAuth authorization request"""
    
    provider = serializers.CharField()
    redirect_uri = serializers.URLField()
    state = serializers.CharField(required=False)


class OAuthCallbackSerializer(serializers.Serializer):
    """Serializer for OAuth callback"""
    
    provider = serializers.CharField()
    code = serializers.CharField()
    state = serializers.CharField()
    redirect_uri = serializers.URLField()


class LoginAttemptSerializer(serializers.ModelSerializer):
    """Serializer for login attempts"""
    
    provider_name = serializers.CharField(source='provider.display_name', read_only=True)
    
    class Meta:
        model = LoginAttempt
        fields = [
            'id', 'email', 'attempt_type', 'status', 'provider_name',
            'ip_address', 'failure_reason', 'created_at'
        ]
        read_only_fields = '__all__'


class OAuthLoginResponseSerializer(serializers.Serializer):
    """Serializer for OAuth login response"""
    
    access_token = serializers.CharField()
    refresh_token = serializers.CharField()
    user = serializers.DictField()
    is_new_user = serializers.BooleanField()
    social_account = SocialAccountSerializer()
