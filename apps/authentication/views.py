from rest_framework import status, generics, permissions
from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response
from rest_framework_simplejwt.views import TokenObtainPairView
from rest_framework_simplejwt.tokens import RefreshToken
from django.core.mail import send_mail
from django.conf import settings
from django.utils import timezone
import logging

from apps.users.models import User
from apps.notifications.email_service import (
    send_verification_email_task,
    send_verification_success_email_task,
    EmailService
)
from .models import EmailVerificationToken, PasswordResetToken
from .serializers import (
    CustomTokenObtainPairSerializer,
    UserRegistrationSerializer,
    PasswordChangeSerializer,
    PasswordResetRequestSerializer,
    PasswordResetConfirmSerializer,
    UserProfileSerializer,
    EmailVerificationSerializer
)

logger = logging.getLogger(__name__)


class CustomTokenObtainPairView(TokenObtainPairView):
    """Custom JWT token obtain view with platform info"""
    serializer_class = CustomTokenObtainPairSerializer


# class UserRegistrationView(generics.CreateAPIView):
#     """User registration view with platform-specific email"""
#     queryset = User.objects.all()
#     serializer_class = UserRegistrationSerializer
#     permission_classes = [permissions.AllowAny]
    
#     def create(self, request, *args, **kwargs):
#         serializer = self.get_serializer(data=request.data, context={'request': request})
#         serializer.is_valid(raise_exception=True)
#         user = serializer.save()
        
#         # Create verification token
#         verification_token = EmailVerificationToken.objects.create(user=user)
#         logger.info(f"✅ User created: {user.email} (ID: {user.id})")
#         logger.info(f"🔑 Token created: {verification_token.token}")
        
#         # ✅ Send verification email with error handling
#         try:
#             task = send_verification_email_task.delay(user.id, verification_token.token)
#             logger.info(f"📧 Email task queued: {task.id} for {user.email}")
#         except Exception as e:
#             logger.error(f"❌ Celery task failed: {str(e)}", exc_info=True)
#             # Fallback to synchronous email
#             try:
#                 EmailService.send_verification_email(
#                     user, 
#                     verification_token.token, 
#                     platform=user.platform
#                 )
#                 logger.info(f"📧 Email sent synchronously to {user.email}")
#             except Exception as email_error:
#                 logger.error(f"❌ Email failed completely: {str(email_error)}", exc_info=True)
        
#         # Generate tokens
#         refresh = RefreshToken.for_user(user)
        
#         # Platform info
#         platform_info = None
#         platform_name = 'PeopleSkillTraining'
        
#         if user.platform:
#             platform_name = user.platform.name
#             platform_info = {
#                 'id': user.platform.id,
#                 'platform_id': user.platform.platform_id,
#                 'name': user.platform.name,
#                 'logo_url': user.platform.logo_url,
#             }
        
#         return Response({
#             'success': True,
#             'message': f'Account created successfully! Please check your email to verify your account.',
#             'platform_message': f'Welcome to {platform_name}! A verification email has been sent to {user.email}',
#             'user': {
#                 'id': user.id,
#                 'email': user.email,
#                 'first_name': user.first_name,
#                 'last_name': user.last_name,
#                 'role': user.role,
#                 'is_verified': user.is_verified,
#                 'platform': platform_info,
#             },
#             'tokens': {
#                 'refresh': str(refresh),
#                 'access': str(refresh.access_token),
#             }
#         }, status=status.HTTP_201_CREATED)
class UserRegistrationView(generics.CreateAPIView):
    """User registration view with platform-specific email verification"""
    queryset = User.objects.all()
    serializer_class = UserRegistrationSerializer
    permission_classes = [permissions.AllowAny]
    
    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data, context={'request': request})
        serializer.is_valid(raise_exception=True)
        user = serializer.save()
        
        platform = user.platform
        requires_verification = platform.requires_email_verification if platform else True
        
        if requires_verification:
            # ✅ Platform requires email verification - send verification email
            verification_token = EmailVerificationToken.objects.create(user=user)
            logger.info(f"✅ User created: {user.email} (ID: {user.id}) - Verification REQUIRED")
            logger.info(f"🔑 Token created: {verification_token.token}")
            
            try:
                task = send_verification_email_task.delay(user.id, verification_token.token)
                logger.info(f"📧 Verification email task queued: {task.id} for {user.email}")
            except Exception as e:
                logger.error(f"❌ Celery task failed: {str(e)}", exc_info=True)
                try:
                    EmailService.send_verification_email(
                        user, 
                        verification_token.token, 
                        platform=user.platform
                    )
                    logger.info(f"📧 Verification email sent synchronously to {user.email}")
                except Exception as email_error:
                    logger.error(f"❌ Email failed completely: {str(email_error)}", exc_info=True)
            
            email_message = f'Please check your email to verify your account.'
        else:
            # ✅ Platform does NOT require verification - auto-verify user
            user.is_verified = True
            user.email_verified_at = timezone.now()
            user.save()
            logger.info(f"✅ User created and AUTO-VERIFIED: {user.email} (Platform: {platform.name})")
            
            # Send welcome email instead of verification email
            try:
                task = send_verification_success_email_task.delay(user.id)
                logger.info(f"📧 Welcome email task queued: {task.id} for {user.email}")
            except Exception as e:
                logger.error(f"❌ Celery task failed for welcome email: {str(e)}", exc_info=True)
                try:
                    EmailService.send_verification_success_email(user, platform=user.platform)
                    logger.info(f"📧 Welcome email sent synchronously to {user.email}")
                except Exception as email_error:
                    logger.error(f"❌ Welcome email failed: {str(email_error)}", exc_info=True)
            
            # Create role-specific profile immediately
            if user.role == 'instructor':
                try:
                    from apps.speakers.models import Speaker
                    Speaker.objects.get_or_create(
                        user=user,
                        defaults={'user': user, 'title': ''}
                    )
                    logger.info(f"✅ Speaker profile created for {user.email}")
                except ImportError:
                    pass
            elif user.role == 'attendee':
                try:
                    from apps.attendees.models import AttendeeProfile
                    AttendeeProfile.objects.get_or_create(
                        user=user,
                        defaults={
                            'user': user,
                            'platform': user.platform,
                            'skill_level': 'beginner',
                            'language': 'en',
                            'timezone': 'America/New_York'
                        }
                    )
                    logger.info(f"✅ Attendee profile created for {user.email}")
                except ImportError:
                    pass
            
            email_message = f'Welcome! Your account is ready to use.'
        
        # Generate tokens
        refresh = RefreshToken.for_user(user)
        
        # Platform info
        platform_info = None
        platform_name = 'PeopleSkillTraining'
        
        if user.platform:
            platform_name = user.platform.name
            platform_info = {
                'id': user.platform.id,
                'platform_id': user.platform.platform_id,
                'name': user.platform.name,
                'logo_url': user.platform.logo_url,
            }
        
        return Response({
            'success': True,
            'message': f'Account created successfully! {email_message}',
            'platform_message': f'Welcome to {platform_name}! {email_message}',
            'requires_verification': requires_verification,
            'user': {
                'id': user.id,
                'email': user.email,
                'first_name': user.first_name,
                'last_name': user.last_name,
                'role': user.role,
                'is_verified': user.is_verified,
                'platform': platform_info,
            },
            'tokens': {
                'refresh': str(refresh),
                'access': str(refresh.access_token),
            }
        }, status=status.HTTP_201_CREATED)


@api_view(['POST'])
@permission_classes([permissions.AllowAny])
def verify_email(request):
    """Email verification with platform-specific behavior"""
    serializer = EmailVerificationSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)
    
    token = serializer.validated_data['token']
    email = serializer.validated_data['email']
    
    try:
        verification_token = EmailVerificationToken.objects.get(
            token=token,
            user__email=email,
            is_used=False
        )
        
        if verification_token.is_expired():
            logger.warning(f"⚠️  Expired token used for: {email}")
            return Response({
                'success': False,
                'error': 'Verification token has expired. Please request a new one.'
            }, status=status.HTTP_400_BAD_REQUEST)
        
        user = verification_token.user
        
        # Check if user was already auto-verified (shouldn't happen, but defensive)
        if user.is_verified:
            logger.info(f"⚠️  User {user.email} already verified")
            return Response({
                'success': True,
                'message': 'Email already verified.',
                'user': {
                    'id': user.id,
                    'email': user.email,
                    'is_verified': True,
                }
            }, status=status.HTTP_200_OK)
        
        # Mark user as verified
        user.is_verified = True
        user.email_verified_at = timezone.now()
        user.save()
        
        verification_token.mark_as_used()
        logger.info(f"✅ Email verified: {user.email}")
        
        # Send success email
        try:
            task = send_verification_success_email_task.delay(user.id)
            logger.info(f"📧 Success email task queued: {task.id} for {user.email}")
        except Exception as e:
            logger.error(f"❌ Celery task failed for success email: {str(e)}", exc_info=True)
            try:
                EmailService.send_verification_success_email(user, platform=user.platform)
                logger.info(f"📧 Success email sent synchronously to {user.email}")
            except Exception as email_error:
                logger.error(f"❌ Success email failed: {str(email_error)}", exc_info=True)
        
        # Create role-specific profile
        profile_created = None
        profile_type = None
        
        if user.role == 'instructor':
            try:
                from apps.speakers.models import Speaker
                speaker_profile, created = Speaker.objects.get_or_create(
                    user=user,
                    defaults={'user': user, 'title': ''}
                )
                if created:
                    profile_created = 'speaker'
                    profile_type = 'Speaker Profile'
                    logger.info(f"✅ Speaker profile created for {user.email}")
            except ImportError:
                pass
                
        elif user.role == 'attendee':
            try:
                from apps.attendees.models import AttendeeProfile
                attendee_profile, created = AttendeeProfile.objects.get_or_create(
                    user=user,
                    defaults={
                        'user': user,
                        'platform': user.platform,
                        'skill_level': 'beginner',
                        'language': 'en',
                        'timezone': 'America/New_York'
                    }
                )
                if created:
                    profile_created = 'attendee'
                    profile_type = 'Attendee Profile'
                    logger.info(f"✅ Attendee profile created for {user.email}")
            except ImportError:
                pass
        
        platform_name = user.platform.name if user.platform else 'PeopleSkillTraining'
        platform_info = None
        if user.platform:
            platform_info = {
                'id': user.platform.id,
                'platform_id': user.platform.platform_id,
                'name': user.platform.name,
            }
        
        response_data = {
            'success': True,
            'message': 'Email verified successfully!',
            'platform_message': f'Welcome to {platform_name}! Your account is now active.',
            'user': {
                'id': user.id,
                'email': user.email,
                'first_name': user.first_name,
                'last_name': user.last_name,
                'role': user.role,
                'is_verified': user.is_verified,
                'platform': platform_info,
            }
        }
        
        if profile_created:
            response_data['profile_created'] = {
                'type': profile_created,
                'name': profile_type,
                'message': f'{profile_type} created automatically'
            }
        
        return Response(response_data, status=status.HTTP_200_OK)
        
    except EmailVerificationToken.DoesNotExist:
        logger.warning(f"⚠️  Invalid token attempted for: {email}")
        return Response({
            'success': False,
            'error': 'Invalid verification token.'
        }, status=status.HTTP_400_BAD_REQUEST)


@api_view(['POST'])
@permission_classes([permissions.IsAuthenticated])
def resend_verification_email(request):
    """Resend email verification with platform context"""
    user = request.user
    
    if user.is_verified:
        logger.info(f"⚠️  Resend attempt for already verified user: {user.email}")
        return Response({
            'success': False,
            'message': 'Email is already verified.'
        }, status=status.HTTP_400_BAD_REQUEST)
    
    # Mark old tokens as used
    EmailVerificationToken.objects.filter(user=user, is_used=False).update(is_used=True)
    
    # Create new token
    verification_token = EmailVerificationToken.objects.create(user=user)
    logger.info(f"🔄 New verification token created for: {user.email}")
    
    # ✅ Send with error handling
    try:
        task = send_verification_email_task.delay(user.id, verification_token.token)
        logger.info(f"📧 Resend email task queued: {task.id} for {user.email}")
    except Exception as e:
        logger.error(f"❌ Celery task failed for resend: {str(e)}", exc_info=True)
        try:
            EmailService.send_verification_email(user, verification_token.token, platform=user.platform)
            logger.info(f"📧 Resend email sent synchronously to {user.email}")
        except Exception as email_error:
            logger.error(f"❌ Resend email failed: {str(email_error)}", exc_info=True)
    
    platform_name = user.platform.name if user.platform else 'PeopleSkillTraining'
    
    return Response({
        'success': True,
        'message': f'Verification email sent successfully from {platform_name}.'
    }, status=status.HTTP_200_OK)


@api_view(['POST'])
@permission_classes([permissions.AllowAny])
def check_verification_status(request):
    """Check email verification status"""
    email = request.data.get('email')
    
    if not email:
        return Response({
            'success': False,
            'error': 'Email is required.'
        }, status=status.HTTP_400_BAD_REQUEST)
    
    try:
        user = User.objects.get(email=email)
        
        has_profile = False
        profile_type = None
        
        if user.role == 'instructor':
            try:
                from apps.speakers.models import Speaker
                has_profile = Speaker.objects.filter(user=user).exists()
                profile_type = 'speaker' if has_profile else None
            except ImportError:
                pass
        elif user.role == 'attendee':
            try:
                from apps.attendees.models import AttendeeProfile
                has_profile = AttendeeProfile.objects.filter(user=user).exists()
                profile_type = 'attendee' if has_profile else None
            except ImportError:
                pass
        
        return Response({
            'success': True,
            'is_verified': user.is_verified,
            'email': user.email,
            'role': user.role,
            'has_profile': has_profile,
            'profile_type': profile_type
        }, status=status.HTTP_200_OK)
    except User.DoesNotExist:
        return Response({
            'success': False,
            'error': 'User not found.'
        }, status=status.HTTP_404_NOT_FOUND)


class UserProfileView(generics.RetrieveUpdateAPIView):
    """User profile view"""
    serializer_class = UserProfileSerializer
    permission_classes = [permissions.IsAuthenticated]
    
    def get_object(self):
        return self.request.user


# class PasswordChangeView(generics.UpdateAPIView):
#     """Password change view"""
#     serializer_class = PasswordChangeSerializer
#     permission_classes = [permissions.IsAuthenticated]
    
#     def get_object(self):
#         return self.request.user
    
#     def update(self, request, *args, **kwargs):
#         serializer = self.get_serializer(data=request.data)
#         serializer.is_valid(raise_exception=True)
        
#         user = self.get_object()
#         user.set_password(serializer.validated_data['new_password'])
#         user.save()
        
#         logger.info(f"🔐 Password changed for: {user.email}")
        
#         return Response({
#             'success': True,
#             'message': 'Password changed successfully'
#         }, status=status.HTTP_200_OK)
# class PasswordChangeView(generics.UpdateAPIView):
#     """Password change view for authenticated users"""
#     serializer_class = PasswordChangeSerializer
#     permission_classes = [permissions.IsAuthenticated]
    
#     def get_object(self):
#         return self.request.user
    
#     def update(self, request, *args, **kwargs):
#         serializer = self.get_serializer(data=request.data)
#         serializer.is_valid(raise_exception=True)
        
#         user = self.get_object()
#         user.set_password(serializer.validated_data['new_password'])
#         user.save()
        
#         logger.info(f"🔐 Password changed for: {user.email}")
        
#         # ✅ Send password change confirmation email (optional)
#         try:
#             from apps.notifications.email_service import EmailService
#             EmailService.send_password_change_notification(
#                 user=user,
#                 platform=user.platform
#             )
#             logger.info(f"📧 Password change notification sent to: {user.email}")
#         except Exception as e:
#             logger.error(f"❌ Failed to send password change notification: {str(e)}")
#             # Don't fail the request if email fails
        
#         return Response({
#             'success': True,
#             'message': 'Password changed successfully'
#         }, status=status.HTTP_200_OK)


class PasswordChangeView(generics.UpdateAPIView):
    """Password change view for authenticated users"""
    serializer_class = PasswordChangeSerializer
    permission_classes = [permissions.IsAuthenticated]
    
    def get_object(self):
        return self.request.user
    
    def update(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        
        user = self.get_object()
        user.set_password(serializer.validated_data['new_password'])
        user.save()
        
        logger.info(f"🔐 Password changed for: {user.email}")
        
        # ✅ Send password change confirmation email
        try:
            from apps.notifications.email_service import EmailService
            
            # ✅ Get platform from request or user
            platform = getattr(request, 'platform', None) or user.platform
            
            EmailService.send_password_change_notification(
                user=user,
                request=request,
                platform=platform  # ✅ PASS PLATFORM HERE
            )
            logger.info(f"📧 Password change notification sent to: {user.email}")
        except Exception as e:
            logger.error(f"❌ Failed to send password change notification: {str(e)}")
            # Don't fail the request if email fails
        
        return Response({
            'success': True,
            'message': 'Password changed successfully'
        }, status=status.HTTP_200_OK)


class PasswordResetRequestView(generics.CreateAPIView):
    """Password reset request with platform support"""
    serializer_class = PasswordResetRequestSerializer
    permission_classes = [permissions.AllowAny]
    
    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        
        email = serializer.validated_data['email']
        
        # ✅ Get platform from request (set by middleware)
        platform = getattr(request, 'platform', None)
        
        # ✅ FIXED: Filter by both email AND platform to handle duplicates
        try:
            if platform:
                # Platform-specific user lookup
                user = User.objects.get(email=email, platform=platform)
                logger.info(f"🔍 Password reset requested for {email} on platform: {platform.name}")
            else:
                # Fallback: Get the most recent user if no platform
                user = User.objects.filter(email=email).order_by('-date_joined').first()
                if not user:
                    raise User.DoesNotExist
                logger.warning(f"🔍 Password reset requested for {email} without platform context")
        except User.DoesNotExist:
            # ✅ Still return success to prevent email enumeration
            logger.warning(f"⚠️ Password reset attempted for non-existent email: {email}")
            return Response({
                'success': True,
                'message': 'Password reset email sent successfully'
            }, status=status.HTTP_200_OK)
        except User.MultipleObjectsReturned:
            # ✅ Handle duplicate users gracefully
            logger.error(f"❌ Multiple users found for {email} - platform: {platform}")
            return Response({
                'success': False,
                'error': 'Multiple accounts found. Please contact support.',
                'message': 'There are multiple accounts with this email. Please contact support for assistance.'
            }, status=status.HTTP_400_BAD_REQUEST)
        
        # Create reset token
        reset_token = PasswordResetToken.objects.create(user=user)
        logger.info(f"🔑 Password reset token created for: {email}")
        
        # ✅ Send email with platform context
        try:
            from apps.notifications.email_service import send_password_reset_email_task
            task = send_password_reset_email_task.delay(user.id, reset_token.token)
            logger.info(f"📧 Password reset email task queued: {task.id} for {email}")
        except Exception as e:
            logger.error(f"❌ Celery task failed for password reset: {str(e)}", exc_info=True)
            # Fallback to synchronous email
            try:
                from apps.notifications.email_service import EmailService
                EmailService.send_password_reset_email(
                    user=user,
                    reset_token=reset_token.token,
                    request=request,
                    platform=platform
                )
                logger.info(f"📧 Password reset email sent synchronously to {email}")
            except Exception as email_error:
                logger.error(f"❌ Password reset email failed: {str(email_error)}", exc_info=True)
        
        return Response({
            'success': True,
            'message': 'Password reset email sent successfully'
        }, status=status.HTTP_200_OK)

# class PasswordResetConfirmView(generics.CreateAPIView):
#     """Password reset confirmation with platform support"""
#     serializer_class = PasswordResetConfirmSerializer
#     permission_classes = [permissions.AllowAny]
    
#     def create(self, request, *args, **kwargs):
#         # ✅ Debug: Log incoming data
#         logger.info(f"🔍 Password reset confirm request data: {request.data}")
        
#         serializer = self.get_serializer(data=request.data)
        
#         # ✅ Log validation errors
#         if not serializer.is_valid():
#             logger.error(f"❌ Serializer validation errors: {serializer.errors}")
#             return Response({
#                 'success': False,
#                 'error': 'Validation failed',
#                 'details': serializer.errors
#             }, status=status.HTTP_400_BAD_REQUEST)
        
#         try:
#             token = serializer.validated_data['token']
#             email = serializer.validated_data['email']
#             new_password = serializer.validated_data['new_password']
            
#             # ✅ Get platform from request
#             platform = getattr(request, 'platform', None)
#             logger.info(f"🔍 Platform context: {platform.name if platform else 'None'}")
            
#             # ✅ FIXED: Filter by email, platform, and token
#             reset_token_query = PasswordResetToken.objects.filter(
#                 token=token,
#                 user__email=email,
#                 is_used=False
#             )
            
#             # Add platform filter if available
#             if platform:
#                 reset_token_query = reset_token_query.filter(user__platform=platform)
            
#             reset_token = reset_token_query.first()
            
#             if not reset_token:
#                 logger.warning(f"⚠️ Invalid reset token attempted for: {email}")
#                 return Response({
#                     'success': False,
#                     'error': 'Invalid reset token'
#                 }, status=status.HTTP_400_BAD_REQUEST)
            
#             if reset_token.is_expired():
#                 logger.warning(f"⚠️ Expired reset token used for: {email}")
#                 return Response({
#                     'success': False,
#                     'error': 'Reset token has expired. Please request a new one.'
#                 }, status=status.HTTP_400_BAD_REQUEST)
            
#             user = reset_token.user
#             user.set_password(new_password)
#             user.save()
            
#             reset_token.mark_as_used()
#             logger.info(f"✅ Password reset successfully for: {email}")
            
#             # ✅ Send password change notification
#          # In PasswordResetConfirmView, before sending email:
#             try:
#                 from apps.notifications.email_service import EmailService
#                 from django.template.loader import render_to_string
                
#                 # Build context manually to test
#                 context = EmailService.get_email_context(
#                     user=user,
#                     request=request,
#                     platform=platform,
#                     login_url=f"{EmailService.get_base_url(request, platform)}/login",
#                     support_url=f"{EmailService.get_base_url(request, platform)}/contact-support",
#                     subject="Password Changed Successfully"
#                 )
                
#                 # Try to render and log
#                 html_content = render_to_string('emails/password_changed_notification.html', context)
#                 logger.info(f"📧 Template rendered successfully, length: {len(html_content)}")
                
#                 # Now send
#                 EmailService.send_password_change_notification(
#                     user=user,
#                     request=request,
#                     platform=platform
#                 )
#                 logger.info(f"✅ Password change notification sent to {email}")
#             except Exception as e:
#                 logger.error(f"❌ Failed to send password change notification: {str(e)}", exc_info=True)

#             return Response({
#                 'success': True,
#                 'message': 'Password reset successfully'
#             }, status=status.HTTP_200_OK)
            
#         except Exception as e:
#             logger.error(f"❌ Password reset confirmation failed: {str(e)}", exc_info=True)
#             return Response({
#                 'success': False,
#                 'error': 'Password reset failed. Please try again.'
#             }, status=status.HTTP_400_BAD_REQUEST)

# class PasswordResetConfirmView(generics.CreateAPIView):
#     """Password reset confirmation with platform support"""
#     serializer_class = PasswordResetConfirmSerializer
#     permission_classes = [permissions.AllowAny]
    
#     def create(self, request, *args, **kwargs):
#         # ✅ Debug: Log incoming data
#         logger.info(f"🔍 Password reset confirm request data: {request.data}")
        
#         serializer = self.get_serializer(data=request.data)
        
#         # ✅ Log validation errors
#         if not serializer.is_valid():
#             logger.error(f"❌ Serializer validation errors: {serializer.errors}")
#             return Response({
#                 'success': False,
#                 'error': 'Validation failed',
#                 'details': serializer.errors
#             }, status=status.HTTP_400_BAD_REQUEST)
        
#         try:
#             token = serializer.validated_data['token']
#             email = serializer.validated_data['email']
#             new_password = serializer.validated_data['new_password']
            
#             # ✅ Get platform from request (set by middleware)
#             platform = getattr(request, 'platform', None)
#             logger.info(f"🔍 Platform context: {platform.name if platform else 'None'}")
            
#             # ✅ FIXED: Filter by email, platform, and token
#             reset_token_query = PasswordResetToken.objects.filter(
#                 token=token,
#                 user__email=email,
#                 is_used=False
#             )
            
#             # Add platform filter if available
#             if platform:
#                 reset_token_query = reset_token_query.filter(user__platform=platform)
            
#             reset_token = reset_token_query.first()
            
#             if not reset_token:
#                 logger.warning(f"⚠️ Invalid reset token attempted for: {email}")
#                 return Response({
#                     'success': False,
#                     'error': 'Invalid reset token'
#                 }, status=status.HTTP_400_BAD_REQUEST)
            
#             if reset_token.is_expired():
#                 logger.warning(f"⚠️ Expired reset token used for: {email}")
#                 return Response({
#                     'success': False,
#                     'error': 'Reset token has expired. Please request a new one.'
#                 }, status=status.HTTP_400_BAD_REQUEST)
            
#             user = reset_token.user
#             user.set_password(new_password)
#             user.save()
            
#             reset_token.mark_as_used()
#             logger.info(f"✅ Password reset successfully for: {email}")
            
#             # ✅ FIXED: Pass platform explicitly to email service
#             try:
#                 from apps.notifications.email_service import EmailService
                
#                 # ✅ Use user's platform (which should match request.platform)
#                 user_platform = user.platform or platform
                
#                 logger.info(f"📧 Sending password change notification to {email} via platform: {user_platform.name if user_platform else 'Default'}")
                
#                 EmailService.send_password_change_notification(
#                     user=user,
#                     request=request,
#                     platform=user_platform  # ✅ PASS PLATFORM HERE
#                 )
#                 logger.info(f"✅ Password change notification sent to {email}")
#             except Exception as e:
#                 logger.error(f"❌ Failed to send password change notification: {str(e)}", exc_info=True)

#             return Response({
#                 'success': True,
#                 'message': 'Password reset successfully'
#             }, status=status.HTTP_200_OK)
            
#         except Exception as e:
#             logger.error(f"❌ Password reset confirmation failed: {str(e)}", exc_info=True)
#             return Response({
#                 'success': False,
#                 'error': 'Password reset failed. Please try again.'
#             }, status=status.HTTP_400_BAD_REQUEST)

class PasswordResetConfirmView(generics.CreateAPIView):
    """Password reset confirmation with platform support"""
    serializer_class = PasswordResetConfirmSerializer
    permission_classes = [permissions.AllowAny]
    
    def create(self, request, *args, **kwargs):
        # ✅ Debug: Log incoming data
        logger.info(f"🔍 Password reset confirm request data: {request.data}")
        
        serializer = self.get_serializer(data=request.data)
        
        # ✅ Log validation errors
        if not serializer.is_valid():
            logger.error(f"❌ Serializer validation errors: {serializer.errors}")
            return Response({
                'success': False,
                'error': 'Validation failed',
                'details': serializer.errors
            }, status=status.HTTP_400_BAD_REQUEST)
        
        try:
            token = serializer.validated_data['token']
            email = serializer.validated_data['email']
            new_password = serializer.validated_data['new_password']
            
            # ✅ Get platform from middleware
            platform = getattr(request, 'platform', None)
            logger.info(f"🔍 Platform from middleware: {platform.name if platform else 'None'}")
            
            # ✅ Filter by email, platform, and token
            reset_token_query = PasswordResetToken.objects.filter(
                token=token,
                user__email=email,
                is_used=False
            )
            
            # Add platform filter if available
            if platform:
                reset_token_query = reset_token_query.filter(user__platform=platform)
            
            reset_token = reset_token_query.first()
            
            if not reset_token:
                logger.warning(f"⚠️ Invalid reset token attempted for: {email}")
                return Response({
                    'success': False,
                    'error': 'Invalid reset token'
                }, status=status.HTTP_400_BAD_REQUEST)
            
            if reset_token.is_expired():
                logger.warning(f"⚠️ Expired reset token used for: {email}")
                return Response({
                    'success': False,
                    'error': 'Reset token has expired. Please request a new one.'
                }, status=status.HTTP_400_BAD_REQUEST)
            
            user = reset_token.user
            user.set_password(new_password)
            user.save()
            
            reset_token.mark_as_used()
            logger.info(f"✅ Password reset successfully for: {email}")
            
            # ✅ Send password change notification with platform
            try:
                from apps.notifications.email_service import EmailService
                
                # Use user's platform (should match request.platform)
                user_platform = user.platform
                
                logger.info(f"📧 Attempting to send email via platform: {user_platform.name if user_platform else 'Default'}")
                
                result = EmailService.send_password_change_notification(
                    user=user,
                    request=request,
                    platform=user_platform  # ✅ EXPLICIT PLATFORM
                )
                
                logger.info(f"✅ Email sent! Message ID: {result.get('message_id') if isinstance(result, dict) else 'N/A'}")
                
            except Exception as e:
                logger.error(f"❌ Failed to send password change notification: {str(e)}", exc_info=True)

            return Response({
                'success': True,
                'message': 'Password reset successfully'
            }, status=status.HTTP_200_OK)
            
        except Exception as e:
            logger.error(f"❌ Password reset confirmation failed: {str(e)}", exc_info=True)
            return Response({
                'success': False,
                'error': 'Password reset failed. Please try again.'
            }, status=status.HTTP_400_BAD_REQUEST)


@api_view(['POST'])
@permission_classes([permissions.IsAuthenticated])
def logout_view(request):
    """User logout"""
    try:
        refresh_token = request.data.get('refresh_token')
        if refresh_token:
            token = RefreshToken(refresh_token)
            token.blacklist()
        
        logger.info(f"👋 User logged out: {request.user.email}")
        
        return Response({
            'success': True,
            'message': 'Successfully logged out'
        }, status=status.HTTP_200_OK)
    except Exception as e:
        logger.error(f"❌ Logout failed: {str(e)}")
        return Response({
            'success': False,
            'error': 'Invalid token'
        }, status=status.HTTP_400_BAD_REQUEST)


@api_view(['GET'])
@permission_classes([permissions.IsAuthenticated])
def verify_token(request):
    """Verify JWT token with profile and platform info"""
    user = request.user
    
    profile_info = {
        'has_profile': False,
        'profile_type': None,
        'profile_id': None
    }
    
    if user.role == 'instructor':
        try:
            from apps.speakers.models import Speaker
            speaker = Speaker.objects.filter(user=user).first()
            if speaker:
                profile_info['has_profile'] = True
                profile_info['profile_type'] = 'speaker'
                profile_info['profile_id'] = speaker.id
        except (ImportError, AttributeError):
            pass
    elif user.role == 'attendee':
        try:
            from apps.attendees.models import AttendeeProfile
            attendee = AttendeeProfile.objects.filter(user=user).first()
            if attendee:
                profile_info['has_profile'] = True
                profile_info['profile_type'] = 'attendee'
                profile_info['profile_id'] = attendee.id
        except (ImportError, AttributeError):
            pass
    
    platform_info = None
    if user.platform:
        platform_info = {
            'id': user.platform.id,
            'platform_id': user.platform.platform_id,
            'name': user.platform.name,
            'logo_url': user.platform.logo_url,
            'primary_color': user.platform.primary_color,
        }
    
    return Response({
        'success': True,
        'valid': True,
        'user': {
            'id': user.id,
            'email': user.email,
            'first_name': user.first_name,
            'last_name': user.last_name,
            'full_name': user.full_name,
            'role': user.role,
            'avatar': user.avatar.url if user.avatar else None,
            'phone': user.phone,
            'company': user.company,
            'is_verified': user.is_verified,
            'is_active': user.is_active,
            'platform': platform_info,
        },
        'profile': profile_info
    }, status=status.HTTP_200_OK)


@api_view(['POST'])
@permission_classes([permissions.IsAuthenticated])
def create_profile(request):
    """Manually create profile with platform support"""
    user = request.user
    
    if not user.is_verified:
        return Response({
            'success': False,
            'error': 'Email must be verified before creating profile'
        }, status=status.HTTP_400_BAD_REQUEST)
    
    profile_created = False
    profile_type = None
    
    if user.role == 'instructor':
        try:
            from apps.speakers.models import Speaker
            speaker_profile, created = Speaker.objects.get_or_create(
                user=user,
                defaults={
                    'user': user,
                    'title': '',
                }
            )
            if created:
                profile_created = True
                profile_type = 'Speaker Profile'
                logger.info(f"✅ Manual speaker profile created for: {user.email}")
        except ImportError:
            return Response({
                'success': False,
                'error': 'Speaker app not available'
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
            
    elif user.role == 'attendee':
        try:
            from apps.attendees.models import AttendeeProfile
            attendee_profile, created = AttendeeProfile.objects.get_or_create(
                user=user,
                defaults={
                    'user': user,
                    'platform': user.platform,
                    'skill_level': 'beginner',
                    'language': 'en',
                    'timezone': 'America/New_York'
                }
            )
            if created:
                profile_created = True
                profile_type = 'Attendee Profile'
                logger.info(f"✅ Manual attendee profile created for: {user.email}")
        except ImportError:
            return Response({
                'success': False,
                'error': 'Attendees app not available'
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
    
    if profile_created:
        return Response({
            'success': True,
            'message': f'{profile_type} created successfully',
            'profile_type': profile_type.lower().replace(' profile', ''),
            'created': True
        }, status=status.HTTP_201_CREATED)
    else:
        logger.info(f"⚠️  Profile creation skipped for {user.email} - already exists")
        return Response({
            'success': False,
            'message': 'Profile already exists or invalid role',
            'created': False
        }, status=status.HTTP_400_BAD_REQUEST)
