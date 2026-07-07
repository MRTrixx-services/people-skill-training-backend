from django.urls import path
from . import views

app_name = 'users'

urlpatterns = [
    # User management (no auth routes since they're in authentication app)
    path('', views.UserListView.as_view(), name='user-list'),
    path('me/', views.current_user, name='current-user'),
    path('profile/', views.UserProfileUpdateView.as_view(), name='user-profile-update'),
    path('<int:pk>/', views.UserDetailView.as_view(), name='user-detail'),
    path('public/<int:id>/', views.UserPublicProfileView.as_view(), name='user-public-profile'),
    
    # Role-based endpoints
    path('role/<str:role>/', views.user_by_role, name='users-by-role'),
    path('update-role/', views.update_user_role, name='update-user-role'),
    
    # Statistics
    path('stats/', views.user_stats, name='user-stats'),
]
