"""
URL configuration for webinar_backend project.
"""
from django.contrib import admin
from django.urls import path, re_path, include
from django.conf import settings
from django.conf.urls.static import static
# from .views import FrontendAppView
urlpatterns = [
  
    path('djadmin/', admin.site.urls),
    path('api/auth/', include('apps.authentication.urls')),
    path('api/users/', include('apps.users.urls')),
    path('api/webinars/', include('apps.webinars.urls')),
    path('api/enrollments/', include('apps.enrollments.urls')),
    path('api/payments/', include('apps.payments.urls')),
    path('api/analytics/', include('apps.analytics.urls')),
    path('api/admin/', include('apps.analytics.urls')),
    path('api/notifications/', include('apps.notifications.urls')),
    path('api/integrations/', include('apps.integrations.urls')),
    path('api/speakers/', include('apps.speakers.urls')),
    path('api/attendees/', include('apps.attendees.urls')),
    path('api/cart/', include('apps.cart.urls')),
    path('api/platforms/', include('apps.platforms.urls')),
      # Catch-all for React SPA
    # re_path(r'^.*$', FrontendAppView.as_view(), name='frontend'),
]

# Serve media files in development
if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
    urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)
