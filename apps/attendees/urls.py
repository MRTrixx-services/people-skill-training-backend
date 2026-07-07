from django.urls import path
from . import views

app_name = 'attendees'

urlpatterns = [
    # Attendee management
    path('', views.AttendeeListView.as_view(), name='attendee-list'),
    path('me/', views.current_attendee, name='current-attendee'),
    path('profile/', views.AttendeeProfileView.as_view(), name='attendee-profile'),
    path('<int:pk>/', views.AttendeeDetailView.as_view(), name='attendee-detail'),
    path('public/<int:id>/', views.AttendeePublicProfileView.as_view(), name='attendee-public-profile'),
    path('public/', views.public_attendees, name='public-attendees'),
    
    # Activities
    path('activities/', views.AttendeeActivityListView.as_view(), name='attendee-activities'),
    path('log-activity/', views.log_attendee_activity, name='log-activity'),
    
    # Learning paths
    path('learning-paths/', views.AttendeeLearningPathListView.as_view(), name='learning-paths'),
    path('learning-paths/<int:pk>/', views.AttendeeLearningPathDetailView.as_view(), name='learning-path-detail'),
    
    # Statistics
    path('stats/', views.attendee_stats, name='attendee-stats'),
]
