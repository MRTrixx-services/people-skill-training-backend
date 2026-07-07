from rest_framework import serializers
from .models import Cart, CartItem, CartSession
from apps.webinars.serializers import WebinarListSerializer


class CartItemSerializer(serializers.ModelSerializer):
    """Cart item with full webinar details"""
    
    webinar_title = serializers.CharField(source='webinar.title', read_only=True)
    webinar_image = serializers.SerializerMethodField()
    instructor_name = serializers.SerializerMethodField()
    total_price = serializers.DecimalField(max_digits=10, decimal_places=2, read_only=True)
    access_type_display = serializers.CharField(source='get_access_type_display', read_only=True)
    
    class Meta:
        model = CartItem
        fields = [
            'item_id', 'webinar', 'webinar_title', 'webinar_image',
            'instructor_name', 'access_type', 'access_type_display',
            'price', 'quantity', 'total_price', 'description',
            'duration', 'added_at', 'updated_at'
        ]
        read_only_fields = ['item_id', 'total_price', 'added_at', 'updated_at']
    
    def get_webinar_image(self, obj):
        if obj.webinar.thumbnail:
            request = self.context.get('request')
            if request:
                return request.build_absolute_uri(obj.webinar.thumbnail.url)
            return obj.webinar.thumbnail.url
        return None
    
    def get_instructor_name(self, obj):
        if obj.webinar.speaker and obj.webinar.speaker.user:
            return obj.webinar.speaker.user.get_full_name()
        return 'TBD'


class CartItemCreateSerializer(serializers.Serializer):
    """Create cart item"""
    
    webinar_id = serializers.IntegerField()
    access_type = serializers.ChoiceField(choices=CartItem.ACCESS_TYPE_CHOICES)
    price = serializers.DecimalField(max_digits=10, decimal_places=2)
    quantity = serializers.IntegerField(default=1, min_value=1)
    description = serializers.CharField(required=False, allow_blank=True)
    duration = serializers.CharField(required=False, allow_blank=True)
    
    def validate_webinar_id(self, value):
        from apps.webinars.models import Webinar
        if not Webinar.objects.filter(id=value).exists():
            raise serializers.ValidationError('Webinar not found')
        return Webinar.objects.get(id=value)


class CartSerializer(serializers.ModelSerializer):
    """Cart with items"""
    
    items = CartItemSerializer(many=True, read_only=True)
    total_items = serializers.IntegerField(read_only=True)
    total_amount = serializers.DecimalField(max_digits=10, decimal_places=2, read_only=True)
    is_empty = serializers.BooleanField(read_only=True)
    
    class Meta:
        model = Cart
        fields = [
            'id', 'user', 'items', 'total_items',
            'total_amount', 'is_empty', 'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'user', 'created_at', 'updated_at']


class CartSummarySerializer(serializers.Serializer):
    """Cart checkout summary"""
    
    subtotal = serializers.DecimalField(max_digits=10, decimal_places=2)
    discount = serializers.DecimalField(max_digits=10, decimal_places=2)
    tax = serializers.DecimalField(max_digits=10, decimal_places=2)
    total = serializers.DecimalField(max_digits=10, decimal_places=2)
    item_count = serializers.IntegerField()
    items = serializers.ListField()


class CartMergeSerializer(serializers.Serializer):
    """Merge session cart with user cart"""
    
    session_cart_data = serializers.ListField(
        child=serializers.DictField(),
        allow_empty=True
    )
