from django.db import models
from django.core.validators import MinValueValidator, MaxValueValidator
from django.utils import timezone
from django.contrib.auth import get_user_model
from apps.webinars.models import Webinar
import uuid

User = get_user_model()

class Cart(models.Model):
    """Shopping cart for users"""
    
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='cart', null=True, blank=True)
    session_id = models.CharField(max_length=100, null=True, blank=True)  # For anonymous users
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        db_table = 'carts'
        verbose_name = 'Cart'
        verbose_name_plural = 'Carts'
    
    def __str__(self):
        if self.user:
            return f"Cart for {self.user.email}"
        return f"Anonymous Cart ({self.session_id})"
    
    @property
    def total_items(self):
        return self.items.count()
    
    @property
    def total_amount(self):
        return sum(item.total_price for item in self.items.all())
    
    @property
    def is_empty(self):
        return self.total_items == 0
    
    def clear(self):
        """Clear all items from cart"""
        self.items.all().delete()


class CartItem(models.Model):
    """Items in shopping cart"""
    
    ACCESS_TYPE_CHOICES = [
        ('live_single', 'Live - Single Attendee'),
        ('live_group', 'Live - Multi Attendees'),
        ('recorded_single', 'Recorded - Single Attendee'),
        ('recorded_group', 'Recorded - Multi Attendees'),
        ('combo_single', 'Live + Recorded - Single'),
        ('combo_group', 'Live + Recorded - Multi'),
    ]
    
    cart = models.ForeignKey(Cart, on_delete=models.CASCADE, related_name='items')
    webinar = models.ForeignKey(Webinar, on_delete=models.CASCADE)
    access_type = models.CharField(max_length=20, choices=ACCESS_TYPE_CHOICES)
    price = models.DecimalField(max_digits=10, decimal_places=2, validators=[MinValueValidator(0)])
    quantity = models.PositiveIntegerField(default=1, validators=[MinValueValidator(1)])
    
    # Additional item metadata
    item_id = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    added_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    # Pricing metadata for frontend
    description = models.TextField(blank=True)
    duration = models.CharField(max_length=50, blank=True)
    
    class Meta:
        db_table = 'cart_items'
        verbose_name = 'Cart Item'
        verbose_name_plural = 'Cart Items'
        unique_together = ['cart', 'webinar', 'access_type']
    
    def __str__(self):
        return f"{self.webinar.title} - {self.get_access_type_display()}"
    
    @property
    def total_price(self):
        return self.price * self.quantity
    
    @property
    def webinar_type(self):
        if 'live' in self.access_type and 'recorded' in self.access_type:
            return 'combo'
        elif 'live' in self.access_type:
            return 'live'
        elif 'recorded' in self.access_type:
            return 'recorded'
        return 'unknown'
    
    def save(self, *args, **kwargs):
        # Set description based on access type
        if not self.description:
            if self.access_type.endswith('_single'):
                if 'recorded' in self.access_type:
                    self.description = '6 months access to recorded webinar'
                elif 'live' in self.access_type:
                    self.description = 'Single attendee live session access'
                elif 'combo' in self.access_type:
                    self.description = 'Live session + 6 months recorded access'
            else:
                if 'recorded' in self.access_type:
                    self.description = 'Unlimited team access to recorded webinar'
                elif 'live' in self.access_type:
                    self.description = 'Multi-attendee live session access'
                elif 'combo' in self.access_type:
                    self.description = 'Live session + unlimited recorded access'
        
        super().save(*args, **kwargs)


class CartSession(models.Model):
    """Track anonymous cart sessions"""
    
    session_id = models.CharField(max_length=100, unique=True)
    user = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True)
    cart = models.ForeignKey(Cart, on_delete=models.CASCADE, null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    last_activity = models.DateTimeField(auto_now=True)
    is_merged = models.BooleanField(default=False)
    
    class Meta:
        db_table = 'cart_sessions'
        verbose_name = 'Cart Session'
        verbose_name_plural = 'Cart Sessions'
    
    def __str__(self):
        return f"Session {self.session_id}"
    
    @property
    def is_expired(self):
        # Sessions expire after 30 days
        return timezone.now() > self.last_activity + timezone.timedelta(days=30)
