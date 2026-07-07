"""
Middleware to ensure webinar auto-completion runs even without Celery Beat.
Runs periodically based on last execution time.
"""

from django.utils import timezone
from datetime import timedelta
from django.core.cache import cache
import logging

logger = logging.getLogger(__name__)


class WebinarAutoCompletionMiddleware:
    """
    Ensures scheduled webinars get completed after 24h even if Celery Beat is down.
    Runs once every 30 minutes (configurable via WEBINAR_COMPLETION_INTERVAL).
    """

    def __init__(self, get_response):
        self.get_response = get_response
        try:
            from django.conf import settings
            self.interval_minutes = getattr(settings, 'WEBINAR_COMPLETION_INTERVAL', 30)
        except Exception as e:
            logger.warning(f"Could not load WEBINAR_COMPLETION_INTERVAL: {e}, using default 30")
            self.interval_minutes = 30

    def __call__(self, request):
        # Check if we should run the task
        try:
            if self._should_run_completion():
                self._run_completion_task()
        except Exception as e:
            logger.exception(f"Webinar completion middleware error: {e}")

        response = self.get_response(request)
        return response

    def _should_run_completion(self):
        """Check if enough time has passed since last execution."""
        try:
            cache_key = 'webinar_completion_last_run'
            last_run = cache.get(cache_key)
            now = timezone.now()

            if last_run is None:
                return True

            elapsed = (now - last_run).total_seconds() / 60  # Convert to minutes
            return elapsed >= self.interval_minutes
        except Exception as e:
            logger.warning(f"Cache check failed: {e}, running task anyway")
            return True

    def _run_completion_task(self):
        """Run the webinar completion task."""
        try:
            from apps.webinars.tasks import auto_manage_live_webinars
            cache_key = 'webinar_completion_last_run'
            
            result = auto_manage_live_webinars()
            
            # Only cache the time if successful
            if result and 'error' not in result:
                cache.set(cache_key, timezone.now(), timeout=3600)  # 1 hour max
                logger.info(f"✅ Webinar completion middleware executed: {result}")
            else:
                logger.warning(f"⚠️ Webinar completion failed: {result}")

        except Exception as e:
            logger.exception(f"❌ Webinar completion middleware error: {e}")
