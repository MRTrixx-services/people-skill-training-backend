from django.urls import path
from . import views

app_name = 'payments'

urlpatterns = [
    # Payment gateway configuration
    path('gateways/', views.get_available_payment_gateways, name='available-gateways'),
    
    # Payment processing
    path('checkout/', views.checkout, name='checkout'),
    path('verify/', views.verify_payment, name='verify-payment'),
    path('stripe/session/<str:session_id>/', views.stripe_session_details, name='stripe-session-details'),
    
    # User payment endpoints
    path('', views.PaymentListView.as_view(), name='payment-list'),
    path('<str:invoice_number>/', views.PaymentDetailView.as_view(), name='payment-detail'),

    # path('<int:pk>/', views.PaymentDetailView.as_view(), name='payment-detail'),
    path('<int:pk>/invoice/', views.download_invoice, name='download-invoice'),
    
    # Refund endpoints
    path('refunds/', views.RefundRequestListView.as_view(), name='refund-list'),
    path('refunds/<int:pk>/', views.RefundRequestDetailView.as_view(), name='refund-detail'),
    path('refunds/<int:pk>/process/', views.process_refund, name='process-refund'),
    
    # Admin analytics endpoints
    path('admin/overview/', views.PaymentOverviewView.as_view(), name='payment-overview'),
    path('admin/analytics/revenue/', views.RevenueAnalyticsView.as_view(), name='revenue-analytics'),
    path('admin/analytics/refunds/', views.RefundStatisticsView.as_view(), name='refund-statistics'),
    path('admin/payments/', views.AdminPaymentListView.as_view(), name='admin-payment-list'),
    path('admin/payments/<int:pk>/', views.AdminPaymentDetailView.as_view(), name='admin-payment-detail'),
    
    # ✅ ADMIN INVOICE ENDPOINTS - ADD THESE
    path('admin/payments/<int:pk>/invoice/', views.download_invoice_admin, name='admin-download-invoice'),
    path('admin/payments/<int:pk>/resend-invoice/', views.resend_invoice_admin, name='admin-resend-invoice'),
]