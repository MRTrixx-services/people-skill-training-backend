# peopleskilltrainingapp/celery.py
import os
from celery import Celery
from celery.schedules import crontab

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'peopleskilltrainingapp.settings')

app = Celery('peopleskilltrainingapp')
app.config_from_object('django.conf:settings', namespace='CELERY')
app.autodiscover_tasks()

app.conf.beat_schedule = {
    'auto-manage-live-webinars': {
        'task': 'webinars.auto_manage_live_webinars',
        'schedule': crontab(hour='*/12', minute=0),
        'options': {'expires': 43200},
    },
}

app.conf.timezone = 'UTC'
app.conf.enable_utc = True


@app.task(bind=True)
def debug_task(self):
    print(f'Request: {self.request!r}')