from django.urls import path
from . import views

app_name = 'speakers'

urlpatterns = [
    # Speaker CRUD
    path('', views.SpeakerListView.as_view(), name='speaker-list'),
    path('create/', views.SpeakerCreateView.as_view(), name='speaker-create'),
    path('<int:pk>/', views.SpeakerDetailView.as_view(), name='speaker-detail'),
    path('public/<int:id>/', views.SpeakerPublicProfileView.as_view(), name='speaker-public-profile'),
    path('me/', views.CurrentSpeakerView.as_view(), name='current-speaker'),
    path('profile/', views.CurrentSpeakerView.as_view(), name='speaker-profile'),
    
    # Search and filtering
    path('search/', views.search_speakers, name='search-speakers'),
    path('featured/', views.featured_speakers, name='featured-speakers'),
    
    # Statistics (admin)
    path('admin/stats/', views.admin_speaker_stats, name='admin-speaker-stats'),
]
