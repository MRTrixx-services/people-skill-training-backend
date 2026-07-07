from django.db.models import Count, Sum, Q
from django.utils import timezone
from datetime import timedelta


def calculate_platform_stats(platform):
    """Calculate and update platform statistics"""
    from apps.users.models import User
    from apps.webinars.models import Webinar
    from apps.enrollments.models import Enrollment
    from apps.payments.models import Payment
    
    stats = platform.stats
    
    # User stats
    users = User.objects.filter(platform=platform)
    stats.total_users = users.count()
    stats.active_users = users.filter(is_active=True).count()
    stats.total_instructors = users.filter(role='instructor').count()
    stats.total_attendees = users.filter(role='attendee').count()
    
    # Webinar stats
    platform_webinars = Webinar.objects.filter(platforms=platform)
    stats.total_webinars = platform_webinars.count()
    stats.live_webinars = platform_webinars.filter(webinar_type='live').count()
    stats.recorded_webinars = platform_webinars.filter(webinar_type='recorded').count()
    
    # Enrollment stats
    enrollments = Enrollment.objects.filter(platform=platform)
    stats.total_enrollments = enrollments.count()
    stats.active_enrollments = enrollments.filter(
        status__in=['enrolled', 'attended']
    ).count()
    
    # Revenue stats
    payments = Payment.objects.filter(platform=platform, status='completed')
    total_revenue = payments.aggregate(total=Sum('amount'))['total'] or 0
    
    # This month revenue
    first_day_of_month = timezone.now().replace(
        day=1, hour=0, minute=0, second=0, microsecond=0
    )
    this_month_revenue = payments.filter(
        created_at__gte=first_day_of_month
    ).aggregate(total=Sum('amount'))['total'] or 0
    
    stats.total_revenue = total_revenue
    stats.this_month_revenue = this_month_revenue
    
    stats.save()
    return stats
