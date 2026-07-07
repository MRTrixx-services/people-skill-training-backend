from rest_framework import serializers
from .models import User, UserProfile


def get_avatar_full_url(request, avatar_field):
    """Get full URL for avatar field"""
    if avatar_field and hasattr(avatar_field, 'url'):
        if request and hasattr(request, 'build_absolute_uri'):
            return request.build_absolute_uri(avatar_field.url)
        else:
            return avatar_field.url
    return None


class UserSerializer(serializers.ModelSerializer):
    """Basic user serializer with platform info"""
    
    full_name = serializers.CharField(read_only=True)
    avatar = serializers.SerializerMethodField()
    is_shared = serializers.BooleanField(source='is_shared_user', read_only=True)
    platform_info = serializers.SerializerMethodField()
    
    class Meta:
        model = User
        fields = [
            'id', 'email', 'first_name', 'last_name', 'full_name', 
            'role', 'avatar', 'phone', 'is_verified', 'is_active','company',
            'is_shared', 'platform_info',
            'created_at', 'updated_at'
        ]
        read_only_fields = ('id', 'is_verified', 'created_at', 'updated_at')
    
    def get_avatar(self, obj):
        """Get full URL for avatar"""
        request = self.context.get('request')
        return get_avatar_full_url(request, obj.avatar)
    
    def get_platform_info(self, obj):
        """Get platform information"""
        if obj.platform:
            return {
                'id': obj.platform.id,
                'platform_id': obj.platform.platform_id,
                'name': obj.platform.name
            }
        return None


class UserProfileSerializer(serializers.ModelSerializer):
    """User profile serializer"""
    
    class Meta:
        model = UserProfile
        fields = [
            'bio', 'location', 'timezone', 'website', 'linkedin', 
            'twitter', 'github', 'show_email_publicly', 'show_phone_publicly', 
            'allow_direct_messages', 'preferences', 'notification_settings',
            'created_at', 'updated_at'
        ]
        read_only_fields = ('created_at', 'updated_at')


class UserDetailSerializer(serializers.ModelSerializer):
    """Detailed user serializer with profile and platform"""
    
    profile = UserProfileSerializer(read_only=True)
    full_name = serializers.CharField(read_only=True)
    avatar = serializers.SerializerMethodField()
    is_shared = serializers.BooleanField(source='is_shared_user', read_only=True)
    platform_info = serializers.SerializerMethodField()
    accessible_platforms = serializers.SerializerMethodField()
    
    class Meta:
        model = User
        fields = [
            'id', 'email', 'first_name', 'last_name', 'full_name', 
            'role', 'avatar', 'phone', 'is_verified', 'is_active',
            'is_shared', 'platform_info', 'accessible_platforms',
            'profile', 'created_at', 'updated_at'
        ]
        read_only_fields = ('id', 'email', 'role', 'is_verified', 'created_at', 'updated_at')
    
    def get_avatar(self, obj):
        """Get full URL for avatar"""
        request = self.context.get('request')
        return get_avatar_full_url(request, obj.avatar)
    
    def get_platform_info(self, obj):
        """Get platform information"""
        if obj.platform:
            return {
                'id': obj.platform.id,
                'platform_id': obj.platform.platform_id,
                'name': obj.platform.name
            }
        return None
    
    def get_accessible_platforms(self, obj):
        """Get list of platforms user can access"""
        platforms = obj.get_platforms()
        return [{
            'id': p.id,
            'platform_id': p.platform_id,
            'name': p.name
        } for p in platforms]


class UserUpdateSerializer(serializers.ModelSerializer):
    """User update serializer"""
    
    profile = UserProfileSerializer(required=False)
    avatar = serializers.ImageField(required=False, write_only=True)
    
    class Meta:
        model = User
        fields = [
            'first_name', 'last_name', 'avatar', 'phone',  'company', 'profile'
        ]
    
    def update(self, instance, validated_data):
        # Handle profile data separately
        profile_data = validated_data.pop('profile', None)
        
        # Update user fields
        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        instance.save()
        
        # Update profile if provided
        if profile_data and hasattr(instance, 'profile'):
            profile = instance.profile
            for attr, value in profile_data.items():
                setattr(profile, attr, value)
            profile.save()
        
        return instance


class UserListSerializer(serializers.ModelSerializer):
    """Serializer for listing users with platform info"""
    
    full_name = serializers.CharField(read_only=True)
    avatar = serializers.SerializerMethodField()
    is_shared = serializers.BooleanField(source='is_shared_user', read_only=True)
    platform_name = serializers.SerializerMethodField()
    
    class Meta:
        model = User
        fields = [
            'id', 'email', 'first_name', 'last_name', 'full_name',
            'role', 'avatar', 'is_verified', 'is_active', 
            'is_shared', 'platform_name', 'created_at'
        ]
    
    def get_avatar(self, obj):
        """Get full URL for avatar"""
        request = self.context.get('request')
        return get_avatar_full_url(request, obj.avatar)
    
    def get_platform_name(self, obj):
        """Get platform name if applicable"""
        if obj.platform:
            return obj.platform.name
        return "All Platforms" if obj.is_shared_user() else None
