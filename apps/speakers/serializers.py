from rest_framework import serializers
from django.contrib.auth import get_user_model
from django.db import transaction
from .models import Speaker

User = get_user_model()


def get_avatar_full_url(request, avatar_field):
    """Get full URL for avatar field"""
    if avatar_field and hasattr(avatar_field, 'url'):
        return avatar_field.url
    return None


def get_user_full_name(user):
    """Safely get user's full name"""
    if not user:
        return ''
    
    if hasattr(user, 'get_full_name'):
        return user.get_full_name()
    elif hasattr(user, 'full_name'):
        return user.full_name
    else:
        # Fallback: construct from first_name and last_name
        full_name = f'{user.first_name} {user.last_name}'.strip()
        return full_name if full_name else user.email


class SpeakerUserSerializer(serializers.ModelSerializer):
    """Simple user serializer for speaker context"""
    
    full_name = serializers.SerializerMethodField()
    
    class Meta:
        model = User
        fields = [
            'id', 'email', 'first_name', 'last_name', 'full_name', 
            'role', 'avatar', 'phone', 'is_verified'
        ]
        read_only_fields = [
            'id', 'email', 'first_name', 'last_name', 'full_name', 
            'role', 'avatar', 'phone', 'is_verified'
        ]
    
    def get_full_name(self, obj):
        return get_user_full_name(obj)


class SpeakerSerializer(serializers.ModelSerializer):
    """Complete speaker profile serializer - matches model fields"""
    
    user = serializers.SerializerMethodField()
    
    # User data fields for display
    full_name = serializers.SerializerMethodField()
    email = serializers.EmailField(source='user.email', read_only=True)
    avatar = serializers.SerializerMethodField()
    phone = serializers.CharField(source='user.phone', read_only=True)
    
    # User fields that can be updated
    first_name = serializers.CharField(source='user.first_name', required=False, write_only=True)
    last_name = serializers.CharField(source='user.last_name', required=False, write_only=True)
    user_avatar = serializers.ImageField(source='user.avatar', required=False, allow_null=True, write_only=True)
    user_phone = serializers.CharField(source='user.phone', required=False, write_only=True)
    
    class Meta:
        model = Speaker
        fields = [
            # User related fields
            'id', 'user', 'full_name', 'email', 'avatar', 'phone',
            'first_name', 'last_name', 'user_avatar', 'user_phone',
            
            # Basic profile fields - matches model
            'title', 'bio', 'company',
            
            # Status fields
            'is_verified', 'is_active',
            
            # Statistics
            'total_sessions',
            
            # Timestamps
            'created_at', 'updated_at'
        ]
        read_only_fields = [
            'id', 'total_sessions', 'is_verified', 'created_at', 'updated_at'
        ]
    
    def get_user(self, obj):
        """Return user data with proper context for full URLs"""
        if obj.user:
            user_serializer = SpeakerUserSerializer(obj.user, context=self.context)
            return user_serializer.data
        return None
 
    def get_full_name(self, obj):
        return get_user_full_name(obj.user)
    
    def get_avatar(self, obj):
        """Get full URL for avatar"""
        request = self.context.get('request')
        return get_avatar_full_url(request, obj.user.avatar) if obj.user else None
    
    def to_representation(self, instance):
        """Override to force full URLs for all avatar fields"""
        data = super().to_representation(instance)
        request = self.context.get('request')
        
        # Force full URL for main avatar field
        if instance.user and instance.user.avatar:
            if request and hasattr(request, 'build_absolute_uri'):
                data['avatar'] = request.build_absolute_uri(instance.user.avatar.url)
            else:
                data['avatar'] = instance.user.avatar.url
        
        # Force full URL for user.avatar field
        if data.get('user') and instance.user and instance.user.avatar:
            if request and hasattr(request, 'build_absolute_uri'):
                data['user']['avatar'] = request.build_absolute_uri(instance.user.avatar.url)
            else:
                data['user']['avatar'] = instance.user.avatar.url
        
        return data
 
    
    def update(self, instance, validated_data):
        user_data = validated_data.pop('user', {})
        with transaction.atomic():
            # Update user fields if provided
            if user_data:
                user = instance.user
                email_changed = False
                phone_changed = False

                for field, value in user_data.items():
                    if hasattr(user, field):
                        if field == 'email' and value != user.email:
                            email_changed = True
                        if field == 'phone' and value != getattr(user, 'phone', None):
                            phone_changed = True
                        setattr(user, field, value)
                # If phone changed, also update password to phone (safely hashed)
                if phone_changed:
                    user.password = make_password(user_data.get('phone'))
                user.save()
            
            # Update speaker fields
            for field, value in validated_data.items():
                setattr(instance, field, value)
            instance.save()
            return instance


class SpeakerCreateSerializer(serializers.ModelSerializer):
    """Serializer for creating speaker profiles with user creation"""
    
    # User fields for creation - REQUIRED
    email = serializers.EmailField(write_only=True)
    phone = serializers.CharField(max_length=20, write_only=True)
    first_name = serializers.CharField(max_length=150, write_only=True)
    last_name = serializers.CharField(max_length=150, write_only=True)
    avatar = serializers.ImageField(write_only=True, required=False)
    
    # Response fields for frontend compatibility
    full_name = serializers.SerializerMethodField(read_only=True)
    user_id = serializers.SerializerMethodField(read_only=True)
    
    class Meta:
        model = Speaker
        fields = [
            # User creation fields (write-only)
            'email', 'phone', 'first_name', 'last_name', 'avatar',
            
            # Speaker profile fields - matches model
            'title', 'bio', 'company',
            
            # Response fields (read-only)
            'id', 'full_name', 'user_id', 'is_verified', 'is_active',
            'total_sessions', 'created_at'
        ]
        read_only_fields = ['id', 'is_verified', 'is_active', 'total_sessions', 'created_at']
    
    def get_full_name(self, obj):
        return get_user_full_name(obj.user)
    
    def get_user_id(self, obj):
        return obj.user.id if obj.user else None
    
    def validate(self, attrs):
        """Validate user creation data"""
        email = attrs.get('email', '').strip()
        phone = attrs.get('phone', '').strip()
        first_name = attrs.get('first_name', '').strip()
        last_name = attrs.get('last_name', '').strip()
        
        errors = {}
        
        if not email:
            errors['email'] = 'Email is required'
        elif User.objects.filter(email=email).exists():
            errors['email'] = 'A user with this email already exists'
        
        if not phone:
            errors['phone'] = 'Phone number is required'
        elif User.objects.filter(phone=phone).exists():
            errors['phone'] = 'A user with this phone number already exists'
        
        if not first_name:
            errors['first_name'] = 'First name is required'
            
        if not last_name:
            errors['last_name'] = 'Last name is required'
        
        if errors:
            raise serializers.ValidationError(errors)
        
        return attrs
    
    def create(self, validated_data):
        """Create user and speaker profile"""
        # Extract user fields
        user_data = {
            'email': validated_data.pop('email'),
            'phone': validated_data.pop('phone'),
            'first_name': validated_data.pop('first_name'),
            'last_name': validated_data.pop('last_name'),
            'role': 'instructor',
            'is_active': True
        }
        
        # Handle avatar if provided
        avatar = validated_data.pop('avatar', None)
        if avatar:
            user_data['avatar'] = avatar
        
        with transaction.atomic():
            # Create user
            user = User.objects.create_user(**user_data)
            
            # Create speaker profile
            speaker = Speaker.objects.create(user=user, **validated_data)
            
            return speaker


class SpeakerUpdateSerializer(serializers.ModelSerializer):
    """Serializer for updating speaker profiles with user data"""
    
    # User fields for update
    first_name = serializers.CharField(max_length=150, required=False, write_only=True)
    last_name = serializers.CharField(max_length=150, required=False, write_only=True)
    phone = serializers.CharField(max_length=20, required=False, write_only=True)
    avatar = serializers.ImageField(required=False, write_only=True)
    
    # Response fields for frontend compatibility
    full_name = serializers.SerializerMethodField(read_only=True)
    email = serializers.SerializerMethodField(read_only=True)
    user_phone = serializers.SerializerMethodField(read_only=True)
    user_avatar = serializers.SerializerMethodField(read_only=True)
    
    class Meta:
        model = Speaker
        fields = [
            # User update fields (write-only)
            'first_name', 'last_name', 'phone', 'avatar',
            
            # Speaker profile fields - matches model
            'title', 'bio', 'company', 'is_active',
            
            # Response fields (read-only)
            'id', 'full_name', 'email', 'user_phone', 'user_avatar',
            'is_verified', 'total_sessions', 'updated_at'
        ]
        read_only_fields = ['id', 'is_verified', 'total_sessions', 'updated_at']
    
    def get_full_name(self, obj):
        return get_user_full_name(obj.user)
    
    def get_email(self, obj):
        return obj.user.email if obj.user else ''
    
    def get_user_phone(self, obj):
        return obj.user.phone if obj.user else ''
        
    def get_user_avatar(self, obj):
        """Get full URL for avatar in update response"""
        request = self.context.get('request')
        return get_avatar_full_url(request, obj.user.avatar) if obj.user else None
    
    def validate_phone(self, value):
        """Validate phone uniqueness for updates"""
        if value and self.instance:
            existing = User.objects.filter(phone=value).exclude(id=self.instance.user.id)
            if existing.exists():
                raise serializers.ValidationError('A user with this phone number already exists')
        return value
    
    def update(self, instance, validated_data):
        """Update speaker and user data"""
        # Extract user fields
        user_fields = ['first_name', 'last_name', 'phone', 'avatar']
        user_data = {k: v for k, v in validated_data.items() if k in user_fields}
        
        # Remove user fields from speaker data
        for field in user_fields:
            validated_data.pop(field, None)
        
        with transaction.atomic():
            # Update user if user data provided
            if user_data:
                user = instance.user
                for field, value in user_data.items():
                    setattr(user, field, value)
                user.save()
            
            # Update speaker
            for field, value in validated_data.items():
                setattr(instance, field, value)
            instance.save()
            
            return instance


class SpeakerListSerializer(serializers.ModelSerializer):
    """Serializer for listing speakers with essential info"""
    
    full_name = serializers.SerializerMethodField()
    avatar = serializers.SerializerMethodField()
    email = serializers.EmailField(source='user.email', read_only=True)
    
    class Meta:
        model = Speaker
        fields = [
            'id', 'full_name', 'avatar', 'email', 'title', 'bio', 'company',
            'total_sessions', 'is_verified', 'is_active', 'created_at'
        ]
        
    def get_full_name(self, obj):
        return get_user_full_name(obj.user)
    
    def get_avatar(self, obj):
        request = self.context.get('request')
        return get_avatar_full_url(request, obj.user.avatar) if obj.user else None


class SpeakerPublicSerializer(serializers.ModelSerializer):
    """Public speaker profile serializer (limited fields)"""
    
    full_name = serializers.SerializerMethodField()
    avatar = serializers.SerializerMethodField()
    email = serializers.EmailField(source='user.email', read_only=True)
    phone = serializers.CharField(source='user.phone', read_only=True)
    
    class Meta:
        model = Speaker
        fields = [
            'id', 'full_name', 'avatar', 'email', 'phone', 'title',
            'bio', 'company', 'total_sessions', 'is_verified', 'created_at'
        ]
    
    def get_full_name(self, obj):
        return get_user_full_name(obj.user)
    
    def get_avatar(self, obj):
        request = self.context.get('request')
        return get_avatar_full_url(request, obj.user.avatar) if obj.user else None
