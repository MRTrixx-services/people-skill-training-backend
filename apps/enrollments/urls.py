from django.urls import path
from .views import (
    EnrollmentListView,
    EnrollmentDetailView,
    EnrollmentCreateView,
    MyEnrollmentsView,
    UpcomingEnrollmentsView,
    EnrollmentFeedbackView,
    CertificateListView,
    CertificateDetailView,
    WaitlistCreateView,
    MyWaitlistView,
    cancel_enrollment,
    track_attendance,
    enrollment_stats,
    user_enrollment_stats,
    leave_waitlist,
)

app_name = 'enrollments'

urlpatterns = [
    # Enrollments
    path('', EnrollmentListView.as_view(), name='enrollment_list'),
    path('<int:pk>/', EnrollmentDetailView.as_view(), name='enrollment_detail'),
    path('create/', EnrollmentCreateView.as_view(), name='enrollment_create'),
    path('my/', MyEnrollmentsView.as_view(), name='my_enrollments'),
    path('upcoming/', UpcomingEnrollmentsView.as_view(), name='upcoming_enrollments'),
    path('<int:enrollment_id>/cancel/', cancel_enrollment, name='cancel_enrollment'),
    
    # Feedback
    path('<int:enrollment_id>/feedback/', EnrollmentFeedbackView.as_view(), name='enrollment_feedback'),
    
    # Certificates
    path('certificates/', CertificateListView.as_view(), name='certificate_list'),
    path('certificates/<str:certificate_id>/', CertificateDetailView.as_view(), name='certificate_detail'),
    
    # Waitlist
    path('waitlist/join/', WaitlistCreateView.as_view(), name='join_waitlist'),
    path('waitlist/my/', MyWaitlistView.as_view(), name='my_waitlist'),
    path('waitlist/<int:waitlist_id>/leave/', leave_waitlist, name='leave_waitlist'),
    
    # Attendance tracking
    path('attendance/track/', track_attendance, name='track_attendance'),
    
    # Statistics
    path('stats/', enrollment_stats, name='enrollment_stats'),
    path('user/stats/', user_enrollment_stats, name='user_enrollment_stats'), 
    # path('stats/user/', user_enrollment_stats, name='user_enrollment_stats'),
]
