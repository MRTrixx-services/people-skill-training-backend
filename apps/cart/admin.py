from django.contrib import admin
from .models import Cart, CartItem, CartSession


class CartItemInline(admin.TabularInline):
    model = CartItem
    extra = 0
    readonly_fields = ['item_id', 'total_price', 'added_at']
    fields = ['webinar', 'access_type', 'price', 'quantity', 'total_price', 'added_at']


@admin.register(Cart)
class CartAdmin(admin.ModelAdmin):
    list_display = ['id', 'user', 'get_user_email', 'total_items', 'total_amount', 'created_at']
    list_filter = ['created_at', 'updated_at']
    search_fields = ['user__email', 'user__first_name', 'user__last_name']
    readonly_fields = ['total_items', 'total_amount', 'created_at', 'updated_at']
    inlines = [CartItemInline]
    
    def get_user_email(self, obj):
        return obj.user.email if obj.user else 'Anonymous'
    get_user_email.short_description = 'Email'
    
    def total_items(self, obj):
        return obj.total_items
    total_items.short_description = 'Items'
    
    def total_amount(self, obj):
        return f"${obj.total_amount:.2f}"
    total_amount.short_description = 'Total'


@admin.register(CartItem)
class CartItemAdmin(admin.ModelAdmin):
    list_display = ['item_id', 'webinar', 'access_type', 'price', 'quantity', 'total_price', 'added_at']
    list_filter = ['access_type', 'added_at']
    search_fields = ['cart__user__email', 'webinar__title']
    readonly_fields = ['item_id', 'total_price', 'added_at', 'updated_at']
    
    def total_price(self, obj):
        return f"${obj.total_price:.2f}"
    total_price.short_description = 'Total'


@admin.register(CartSession)
class CartSessionAdmin(admin.ModelAdmin):
    list_display = ['session_id', 'user', 'is_merged', 'is_expired', 'created_at', 'last_activity']
    list_filter = ['is_merged', 'created_at', 'last_activity']
    search_fields = ['session_id', 'user__email']
    readonly_fields = ['is_expired', 'created_at', 'last_activity']
    
    def is_expired(self, obj):
        return obj.is_expired
    is_expired.boolean = True
    is_expired.short_description = 'Expired'
