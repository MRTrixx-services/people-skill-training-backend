from django.db.models.signals import post_save, post_delete
from django.dispatch import receiver
from apps.enrollments.models import Enrollment
from apps.payments.models import Payment
from apps.webinars.models import Webinar
from .models import WebinarAnalytics, UserActivity

@receiver(post_save, sender=Enrollment)
def update_webinar_analytics_on_enrollment(sender, instance, created, **kwargs):
    """Update webinar analytics when enrollment is created"""
    if created:
        analytics, _ = WebinarAnalytics.objects.get_or_create(
            webinar=instance.webinar
        )
        analytics.total_enrollments = Enrollment.objects.filter(
            webinar=instance.webinar
        ).count()
        analytics.save()
        
        # Track user activity
        UserActivity.objects.create(
            user=instance.user,
            activity_type='enrollment',
            webinar=instance.webinar,
            metadata={'enrollment_id': instance.id}
        )

@receiver(post_save, sender=Payment)
def update_revenue_analytics_on_payment(sender, instance, created, **kwargs):
    """Update revenue analytics when payment is completed"""
    if instance.status == 'completed':
        analytics, _ = WebinarAnalytics.objects.get_or_create(
            webinar=instance.webinar
        )
        
        # Recalculate total revenue
        total_revenue = Payment.objects.filter(
            webinar=instance.webinar,
            status='completed'
        ).aggregate(total=models.Sum('amount'))['total'] or 0
        
        analytics.total_revenue = total_revenue
        analytics.save()
        
        # Track payment activity
        if created:
            UserActivity.objects.create(
                user=instance.user,
                activity_type='payment',
                webinar=instance.webinar,
                metadata={
                    'payment_id': instance.id,
                    'amount': str(instance.amount)
                }
            )
