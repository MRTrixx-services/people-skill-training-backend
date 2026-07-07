# -----------------------------
# WEBINAR AUTO-MANAGEMENT TASK
# -----------------------------

from celery import shared_task
from django.utils import timezone
from datetime import timedelta
import logging

logger = logging.getLogger(__name__)


@shared_task(name='webinars.auto_manage_live_webinars')
def auto_manage_live_webinars():
    from apps.webinars.models import Webinar
    from apps.integrations.services import ZoomAPIService

    try:
        zoom_api = ZoomAPIService()
    except Exception as e:
        logger.error(f"❌ Zoom API init failed: {e}")
        return {'error': str(e)}

    # Prefetch zoom_meetings to avoid N+1
    # Check both 'scheduled' and 'live' webinars - they can both be marked as completed after 24h
    webinars = Webinar.objects.filter(
        webinar_type='live',
        status__in=['scheduled', 'live']
    ).prefetch_related('zoom_meetings').select_related('speaker')

    stats = {
        'checked': 0,
        'forced_completed': 0,
        'zoom_completed': 0,
        'recordings_found': 0,
        'recorded_created': 0,
        'errors': 0,
    }

    for webinar in webinars:
        stats['checked'] += 1
        try:
            # 🔒 ALWAYS enforce 48-hour rule first
            force_result = force_complete_after_48_hours(webinar)
            if force_result['status_changed']:
                stats['forced_completed'] += 1
                # Refresh in-memory status
                webinar.status = 'completed'

            # Only check Zoom if still scheduled
            if webinar.status == 'scheduled':
                zoom_meeting = webinar.zoom_meetings.first()
                if zoom_meeting and zoom_meeting.zoom_meeting_id:
                    zoom_result = sync_zoom_completion_only(webinar, zoom_meeting, zoom_api)
                    if zoom_result['status_changed']:
                        stats['zoom_completed'] += 1
                        webinar.status = 'completed'

            # Handle recordings if completed
            if webinar.status == 'completed' and not webinar.has_recording:
                rec_result = check_and_add_recordings(webinar, zoom_api)
                if rec_result['found']:
                    stats['recordings_found'] += 1
                    if webinar.auto_convert_to_recorded:
                        created_result = create_recorded_webinar_from_live(webinar)
                        if created_result['created']:
                            stats['recorded_created'] += 1

        except Exception as e:
            logger.exception(f"❌ Webinar {webinar.webinar_id} failed: {e}")
            stats['errors'] += 1

    logger.info(f"✅ Webinar auto-manage stats: {stats}")
    return stats


# -----------------------------
# CORE LOGIC FUNCTIONS
# -----------------------------

def force_complete_after_48_hours(webinar):
    """Force COMPLETED if current time >= scheduled_end + 24h. Handles missing dates gracefully."""
    from django.utils import timezone
    from datetime import timedelta
    
    result = {'status_changed': False}
    if webinar.status == 'completed':
        return result

    try:
        now = timezone.now()
        scheduled_end = None
        fallback_used = False

        # Priority 1: Use scheduled_date + duration
        if webinar.scheduled_date and webinar.duration:
            scheduled_end = webinar.scheduled_date + timedelta(minutes=webinar.duration)
        
        # Priority 2: Use created_at (fallback for legacy webinars without scheduled_date)
        elif webinar.created_at:
            # Use created_at + a default 1-day assumption
            scheduled_end = webinar.created_at + timedelta(days=1)
            fallback_used = True
        else:
            # No date info - cannot process
            logger.warning(f"⏭️  {webinar.webinar_id}: No scheduled_date or created_at, skipping")
            return result

        deadline = scheduled_end + timedelta(hours=24)

        if now >= deadline:
            webinar.status = 'completed'
            webinar.save(update_fields=['status', 'updated_at'])
            result['status_changed'] = True
            
            if fallback_used:
                logger.info(f"⏱️ Forced COMPLETED (24h, fallback): {webinar.webinar_id}")
            else:
                logger.info(f"⏱️ Forced COMPLETED (24h): {webinar.webinar_id}")
                
    except Exception as e:
        logger.error(f"24h rule failed for {webinar.webinar_id}: {e}")

    return result


def sync_zoom_completion_only(webinar, zoom_meeting, zoom_api):
    result = {'status_changed': False}
    try:
        meeting_data = zoom_api.get_meeting(zoom_meeting.zoom_meeting_id)
        if meeting_data and meeting_data.get('end_time') and webinar.status != 'completed':
            webinar.status = 'completed'
            webinar.save(update_fields=['status', 'updated_at'])
            result['status_changed'] = True
            logger.info(f"✅ Zoom ended → COMPLETED: {webinar.webinar_id}")
    except Exception as e:
        logger.error(f"Zoom sync failed for {webinar.webinar_id}: {e}")
    return result


def check_and_add_recordings(webinar, zoom_api):
    result = {'found': False}
    try:
        zoom_meeting = webinar.zoom_meetings.first()
        if not zoom_meeting:
            return result

        # ✅ Use meeting-specific recording endpoint
        recordings = zoom_api.get_meeting_recordings(zoom_meeting.zoom_meeting_id)
        if not recordings or not recordings.get('recording_files'):
            return result

        files = recordings['recording_files']
        primary = next((f for f in files if f.get('file_type') == 'MP4'), files[0])
        url = primary.get('play_url') or primary.get('download_url')
        if not url:
            return result

        webinar.zoom_url = url
        webinar.has_recording = True
        webinar.last_recording_check = timezone.now()
        webinar.save(update_fields=['zoom_url', 'has_recording', 'last_recording_check', 'updated_at'])
        result['found'] = True
        logger.info(f"🎬 Recording attached: {webinar.webinar_id}")
    except Exception as e:
        logger.error(f"Recording check failed for {webinar.webinar_id}: {e}")
    return result


def create_recorded_webinar_from_live(live_webinar):
    from apps.webinars.models import Webinar
    result = {'created': False}

    if not live_webinar.has_recording or not live_webinar.zoom_url:
        return result

    if Webinar.objects.filter(
        title=live_webinar.title,
        webinar_type='recorded',
        speaker=live_webinar.speaker
    ).exists():
        return result

    try:
        recorded = Webinar.objects.create(
            title=live_webinar.title,
            description=live_webinar.description,
            speaker=live_webinar.speaker,
            category=live_webinar.category,
            skill_level=live_webinar.skill_level,
            webinar_type='recorded',
            status='available',
            zoom_url=live_webinar.zoom_url,
            has_recording=True,
            duration=live_webinar.duration,
            pricing_data=convert_live_to_recorded_pricing(live_webinar.pricing_data),
            cover_image=live_webinar.cover_image,
            has_enrollment_limit=False,
            max_attendees=None,
            auto_convert_to_recorded=False,
        )
        if live_webinar.platforms.exists():
            recorded.platforms.set(live_webinar.platforms.all())
        result['created'] = True
        result['webinar_id'] = recorded.webinar_id
        logger.info(f"🎉 Recorded webinar created: {recorded.webinar_id}")
    except Exception as e:
        logger.error(f"Recorded creation failed: {e}")
    return result


def convert_live_to_recorded_pricing(live_pricing):
    if not live_pricing:
        return {}
    return {
        'recorded_single_price': live_pricing.get('recorded_single_price', live_pricing.get('live_single_price', '0.00')),
        'recorded_multi_price': live_pricing.get('recorded_multi_price', live_pricing.get('live_multi_price', '0.00')),
        'live_single_price': None,
        'live_multi_price': None,
        'combo_single_price': None,
        'combo_multi_price': None,
        'early_bird_single_price': None,
        'early_bird_multi_price': None,
        'early_bird_end_date': None,
    }