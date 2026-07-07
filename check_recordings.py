import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'peopleskilltrainingapp.settings')
django.setup()

from apps.webinars.models import Webinar

print("\n📹 WEBINARS WITH RECORDINGS\n")
print("-" * 70)

recordings = Webinar.objects.filter(has_recording=True).values(
    'webinar_id', 'title', 'webinar_type', 'status'
)

for rec in recordings:
    print(f"✅ {rec['webinar_id']} - {rec['title'][:40]}")
    print(f"   Type: {rec['webinar_type']} | Status: {rec['status']}")

print(f"\n📊 Total: {recordings.count()} webinars with recordings")
