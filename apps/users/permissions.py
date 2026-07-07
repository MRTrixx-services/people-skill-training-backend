from rest_framework import permissions


class IsOwnerOrAdmin(permissions.BasePermission):
    """
    Permission to only allow owners of an object or admins to access it.
    """

    def has_object_permission(self, request, view, obj):
        # Admin users have full access
        if request.user.is_staff or request.user.role == 'admin':
            return True
        
        # Check if the object is the user themselves
        if hasattr(obj, 'user'):
            return obj.user == request.user
        
        # Direct user object comparison
        return obj == request.user


class IsAdminOrReadOnly(permissions.BasePermission):
    """
    Permission to allow read access to anyone, but write access only to admins.
    """

    def has_permission(self, request, view):
        if request.method in permissions.SAFE_METHODS:
            return True
        
        return (request.user.is_authenticated and 
                (request.user.is_staff or request.user.role == 'admin'))


class IsInstructorOrAdmin(permissions.BasePermission):
    """
    Permission for instructors and admins only.
    """

    def has_permission(self, request, view):
        return (request.user.is_authenticated and 
                (request.user.role in ['instructor', 'admin'] or request.user.is_staff))


class IsAttendeeOrAdmin(permissions.BasePermission):
    """
    Permission for attendees and admins only.
    """

    def has_permission(self, request, view):
        return (request.user.is_authenticated and 
                (request.user.role in ['attendee', 'admin'] or request.user.is_staff))


class IsAdminOnly(permissions.BasePermission):
    """
    Permission for admins only.
    """

    def has_permission(self, request, view):
        return (request.user.is_authenticated and 
                (request.user.is_staff or request.user.role == 'admin'))
    
    def has_object_permission(self, request, view, obj):
        return (request.user.is_authenticated and 
                (request.user.is_staff or request.user.role == 'admin'))


class IsAdminUser(permissions.BasePermission):
    """
    Permission for admin users only (alias for IsAdminOnly for backward compatibility).
    """

    def has_permission(self, request, view):
        return (request.user.is_authenticated and 
                (request.user.is_staff or request.user.role == 'admin'))
    
    def has_object_permission(self, request, view, obj):
        return (request.user.is_authenticated and 
                (request.user.is_staff or request.user.role == 'admin'))


class IsOwnerOrReadOnly(permissions.BasePermission):
    """
    Object-level permission to only allow owners of an object to edit it.
    Assumes the model instance has an `owner` or `user` attribute.
    """

    def has_object_permission(self, request, view, obj):
        # Read permissions are allowed to any request,
        # so we'll always allow GET, HEAD or OPTIONS requests.
        if request.method in permissions.SAFE_METHODS:
            return True

        # Instance must have an attribute named `user` or `owner`.
        if hasattr(obj, 'user'):
            return obj.user == request.user
        elif hasattr(obj, 'owner'):
            return obj.owner == request.user
        
        return False


class IsInstructorOwnerOrAdmin(permissions.BasePermission):
    """
    Permission for instructor owners or admins only.
    Used for instructor-specific resources like webinars, courses, etc.
    """

    def has_permission(self, request, view):
        return (request.user.is_authenticated and 
                (request.user.role in ['instructor', 'admin'] or request.user.is_staff))
    
    def has_object_permission(self, request, view, obj):
        # Admin users have full access
        if request.user.is_staff or request.user.role == 'admin':
            return True
        
        # Check if the object belongs to the instructor
        if hasattr(obj, 'instructor'):
            return obj.instructor.user == request.user
        elif hasattr(obj, 'speaker'):
            return obj.speaker.user == request.user
        elif hasattr(obj, 'user'):
            return obj.user == request.user and request.user.role == 'instructor'
        
        return False


class IsAttendeeOwnerOrAdmin(permissions.BasePermission):
    """
    Permission for attendee owners or admins only.
    Used for attendee-specific resources like enrollments, progress, etc.
    """

    def has_permission(self, request, view):
        return (request.user.is_authenticated and 
                (request.user.role in ['attendee', 'admin'] or request.user.is_staff))
    
    def has_object_permission(self, request, view, obj):
        # Admin users have full access
        if request.user.is_staff or request.user.role == 'admin':
            return True
        
        # Check if the object belongs to the attendee
        if hasattr(obj, 'attendee'):
            return obj.attendee.user == request.user
        elif hasattr(obj, 'user'):
            return obj.user == request.user and request.user.role == 'attendee'
        
        return False


class IsVerifiedInstructor(permissions.BasePermission):
    """
    Permission for verified instructors only.
    """

    def has_permission(self, request, view):
        return (request.user.is_authenticated and 
                request.user.role == 'instructor' and 
                request.user.is_verified)


class IsActiveUser(permissions.BasePermission):
    """
    Permission for active users only.
    """

    def has_permission(self, request, view):
        return (request.user.is_authenticated and 
                request.user.is_active)


class IsSuperUser(permissions.BasePermission):
    """
    Permission for superusers only.
    """

    def has_permission(self, request, view):
        return (request.user.is_authenticated and 
                request.user.is_superuser)


class IsStaffUser(permissions.BasePermission):
    """
    Permission for staff users only.
    """

    def has_permission(self, request, view):
        return (request.user.is_authenticated and 
                request.user.is_staff)
