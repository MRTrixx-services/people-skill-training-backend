from celery import shared_task
from django.core.management import call_command
from django.utils import timezone
import logging

logger = logging.getLogger(__name__)

@shared_task
def generate_daily_analytics():
    """Generate daily analytics data"""
    try:
        call_command('generate_analytics', days=1)
        logger.info('Daily analytics generated successfully')
    except Exception as e:
        logger.error(f'Error generating daily analytics: {str(e)}')

@shared_task
def generate_weekly_analytics():
    """Generate weekly analytics data"""
    try:
        call_command('generate_analytics', days=7)
        logger.info('Weekly analytics generated successfully')
    except Exception as e:
        logger.error(f'Error generating weekly analytics: {str(e)}')
