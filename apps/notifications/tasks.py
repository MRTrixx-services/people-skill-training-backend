from celery import shared_task
from django.core.mail import send_mail
from django.conf import settings
from django.utils import timezone
from .models import Notification, EmailLog, SMSLog
import logging


logger = logging.getLogger(__name__)


@shared_task
def send_email_notification(notification_id):
    """Send email notification - Platform-aware"""
    try:
        notification = Notification.objects.select_related(
            'user', 'template', 'platform'
        ).get(id=notification_id)
        
        # Get platform-specific email settings
        from_email = settings.DEFAULT_FROM_EMAIL
        if notification.platform and hasattr(notification.platform, 'from_email'):
            from_email = notification.platform.from_email or from_email
        
        # Create email log
        email_log = EmailLog.objects.create(
            notification=notification,
            to_email=notification.user.email,
            from_email=from_email,
            subject=notification.title,
            body=notification.message
        )
        
        # Send email with platform-specific branding
        send_mail(
            subject=notification.title,
            message=notification.message,
            from_email=from_email,
            recipient_list=[notification.user.email],
            fail_silently=False
        )
        
        # Update notification and log
        notification.status = 'sent'
        notification.sent_at = timezone.now()
        notification.save()
        
        email_log.sent_at = timezone.now()
        email_log.delivery_status = 'sent'
        email_log.save()
        
        platform_name = notification.platform.name if notification.platform else 'System'
        logger.info(
            f"[{platform_name}] Email sent successfully to {notification.user.email}"
        )
        
    except Notification.DoesNotExist:
        logger.error(f"Notification {notification_id} not found")
    except Exception as e:
        logger.error(f"Failed to send email notification {notification_id}: {str(e)}")
        
        try:
            notification.status = 'failed'
            notification.save()
            
            if 'email_log' in locals():
                email_log.delivery_status = 'failed'
                email_log.error_message = str(e)
                email_log.save()
        except:
            pass


@shared_task
def send_sms_notification(notification_id):
    """Send SMS notification - Platform-aware"""
    try:
        notification = Notification.objects.select_related(
            'user', 'template', 'platform'
        ).get(id=notification_id)
        
        if not notification.user.phone:
            logger.warning(f"User {notification.user.email} has no phone number")
            notification.status = 'failed'
            notification.save()
            return
        
        # Create SMS log
        sms_log = SMSLog.objects.create(
            notification=notification,
            to_phone=notification.user.phone,
            message=notification.message
        )
        
        # TODO: Integrate with SMS service (Twilio, AWS SNS, etc.)
        # Platform-specific SMS gateway configuration
        # if notification.platform and notification.platform.sms_gateway:
        #     use platform-specific SMS gateway
        
        # For now, just mark as sent
        notification.status = 'sent'
        notification.sent_at = timezone.now()
        notification.save()
        
        sms_log.sent_at = timezone.now()
        sms_log.delivery_status = 'sent'
        sms_log.save()
        
        platform_name = notification.platform.name if notification.platform else 'System'
        logger.info(
            f"[{platform_name}] SMS sent successfully to {notification.user.phone}"
        )
        
    except Notification.DoesNotExist:
        logger.error(f"Notification {notification_id} not found")
    except Exception as e:
        logger.error(f"Failed to send SMS notification {notification_id}: {str(e)}")
        
        try:
            notification.status = 'failed'
            notification.save()
            
            if 'sms_log' in locals():
                sms_log.delivery_status = 'failed'
                sms_log.error_message = str(e)
                sms_log.save()
        except:
            pass


@shared_task
def process_scheduled_notifications():
    """Process notifications scheduled to be sent - Platform-aware"""
    now = timezone.now()
    
    scheduled_notifications = Notification.objects.filter(
        status='pending',
        scheduled_at__lte=now
    ).select_related('template', 'user', 'platform')
    
    total_processed = 0
    by_platform = {}
    
    for notification in scheduled_notifications:
        try:
            # Track by platform
            platform_name = notification.platform.name if notification.platform else 'System'
            by_platform[platform_name] = by_platform.get(platform_name, 0) + 1
            
            # Send based on template type
            if notification.template.template_type == 'email':
                send_email_notification.delay(notification.id)
            elif notification.template.template_type == 'sms':
                send_sms_notification.delay(notification.id)
            # Add other notification types as needed
            
            total_processed += 1
            
        except Exception as e:
            logger.error(
                f"Error processing notification {notification.id}: {str(e)}"
            )
    
    # Log summary
    logger.info(
        f"Processed {total_processed} scheduled notifications. "
        f"By platform: {by_platform}"
    )
    
    return {
        'total_processed': total_processed,
        'by_platform': by_platform
    }


@shared_task
def cleanup_old_notifications(days=30):
    """Clean up old read notifications - Platform-aware"""
    from datetime import timedelta
    
    cutoff_date = timezone.now() - timedelta(days=days)
    
    deleted = Notification.objects.filter(
        status='read',
        read_at__lt=cutoff_date
    ).delete()
    
    logger.info(
        f"Cleaned up {deleted[0]} notifications older than {days} days"
    )
    
    return deleted[0]


@shared_task
def send_platform_digest(platform_id, period='daily'):
    """Send digest notifications for a specific platform"""
    try:
        from apps.platforms.models import Platform
        
        platform = Platform.objects.get(id=platform_id)
        
        # Get unread notifications for this platform
        unread_count = Notification.objects.filter(
            platform=platform,
            status__in=['sent', 'pending']
        ).count()
        
        logger.info(
            f"[{platform.name}] {period.capitalize()} digest: "
            f"{unread_count} unread notifications"
        )
        
        # TODO: Implement digest email sending
        
    except Platform.DoesNotExist:
        logger.error(f"Platform {platform_id} not found")
