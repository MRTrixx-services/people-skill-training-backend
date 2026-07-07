from django.contrib.auth.backends import ModelBackend
from django.db.models import Q
from apps.users.models import User
import logging

logger = logging.getLogger(__name__)


class EmailAuthBackend(ModelBackend):
    """
    Custom authentication backend for email-based login
    
    Allows authentication with:
    1. Email + Password (for admin and API)
    2. username_key + Password (for internal use)
    """
    
    def authenticate(self, request, username=None, password=None, **kwargs):
        """
        Authenticate user by email or username_key
        
        Args:
            request: HTTP request object
            username: Can be either email or username_key
            password: User password
            
        Returns:
            User object if successful, None otherwise
        """
        if username is None or password is None:
            return None
        
        try:
            # Try to find user by email OR username_key
            user = User.objects.filter(
                Q(email=username) | Q(username_key=username)
            ).first()
            
            if user and user.check_password(password):
                logger.info(f"Successful authentication for: {user.email}")
                return user
            else:
                logger.warning(f"Failed authentication attempt for: {username}")
                
        except User.DoesNotExist:
            # Run default password hasher to prevent timing attacks
            User().set_password(password)
            logger.warning(f"Authentication attempt for non-existent user: {username}")
            return None
        except Exception as e:
            logger.error(f"Authentication error: {str(e)}")
            return None
        
        return None
    
    def get_user(self, user_id):
        """Get user by primary key"""
        try:
            return User.objects.get(pk=user_id)
        except User.DoesNotExist:
            return None
