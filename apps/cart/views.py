from rest_framework import generics, permissions, status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response
from django.db import transaction
from django.contrib.auth import get_user_model
from apps.webinars.models import Webinar
from .models import Cart, CartItem, CartSession
from .serializers import (
    CartSerializer, CartItemSerializer, CartItemCreateSerializer,
    CartSummarySerializer, CartMergeSerializer
)
import uuid

User = get_user_model()

class CartView(generics.RetrieveUpdateAPIView):
    """Get or clear user's cart"""
    
    serializer_class = CartSerializer
    permission_classes = [permissions.IsAuthenticated]
    
    def get_object(self):
        cart, created = Cart.objects.get_or_create(user=self.request.user)
        return cart
    
    def patch(self, request, *args, **kwargs):
        """Clear cart"""
        if request.data.get('action') == 'clear':
            cart = self.get_object()
            cart.clear()
            return Response({'message': 'Cart cleared successfully'})
        
        return super().patch(request, *args, **kwargs)


class CartItemListCreateView(generics.ListCreateAPIView):
    """List cart items or add new item"""
    
    serializer_class = CartItemSerializer
    permission_classes = [permissions.IsAuthenticated]
    
    def get_queryset(self):
        cart, created = Cart.objects.get_or_create(user=self.request.user)
        return cart.items.select_related('webinar', 'webinar__instructor', 'webinar__category')
    
    def get_serializer_class(self):
        if self.request.method == 'POST':
            return CartItemCreateSerializer
        return CartItemSerializer
    
    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        
        # Get or create cart
        cart, created = Cart.objects.get_or_create(user=request.user)
        
        # Get webinar
        webinar = serializer.validated_data['webinar_id']
        access_type = serializer.validated_data['access_type']
        
        # Check if item already exists
        existing_item = cart.items.filter(
            webinar=webinar,
            access_type=access_type
        ).first()
        
        if existing_item:
            # Update quantity instead of creating new item
            existing_item.quantity += serializer.validated_data.get('quantity', 1)
            existing_item.save()
            response_serializer = CartItemSerializer(existing_item)
        else:
            # Create new cart item
            cart_item = CartItem.objects.create(
                cart=cart,
                webinar=webinar,
                **{k: v for k, v in serializer.validated_data.items() if k != 'webinar_id'}
            )
            response_serializer = CartItemSerializer(cart_item)
        
        return Response(response_serializer.data, status=status.HTTP_201_CREATED)


class CartItemDetailView(generics.RetrieveUpdateDestroyAPIView):
    """Cart item detail operations"""
    
    serializer_class = CartItemSerializer
    permission_classes = [permissions.IsAuthenticated]
    lookup_field = 'item_id'
    
    def get_queryset(self):
        cart, created = Cart.objects.get_or_create(user=self.request.user)
        return cart.items.all()


@api_view(['POST'])
@permission_classes([permissions.IsAuthenticated])
def merge_cart_on_login(request):
    """Merge session cart with user cart on login"""
    
    serializer = CartMergeSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)
    
    session_cart_data = serializer.validated_data['session_cart_data']
    
    # Get or create user cart
    user_cart, created = Cart.objects.get_or_create(user=request.user)
    
    merged_items = []
    skipped_items = []
    
    with transaction.atomic():
        for item_data in session_cart_data:
            try:
                # Get webinar
                webinar = Webinar.objects.get(id=item_data['webinarId'])
                
                # Map frontend access type to backend
                access_type_mapping = {
                    'Live - Single Attendee': 'live_single',
                    'Live - Multi Attendees': 'live_group',
                    'Recorded - Single Attendee': 'recorded_single',
                    'Recorded - Multi Attendees': 'recorded_group',
                    'Live + Recorded - Single': 'combo_single',
                    'Live + Recorded - Multi': 'combo_group',
                }
                
                access_type = access_type_mapping.get(item_data['accessType'])
                if not access_type:
                    skipped_items.append(item_data['title'])
                    continue
                
                # Check if item already exists in user cart
                existing_item = user_cart.items.filter(
                    webinar=webinar,
                    access_type=access_type
                ).first()
                
                if existing_item:
                    # Skip if already exists
                    skipped_items.append(item_data['title'])
                else:
                    # Create new cart item
                    cart_item = CartItem.objects.create(
                        cart=user_cart,
                        webinar=webinar,
                        access_type=access_type,
                        price=item_data['price'],
                        quantity=1,
                        description=item_data.get('description', ''),
                        duration=item_data.get('duration', '')
                    )
                    merged_items.append(cart_item)
            
            except Webinar.DoesNotExist:
                skipped_items.append(item_data.get('title', 'Unknown webinar'))
            except Exception as e:
                skipped_items.append(item_data.get('title', 'Unknown webinar'))
    
    # Return updated cart
    cart_serializer = CartSerializer(user_cart)
    
    return Response({
        'cart': cart_serializer.data,
        'merged_items': len(merged_items),
        'skipped_items': len(skipped_items),
        'message': f'Merged {len(merged_items)} items into your cart'
    })


@api_view(['GET'])
@permission_classes([permissions.IsAuthenticated])
def cart_summary(request):
    """Get cart summary for checkout"""
    
    cart, created = Cart.objects.get_or_create(user=request.user)
    
    if cart.is_empty:
        return Response({
            'error': 'Cart is empty'
        }, status=status.HTTP_400_BAD_REQUEST)
    
    # Calculate summary
    subtotal = cart.total_amount
    discount = 0  # Can be enhanced with coupon logic
    tax = subtotal * 0.08  # 8% tax
    total = subtotal - discount + tax
    
    # Prepare items summary
    items_summary = []
    for item in cart.items.select_related('webinar').all():
        items_summary.append({
            'id': str(item.item_id),
            'webinar_id': item.webinar.id,
            'title': item.webinar.title,
            'instructor': item.webinar.instructor.full_name if item.webinar.instructor else '',
            'access_type': item.get_access_type_display(),
            'price': float(item.price),
            'quantity': item.quantity,
            'total_price': float(item.total_price),
            'webinar_type': item.webinar_type,
            'image': item.webinar.thumbnail.url if item.webinar.thumbnail else '',
        })
    
    summary_data = {
        'subtotal': subtotal,
        'discount': discount,
        'tax': tax,
        'total': total,
        'item_count': cart.total_items,
        'items': items_summary
    }
    
    serializer = CartSummarySerializer(summary_data)
    return Response(serializer.data)


@api_view(['POST'])
@permission_classes([permissions.IsAuthenticated])
def add_to_cart_from_webinar(request, webinar_id):
    """Add webinar to cart with specific configuration"""
    
    try:
        webinar = Webinar.objects.get(id=webinar_id)
    except Webinar.DoesNotExist:
        return Response({
            'error': 'Webinar not found'
        }, status=status.HTTP_404_NOT_FOUND)
    
    # Get cart
    cart, created = Cart.objects.get_or_create(user=request.user)
    
    # Extract data from request
    access_type = request.data.get('access_type')
    price = request.data.get('price')
    
    if not access_type or price is None:
        return Response({
            'error': 'access_type and price are required'
        }, status=status.HTTP_400_BAD_REQUEST)
    
    # Check if item already exists
    existing_item = cart.items.filter(
        webinar=webinar,
        access_type=access_type
    ).first()
    
    if existing_item:
        return Response({
            'error': 'Item already in cart',
            'item': CartItemSerializer(existing_item).data
        }, status=status.HTTP_400_BAD_REQUEST)
    
    # Create cart item
    cart_item = CartItem.objects.create(
        cart=cart,
        webinar=webinar,
        access_type=access_type,
        price=price,
        quantity=1,
        description=request.data.get('description', ''),
        duration=request.data.get('duration', '')
    )
    
    # Return updated cart
    cart_serializer = CartSerializer(cart)
    return Response({
        'message': 'Added to cart successfully',
        'cart': cart_serializer.data,
        'item': CartItemSerializer(cart_item).data
    })
