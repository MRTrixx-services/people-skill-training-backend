from rest_framework import serializers
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer
from django.contrib.auth import authenticate
from django.contrib.auth.password_validation import validate_password
from apps.users.models import User

import logging

logger = logging.getLogger(__name__)
class CustomTokenObtainPairSerializer(TokenObtainPairSerializer):
    """Custom JWT token serializer with user data and platform info"""
    
    @classmethod
    def get_token(cls, user):
        token = super().get_token(user)
        
        # Add custom claims
        token['user_id'] = user.id
        token['email'] = user.email
        token['role'] = user.role
        token['first_name'] = user.first_name
        token['last_name'] = user.last_name
        
        # Add platform info
        if hasattr(user, 'platform') and user.platform:
            token['platform_id'] = user.platform.platform_id
            token['platform_name'] = user.platform.name
        
        return token

    # def validate(self, attrs):
    #     data = super().validate(attrs)
        
    #     # Platform info
    #     platform_info = None
    #     if hasattr(self.user, 'platform') and self.user.platform:
    #         platform_info = {
    #             'id': self.user.platform.id,
    #             'platform_id': self.user.platform.platform_id,
    #             'name': self.user.platform.name,
    #             'logo_url': self.user.platform.logo_url,
    #             'primary_color': self.user.platform.primary_color,
    #         }
        
    #     # Add user data to response
    #     data['user'] = {
    #         'id': self.user.id,
    #         'email': self.user.email,
    #         'first_name': self.user.first_name,
    #         'last_name': self.user.last_name,
    #         'full_name': self.user.full_name,
    #         'role': self.user.role,
    #         'avatar': self.user.avatar.url if self.user.avatar else None,
    #         'is_verified': self.user.is_verified,
    #         'platform': platform_info,
    #     }
        
    #     return data

    def validate(self, attrs):
        """Validate with platform context"""
        # ✅ Import the module-level _thread_locals from users.models
        from apps.users.models import _thread_locals
        
        # Get platform from request (set by PlatformAPIKeyMiddleware)
        request = self.context.get('request')
        platform = getattr(request, 'platform', None)
        
        email = attrs.get(self.username_field)
        logger.info(f"🔐 Login attempt: {email} | Platform: {platform}")
        
        # ✅ Store platform in thread-local for UserManager.get_by_natural_key
        _thread_locals.platform = platform
        
        # Call parent validation (will use our custom get_by_natural_key)
        try:
            data = super().validate(attrs)
            user = self.user
            
            logger.info(f"✅ Login successful: {user.email} (Role: {user.role})")
            
            # Add platform info to response
            platform_info = None
            if hasattr(user, 'platform') and user.platform:
                platform_info = {
                    'id': user.platform.id,
                    'platform_id': user.platform.platform_id,
                    'name': user.platform.name,
                    'logo_url': user.platform.logo_url,
                    'primary_color': user.platform.primary_color,
                }
            
            # Add user data to response
            data['user'] = {
                'id': user.id,
                'email': user.email,
                'first_name': user.first_name,
                'last_name': user.last_name,
                'full_name': user.full_name,
                'role': user.role,
                'avatar': user.avatar.url if user.avatar else None,
                'is_verified': user.is_verified,
                'platform': platform_info,
            }
            
            return data
            
        except Exception as e:
            logger.error(f"❌ Login failed for {email}: {str(e)}")
            raise
        finally:
            # ✅ Cleanup thread-local
            if hasattr(_thread_locals, 'platform'):
                delattr(_thread_locals, 'platform')


class UserRegistrationSerializer(serializers.ModelSerializer):
    """User registration serializer with automatic platform detection from middleware"""
    
    password = serializers.CharField(write_only=True, validators=[validate_password])
    password_confirm = serializers.CharField(write_only=True)
    company = serializers.CharField(required=False, allow_blank=True, max_length=255)
    phone = serializers.CharField(required=True, max_length=20)
    
    class Meta:
        model = User
        fields = (
            'email', 
            'first_name', 
            'last_name', 
            'phone',
            'company',
            'password', 
            'password_confirm', 
            'role',
        )
        
    def validate(self, attrs):
        """Validate password match and platform requirement"""
        
        # Password validation
        if attrs['password'] != attrs['password_confirm']:
            raise serializers.ValidationError({
                "password": "Passwords don't match"
            })
        
        # ✅ Get platform from request context (set by middleware)
        request = self.context.get('request')
        platform = getattr(request, 'platform', None)
        
        # ✅ For attendees, platform is required
        role = attrs.get('role', 'attendee')
        if role == 'attendee' and not platform:
            raise serializers.ValidationError({
                "role": "Attendee registration requires a valid platform API key. Please contact support."
            })
        
        # Store platform for create method
        attrs['_platform'] = platform
        
        return attrs
    
    def validate_email(self, value):
        """Validate email uniqueness based on role and platform"""
        
        request = self.context.get('request')
        platform = getattr(request, 'platform', None)
        role = self.initial_data.get('role', 'attendee')
        
        # For admins/instructors: email must be globally unique
        if role in ['admin', 'instructor']:
            if User.objects.filter(
                email=value, 
                role__in=['admin', 'instructor']
            ).exists():
                raise serializers.ValidationError(
                    f"A {role} with this email already exists"
                )
        
        # For attendees: email must be unique per platform
        elif role == 'attendee' and platform:
            if User.objects.filter(
                email=value, 
                platform=platform,
                role='attendee'
            ).exists():
                raise serializers.ValidationError(
                    f"An attendee with this email already exists on {platform.name}"
                )
        
        return value
    
    def validate_role(self, value):
        """Validate role"""
        if value not in ['instructor', 'attendee', 'admin']:
            raise serializers.ValidationError(
                "Role must be 'instructor', 'attendee', or 'admin'"
            )
        return value
    
    def create(self, validated_data):
        """Create user with platform from middleware"""
        
        # Remove extra fields
        validated_data.pop('password_confirm')
        password = validated_data.pop('password')
        
        # ✅ Get platform from validated data (set in validate method)
        platform = validated_data.pop('_platform', None)
        
        # ✅ Create user with platform
        user = User.objects.create_user(
            password=password,
            platform=platform,  # Will be None for instructors, set for attendees
            **validated_data
        )
        
        return user


class EmailVerificationSerializer(serializers.Serializer):
    """Email verification serializer"""
    
    token = serializers.CharField(required=True)
    email = serializers.EmailField(required=True)
    
    def validate_email(self, value):
        if not User.objects.filter(email=value).exists():
            raise serializers.ValidationError("User with this email does not exist")
        return value


class PasswordChangeSerializer(serializers.Serializer):
    """Password change serializer"""
    
    old_password = serializers.CharField(required=True, write_only=True)
    new_password = serializers.CharField(
        required=True, 
        write_only=True, 
        validators=[validate_password]
    )
    new_password_confirm = serializers.CharField(required=True, write_only=True)
    
    def validate(self, attrs):
        if attrs['new_password'] != attrs['new_password_confirm']:
            raise serializers.ValidationError({
                "new_password": "New passwords don't match"
            })
        return attrs
    
    def validate_old_password(self, value):
        user = self.context['request'].user
        if not user.check_password(value):
            raise serializers.ValidationError("Old password is incorrect")
        return value


class PasswordResetRequestSerializer(serializers.Serializer):
    """Password reset request serializer"""
    
    email = serializers.EmailField(required=True)
    
    def validate_email(self, value):
        if not User.objects.filter(email=value).exists():
            raise serializers.ValidationError("User with this email does not exist")
        return value


class PasswordResetConfirmSerializer(serializers.Serializer):
    """Password reset confirmation serializer"""
    
    token = serializers.CharField(required=True)
    email = serializers.EmailField(required=True)
    new_password = serializers.CharField(
        required=True, 
        write_only=True, 
        validators=[validate_password]
    )
    new_password_confirm = serializers.CharField(required=True, write_only=True)
    
    def validate(self, attrs):
        if attrs['new_password'] != attrs['new_password_confirm']:
            raise serializers.ValidationError({
                "new_password": "Passwords don't match"
            })
        return attrs
    
    def validate_email(self, value):
        if not User.objects.filter(email=value).exists():
            raise serializers.ValidationError("User with this email does not exist")
        return value


class UserProfileSerializer(serializers.ModelSerializer):
    """User profile serializer with platform info"""
    
    full_name = serializers.CharField(read_only=True)
    platform_info = serializers.SerializerMethodField()
    
    class Meta:
        model = User
        fields = (
            'id', 
            'email', 
            'first_name', 
            'last_name', 
            'full_name', 
            'role', 
            'avatar', 
            'phone', 
            'company',
            'is_verified',
            'platform_info', 
            'created_at', 
            'last_login'
        )
        read_only_fields = (
            'id', 
            'email', 
            'role', 
            'is_verified', 
            'platform_info', 
            'created_at', 
            'last_login'
        )
    
    def get_platform_info(self, obj):
        """Get platform information"""
        if hasattr(obj, 'platform') and obj.platform:
            return {
                'id': obj.platform.id,
                'platform_id': obj.platform.platform_id,
                'name': obj.platform.name,
                'logo_url': obj.platform.logo_url,
                'primary_color': obj.platform.primary_color,
            }
        return None


class UserListSerializer(serializers.ModelSerializer):
    """Simplified user list serializer with platform"""
    
    full_name = serializers.CharField(read_only=True)
    platform_name = serializers.CharField(source='platform.name', read_only=True)
    
    class Meta:
        model = User
        fields = (
            'id', 
            'email', 
            'full_name', 
            'role', 
            'avatar', 
            'is_verified', 
            'platform_name',
            'company'
        )
