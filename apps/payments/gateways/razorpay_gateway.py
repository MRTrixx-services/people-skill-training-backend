import razorpay
import hmac
import hashlib
from decimal import Decimal
from typing import Dict, Any
from django.conf import settings
from .base import PaymentGatewayBase, PaymentGatewayError, PaymentVerificationError, RefundError


class RazorpayGateway(PaymentGatewayBase):
    """Razorpay payment gateway implementation"""
    
    def __init__(self, config: Dict[str, Any]):
        super().__init__(config)
        self.client = razorpay.Client(auth=(
            config.get('key_id', settings.RAZORPAY_KEY_ID),
            config.get('key_secret', settings.RAZORPAY_KEY_SECRET)
        ))
    
    def get_required_config_fields(self) -> list:
        return ['key_id', 'key_secret']
    
    def create_order(self, amount: Decimal, currency: str, order_data: Dict[str, Any]) -> Dict[str, Any]:
        """Create Razorpay order"""
        try:
            order_payload = {
                'amount': int(amount * 100),  # Convert to paise
                'currency': currency,
                'receipt': order_data.get('receipt', f"order_{order_data.get('user_id')}_{order_data.get('webinar_id')}"),
                'notes': order_data.get('notes', {})
            }
            
            order = self.client.order.create(data=order_payload)
            
            return {
                'success': True,
                'order_id': order['id'],
                'amount': order['amount'],
                'currency': order['currency'],
                'gateway_data': order
            }
        except Exception as e:
            raise PaymentGatewayError(f"Failed to create Razorpay order: {str(e)}", 'razorpay')
    
    def verify_payment(self, payment_data: Dict[str, Any]) -> Dict[str, Any]:
        """Verify Razorpay payment"""
        try:
            razorpay_order_id = payment_data.get('razorpay_order_id')
            razorpay_payment_id = payment_data.get('razorpay_payment_id')
            razorpay_signature = payment_data.get('razorpay_signature')
            
            # Verify signature
            self.client.utility.verify_payment_signature({
                'razorpay_order_id': razorpay_order_id,
                'razorpay_payment_id': razorpay_payment_id,
                'razorpay_signature': razorpay_signature
            })
            
            # Fetch payment details
            payment = self.client.payment.fetch(razorpay_payment_id)
            
            return {
                'success': True,
                'payment_id': razorpay_payment_id,
                'order_id': razorpay_order_id,
                'amount': payment['amount'] / 100,  # Convert from paise
                'currency': payment['currency'],
                'status': payment['status'],
                'gateway_data': payment
            }
        except Exception as e:
            raise PaymentVerificationError(f"Razorpay payment verification failed: {str(e)}", 'razorpay')
    
    def process_refund(self, payment_id: str, amount: Decimal, reason: str = None) -> Dict[str, Any]:
        """Process Razorpay refund"""
        try:
            refund_data = {
                'amount': int(amount * 100),  # Convert to paise
                'speed': 'normal'
            }
            
            if reason:
                refund_data['notes'] = {'reason': reason}
            
            refund = self.client.payment.refund(payment_id, refund_data)
            
            return {
                'success': True,
                'refund_id': refund['id'],
                'amount': refund['amount'] / 100,
                'status': refund['status'],
                'gateway_data': refund
            }
        except Exception as e:
            raise RefundError(f"Razorpay refund failed: {str(e)}", 'razorpay')
    
    def handle_webhook(self, payload: Dict[str, Any], signature: str = None) -> Dict[str, Any]:
        """Handle Razorpay webhook"""
        try:
            # Verify webhook signature
            webhook_secret = self.config.get('webhook_secret', settings.RAZORPAY_WEBHOOK_SECRET)
            if webhook_secret and signature:
                expected_signature = hmac.new(
                    webhook_secret.encode('utf-8'),
                    str(payload).encode('utf-8'),
                    hashlib.sha256
                ).hexdigest()
                
                if not hmac.compare_digest(signature, expected_signature):
                    raise PaymentGatewayError("Invalid webhook signature", 'razorpay')
            
            event_type = payload.get('event')
            payment_entity = payload.get('payload', {}).get('payment', {}).get('entity', {})
            
            return {
                'success': True,
                'event_type': event_type,
                'payment_id': payment_entity.get('id'),
                'order_id': payment_entity.get('order_id'),
                'amount': payment_entity.get('amount', 0) / 100 if payment_entity.get('amount') else 0,
                'status': payment_entity.get('status'),
                'gateway_data': payload
            }
        except Exception as e:
            raise PaymentGatewayError(f"Razorpay webhook handling failed: {str(e)}", 'razorpay')
