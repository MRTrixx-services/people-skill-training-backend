from django.contrib.auth.models import BaseUserManager, AbstractBaseUser, PermissionsMixin
from django.db import models
from django.core.exceptions import ValidationError
from django.utils.translation import gettext_lazy as _
from threading import local
import logging

logger = logging.getLogger(__name__)
_thread_locals = local()

# ============================================
# USER MANAGER
# ============================================

class UserManager(BaseUserManager):
    """
    Custom user manager for email-based authentication
    """
    
    def create_user(self, email, password=None, platform=None, **extra_fields):
        """
        Create and save a regular user
        
        Args:
            email: User's email address (used for login)
            password: User's password
            platform: Platform instance (required for attendees)
            **extra_fields: Additional user fields
        """
        if not email:
            raise ValueError(_("Users must have an email address"))
        
        # Normalize email
        email = self.normalize_email(email)
        
        # Get role (default is attendee)
        role = extra_fields.get('role', 'attendee')
        
        # Validate platform requirement for attendees
        if role == 'attendee' and not platform:
            raise ValueError(_("Attendees must be associated with a platform"))
        
        # Remove username_key if accidentally passed
        extra_fields.pop('username_key', None)
        
        # Generate username_key based on role
        if role in ['admin', 'instructor']:
            username_key = f"{email}::SHARED"
            platform = None  # Ensure platform is None for shared users
        else:
            platform_id = platform.platform_id if platform else 'NONE'
            username_key = f"{email}::{platform_id}"
        
        # Set default values
        extra_fields.setdefault('is_active', True)
        extra_fields.setdefault('is_staff', False)
        extra_fields.setdefault('is_superuser', False)
        
        # Create user instance
        user = self.model(
            email=email,
            username_key=username_key,
            platform=platform,
            **extra_fields
        )
        
        # Set password (hashed)
        if password:
            user.set_password(password)
        
        # Save to database
        try:
            user.save(using=self._db)
            logger.info(f"User created: {email} ({role})")
        except Exception as e:
            logger.error(f"Error creating user {email}: {str(e)}")
            raise
        
        return user
    
    def create_superuser(self, email, password=None, **extra_fields):
        """
        Create and save a superuser
        
        ✅ This accepts 'email' as first parameter (matches USERNAME_FIELD)
        
        Args:
            email: Superuser's email address
            password: Superuser's password
            **extra_fields: Additional fields (first_name, last_name, etc.)
        """
        # Set required superuser fields
        extra_fields.setdefault('is_staff', True)
        extra_fields.setdefault('is_superuser', True)
        extra_fields.setdefault('is_active', True)
        extra_fields.setdefault('is_verified', True)
        extra_fields.setdefault('role', 'admin')
        
        # Validate superuser fields
        if extra_fields.get('is_staff') is not True:
            raise ValueError(_("Superuser must have is_staff=True"))
        if extra_fields.get('is_superuser') is not True:
            raise ValueError(_("Superuser must have is_superuser=True"))
        if not password:
            raise ValueError(_("Superuser must have a password"))
        
        # Remove username_key if passed
        extra_fields.pop('username_key', None)
        
        # Create superuser (platform is None for admins)
        logger.info(f"Creating superuser: {email}")
        return self.create_user(email, password, platform=None, **extra_fields)
    
    # def get_by_natural_key(self, username):
    #     """
    #     Retrieve user by natural key (email)
    #     Used by Django's authentication system
    #     """
    #     return self.get(**{self.model.USERNAME_FIELD: username})

    def get_by_natural_key(self, username):
        """
        Platform-aware user lookup for authentication
        
        Business Logic:
        1. If only one user with email exists → return it
        2. If multiple users exist:
        a. Check for admin/instructor (global users) → return first
        b. Check for attendee on current platform → return it
        c. Fallback → raise DoesNotExist
        
        Args:
            username: Email address (USERNAME_FIELD)
        
        Returns:
            User instance
        
        Raises:
            User.DoesNotExist: If no valid user found
        """
        # from threading import local
        # _thread_locals = local()
        
        # Get current platform from thread-local (set by login serializer)
        current_platform = getattr(_thread_locals, 'platform', None)
        
        # Query all users with this email
        users = self.filter(**{self.model.USERNAME_FIELD: username})
        user_count = users.count()
        
        logger.info(
            f"🔍 Auth lookup: {username} | "
            f"Found: {user_count} user(s) | "
            f"Platform: {current_platform.name if current_platform else 'None'}"
        )
        
        # Case 1: No users found
        if user_count == 0:
            logger.warning(f"❌ No user found: {username}")
            raise self.model.DoesNotExist(
                f"{self.model._meta.object_name} matching query does not exist."
            )
        
        # Case 2: Only one user found (common case)
        if user_count == 1:
            user = users.first()
            logger.info(f"✅ Single user: {user.email} (Role: {user.role})")
            return user
        
        # Case 3: Multiple users found - apply platform logic
        logger.info(f"⚠️  Multiple users ({user_count}) found for {username}")
        
        # Priority 1: Admin/Instructor (global users - no platform)
        admin_or_instructor = users.filter(
            role__in=['admin', 'instructor']
        ).first()
        
        if admin_or_instructor:
            logger.info(
                f"✅ Returning global {admin_or_instructor.role}: "
                f"{admin_or_instructor.email}"
            )
            return admin_or_instructor
        
        # Priority 2: Attendee on current platform
        if current_platform:
            attendee = users.filter(
                role='attendee', 
                platform=current_platform
            ).first()
            
            if attendee:
                logger.info(
                    f"✅ Returning platform-specific attendee: "
                    f"{attendee.email} on {current_platform.name}"
                )
                return attendee
            else:
                logger.warning(
                    f"❌ No attendee found for {username} on platform: "
                    f"{current_platform.name}"
                )
                raise self.model.DoesNotExist(
                    f"No account found on {current_platform.name}. "
                    f"Please register or check your platform."
                )
        
        # Priority 3: No platform context - can't determine correct user
        logger.error(
            f"❌ Multiple attendees found for {username} but no platform context"
        )
        raise self.model.DoesNotExist(
            f"Multiple accounts found. Please specify platform."
        )

# ============================================
# USER MODEL
# ============================================

class User(AbstractBaseUser, PermissionsMixin):
    """
    Multi-platform custom user model with email-based authentication
    
    Business Rules:
    - Admins/Instructors: Shared across platforms (platform=NULL)
    - Attendees: Platform-specific (platform=FK)
    - Email is unique per platform for attendees
    - Email is globally unique for admins/instructors
    - username_key is auto-generated for internal use
    """
    
    ROLE_CHOICES = [
        ('admin', 'Admin'),
        ('instructor', 'Instructor'),
        ('attendee', 'Attendee'),
    ]
    
    # ============================================
    # AUTHENTICATION FIELDS
    # ============================================
    
    # ✅ username_key: Auto-generated composite key for internal use
    username_key = models.CharField(
        max_length=255,
        unique=True,
        db_index=True,
        editable=False,  # Not editable by users
        help_text=_("Composite key: email::platform_id (auto-generated)")
    )
    
    # ✅ email: Primary login identifier
    email = models.EmailField(
        _('email address'),
        max_length=255,
        db_index=True,
        help_text=_("Email address (used for login)")
    )
    
    # ============================================
    # PERSONAL INFORMATION
    # ============================================
    
    first_name = models.CharField(
        _('first name'),
        max_length=150,
        blank=True
    )
    
    last_name = models.CharField(
        _('last name'),
        max_length=150,
        blank=True
    )
    
    avatar = models.ImageField(
        upload_to='avatars/%Y/%m/',
        null=True,
        blank=True,
        help_text=_("User profile picture")
    )
    
    phone = models.CharField(
        _('phone number'),
        max_length=20,
        blank=True
    )
    
    # ============================================
    # ROLE & PLATFORM
    # ============================================
    company = models.CharField(
        _('company name'),
        max_length=255,
        blank=True,
        help_text=_("Company or organization name")
    )
    
    role = models.CharField(
        max_length=20,
        choices=ROLE_CHOICES,
        default='attendee',
        db_index=True,
        help_text=_("User role in the system")
    )
    
    platform = models.ForeignKey(
        'platforms.Platform',
        on_delete=models.CASCADE,
        related_name='users',
        null=True,
        blank=True,
        db_index=True,
        help_text=_("Platform for attendees only. NULL for admins/instructors")
    )
    
    # ============================================
    # PERMISSIONS & STATUS
    # ============================================
    
    is_active = models.BooleanField(
        _('active'),
        default=True,
        help_text=_('Designates whether this user should be treated as active.')
    )
    
    is_staff = models.BooleanField(
        _('staff status'),
        default=False,
        help_text=_('Designates whether the user can log into admin site.')
    )
    
    is_verified = models.BooleanField(
        _('verified'),
        default=False,
        help_text=_('Designates whether email has been verified.')
    )
    
    email_verified_at = models.DateTimeField(
        _('email verified at'),
        null=True,
        blank=True
    )
    
    # ============================================
    # TIMESTAMPS
    # ============================================
    
    created_at = models.DateTimeField(
        _('date joined'),
        auto_now_add=True
    )
    
    updated_at = models.DateTimeField(
        _('last updated'),
        auto_now=True
    )
    
    # ============================================
    # MANAGER & AUTHENTICATION CONFIG
    # ============================================
    
    objects = UserManager()
    
    # ✅ FIX: Use 'email' as USERNAME_FIELD (for createsuperuser command)
    USERNAME_FIELD = 'email'
    EMAIL_FIELD = 'email'
    
    # ✅ FIX: REQUIRED_FIELDS should NOT include USERNAME_FIELD or password
    REQUIRED_FIELDS = ['first_name', 'last_name']
    
    # ============================================
    # META OPTIONS
    # ============================================
    
    class Meta:
        db_table = 'users'
        verbose_name = _('User')
        verbose_name_plural = _('Users')
        
        # Unique constraints
        constraints = [
            # Email unique for admins/instructors
            models.UniqueConstraint(
                fields=['email'],
                condition=models.Q(role__in=['admin', 'instructor']),
                name='unique_email_for_shared_users'
            ),
            # Email unique per platform for attendees
            models.UniqueConstraint(
                fields=['email', 'platform'],
                condition=models.Q(role='attendee'),
                name='unique_email_per_platform_for_attendees'
            ),
        ]
        
        # Database indexes
        indexes = [
            models.Index(fields=['email'], name='idx_user_email'),
            models.Index(fields=['username_key'], name='idx_username_key'),
            models.Index(fields=['platform', 'role'], name='idx_platform_role'),
            models.Index(fields=['role', 'is_active'], name='idx_role_active'),
            models.Index(fields=['is_active', 'is_verified'], name='idx_active_verified'),
            models.Index(fields=['created_at'], name='idx_created_at'),
        ]
        
        ordering = ['-created_at']
    
    # ============================================
    # STRING REPRESENTATION
    # ============================================
    
    def __str__(self):
        if self.platform:
            return f"{self.full_name} ({self.email}) - {self.platform.name}"
        return f"{self.full_name} ({self.email}) - Shared User"
    
    def __repr__(self):
        return f"<User {self.id}: {self.email} ({self.role})>"
    
    # ============================================
    # SAVE METHOD WITH VALIDATION
    # ============================================
    
    def save(self, *args, **kwargs):
        """Custom save with business rule enforcement"""
        
        # Enforce business rules
        if self.role in ['admin', 'instructor']:
            self.platform = None
        elif self.role == 'attendee' and not self.platform:
            raise ValidationError(_("Attendees must be associated with a platform"))
        
        # Auto-generate username_key if not set
        if not self.username_key:
            if self.role in ['admin', 'instructor']:
                self.username_key = f"{self.email}::SHARED"
            else:
                platform_id = self.platform.platform_id if self.platform else 'NONE'
                self.username_key = f"{self.email}::{platform_id}"
        
        super().save(*args, **kwargs)
    
    def clean(self):
        """Model validation"""
        super().clean()
        
        if not self.email:
            raise ValidationError({'email': _("Email is required")})
        
        if self.role == 'attendee' and not self.platform:
            raise ValidationError({
                'platform': _("Attendees must be assigned to a platform")
            })
        
        if self.role in ['admin', 'instructor'] and self.platform:
            raise ValidationError({
                'platform': _("Admins and instructors cannot be assigned to a platform")
            })
    
    # ============================================
    # PROPERTIES
    # ============================================
    
    @property
    def full_name(self):
        """Return full name or email if name not set"""
        full_name = f"{self.first_name} {self.last_name}".strip()
        return full_name if full_name else self.email
    
    @property
    def short_name(self):
        """Return short name"""
        return self.first_name or self.email.split('@')[0]
    
    @property
    def initials(self):
        """Get user initials"""
        if self.first_name and self.last_name:
            return f"{self.first_name[0]}{self.last_name[0]}".upper()
        elif self.first_name:
            return self.first_name[0].upper()
        return self.email[0].upper()
    
    # ============================================
    # REQUIRED METHODS FOR DJANGO ADMIN
    # ============================================
    
    def get_full_name(self):
        """Required by Django admin"""
        full_name = f'{self.first_name} {self.last_name}'.strip()
        return full_name if full_name else self.email
    
    def get_short_name(self):
        """Required by Django admin"""
        return self.first_name or self.email
    
    def get_avatar_url(self, request=None):
        """Get absolute URL for avatar"""
        if self.avatar and hasattr(self.avatar, 'url'):
            if request:
                return request.build_absolute_uri(self.avatar.url)
            return self.avatar.url
        return None
    
    # ============================================
    # ROLE CHECK METHODS
    # ============================================
    
    def is_admin(self):
        return self.role == 'admin'
    
    def is_instructor(self):
        return self.role == 'instructor'
    
    def is_attendee(self):
        return self.role == 'attendee'
    
    def is_shared_user(self):
        return self.role in ['admin', 'instructor']
    
    # ============================================
    # PLATFORM METHODS
    # ============================================
    
    def get_platforms(self):
        """Get list of platforms accessible by user"""
        if self.is_shared_user():
            from apps.platforms.models import Platform
            return Platform.objects.filter(is_active=True)
        elif self.platform:
            return [self.platform]
        return []
    
    def can_access_platform(self, platform):
        """Check if user can access a specific platform"""
        if self.is_shared_user():
            return platform.is_active
        return self.platform == platform
    
    # ============================================
    # UTILITY METHODS
    # ============================================
    
    def mark_email_verified(self):
        """Mark user's email as verified"""
        from django.utils import timezone
        self.is_verified = True
        self.email_verified_at = timezone.now()
        self.save(update_fields=['is_verified', 'email_verified_at'])
        logger.info(f"Email verified for user: {self.email}")


# ============================================
# USER PROFILE MODEL
# ============================================

class UserProfile(models.Model):
    """Extended user profile for additional information"""
    
    user = models.OneToOneField(
        User,
        on_delete=models.CASCADE,
        related_name='profile',
        primary_key=True
    )
    
    bio = models.TextField(
        _('biography'),
        blank=True,
        max_length=500
    )
    
    location = models.CharField(
        _('location'),
        max_length=100,
        blank=True
    )
    
    timezone = models.CharField(
        _('timezone'),
        max_length=50,
        default='UTC'
    )
    
    # Social links
    website = models.URLField(_('website'), blank=True, max_length=200)
    linkedin = models.URLField(_('LinkedIn'), blank=True, max_length=200)
    twitter = models.URLField(_('Twitter'), blank=True, max_length=200)
    github = models.URLField(_('GitHub'), blank=True, max_length=200)
    
    # Privacy settings
    show_email_publicly = models.BooleanField(_('show email publicly'), default=False)
    show_phone_publicly = models.BooleanField(_('show phone publicly'), default=False)
    allow_direct_messages = models.BooleanField(_('allow direct messages'), default=True)
    
    # JSON fields
    preferences = models.JSONField(_('preferences'), default=dict, blank=True)
    notification_settings = models.JSONField(_('notification settings'), default=dict, blank=True)
    
    # Timestamps
    created_at = models.DateTimeField(_('created at'), auto_now_add=True)
    updated_at = models.DateTimeField(_('updated at'), auto_now=True)
    
    class Meta:
        db_table = 'user_profiles'
        verbose_name = _('User Profile')
        verbose_name_plural = _('User Profiles')
        ordering = ['-created_at']
    
    def __str__(self):
        return f"{self.user.full_name}'s Profile"


# ============================================
# SIGNALS
# ============================================

from django.db.models.signals import post_save, pre_save
from django.dispatch import receiver


@receiver(post_save, sender=User)
def create_user_profile(sender, instance, created, **kwargs):
    """Auto-create UserProfile when User is created"""
    if created:
        try:
            UserProfile.objects.create(user=instance)
            logger.info(f"Profile created for user: {instance.email}")
        except Exception as e:
            logger.error(f"Error creating profile for {instance.email}: {str(e)}")


@receiver(post_save, sender=User)
def save_user_profile(sender, instance, **kwargs):
    """Save UserProfile when User is saved"""
    if hasattr(instance, 'profile'):
        try:
            instance.profile.save()
        except Exception as e:
            logger.error(f"Error saving profile for {instance.email}: {str(e)}")


@receiver(pre_save, sender=User)
def log_user_changes(sender, instance, **kwargs):
    """Log significant user changes"""
    if instance.pk:
        try:
            old_instance = User.objects.get(pk=instance.pk)
            
            if old_instance.role != instance.role:
                logger.warning(
                    f"User role changed: {instance.email} "
                    f"from {old_instance.role} to {instance.role}"
                )
            
            if old_instance.is_active != instance.is_active:
                status = "activated" if instance.is_active else "deactivated"
                logger.info(f"User {status}: {instance.email}")
                
        except User.DoesNotExist:
            pass
