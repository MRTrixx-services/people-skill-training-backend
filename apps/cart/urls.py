from django.urls import path
from .views import (
    CartView,
    CartItemListCreateView,
    CartItemDetailView,
    merge_cart_on_login,
    cart_summary,
    add_to_cart_from_webinar
)

app_name = 'cart'

urlpatterns = [
    # Cart management
    path('', CartView.as_view(), name='cart_detail'),
    path('items/', CartItemListCreateView.as_view(), name='cart_items'),
    path('items/<uuid:item_id>/', CartItemDetailView.as_view(), name='cart_item_detail'),
    
    # Cart operations
    path('summary/', cart_summary, name='cart_summary'),
    path('merge/', merge_cart_on_login, name='merge_cart'),
    path('add/<int:webinar_id>/', add_to_cart_from_webinar, name='add_to_cart'),
]
