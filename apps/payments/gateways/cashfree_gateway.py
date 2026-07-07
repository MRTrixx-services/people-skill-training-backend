import requests
import hmac
import hashlib
import base64
from decimal import Decimal
from typing import Dict, Any
from django.conf import settings
from .base import PaymentGatewayBase, PaymentGatewayError, PaymentVerificationError, RefundError


class CashfreeGateway(PaymentGatewayBase):
    """Cashfree payment gateway implementation"""
    
    def __init__(self, config: Dict[str, Any]):
        super().__init__(config)
        self.app_id = config.get('app_id', settings.CASHFREE_APP_ID)
        self.secret_key = config.get('secret_key', settings.CASHFREE_SECRET_KEY)
        self.sandbox = config.get('sandbox', settings.CASHFREE_SANDBOX)
        self.base_url = 'https://sandbox.cashfree.com/pg' if self.sandbox else 'https://api.cashfree.com/pg'
    
    def get_required_config_fields(self) -> list:
        return ['app_id', 'secret_key']
    
    def get_headers(self) -> Dict[str, str]:
        """Get common headers for Cashfree API"""
        return {
            'Content-Type': 'application/json',
            'x-client-id': self.app_id,
            'x-client-secret': self.secret_key,
            'x-api-version': '2022-09-01'
        }
    
    def create_order(self, amount: Decimal, currency: str, order_data: Dict[str, Any]) -> Dict[str, Any]:
        """Create Cashfree order"""
        try:
            url = f"{self.base_url}/orders"
            headers = self.get_headers()
            
            payload = {
                'order_id': order_data.get('receipt', f"order_{order_data.get('user_id')}_{order_data.get('webinar_id')}"),
                'order_amount': float(amount),
                'order_currency': currency,
                'customer_details': {
                    'customer_id': str(order_data.get('user_id')),
                    'customer_name': order_data.get('customer_name', 'Customer'),
                    'customer_email': order_data.get('customer_email', 'customer@example.com'),
                    'customer_phone': order_data.get('customer_phone', '9999999999')
                },
                'order_meta': {
                    'return_url': order_data.get('return_url', 'https://example.com/success'),
                    'notify_url': order_data.get('notify_url', 'https://example.com/webhook')
                },
                'order_note': order_data.get('description', 'Webinar Purchase')
            }
            
            response = requests.post(url, headers=headers, json=payload)
            response.raise_for_status()
            
            order = response.json()
            
            return {
                'success': True,
                'order_id': order['order_id'],
                'amount': order['order_amount'],
                'currency': order['order_currency'],
                'payment_session_id': order.get('payment_session_id'),
                'gateway_data': order
            }
        except Exception as e:
            raise PaymentGatewayError(f"Failed to create Cashfree order: {str(e)}", 'cashfree')
    
    def verify_payment(self, payment_data: Dict[str, Any]) -> Dict[str, Any]:
        """Verify Cashfree payment"""
        try:
            order_id = payment_data.get('order_id')
            
            url = f"{self.base_url}/orders/{order_id}"
            headers = self.get_headers()
            
            response = requests.get(url, headers=headers)
            response.raise_for_status()
            
            order = response.json()
            
            if order['order_status'] == 'PAID':
                return {
                    'success': True,
                    'payment_id': order.get('cf_order_id'),
                    'order_id': order_id,
                    'amount': order['order_amount'],
                    'currency': order['order_currency'],
                    'status': order['order_status'],
                    'gateway_data': order
                }
            else:
                raise PaymentVerificationError(f"Cashfree payment not completed: {order['order_status']}", 'cashfree')
                
        except Exception as e:
            raise PaymentVerificationError(f"Cashfree payment verification failed: {str(e)}", 'cashfree')
    
    def process_refund(self, payment_id: str, amount: Decimal, reason: str = None) -> Dict[str, Any]:
        """Process Cashfree refund"""
        try:
            url = f"{self.base_url}/orders/{payment_id}/refunds"
            headers = self.get_headers()
            
            payload = {
                'refund_amount': float(amount),
                'refund_id': f"refund_{payment_id}_{int(amount * 100)}",
                'refund_note': reason or 'Refund requested'
            }
            
            response = requests.post(url, headers=headers, json=payload)
            response.raise_for_status()
            
            refund = response.json()
            
            return {
                'success': True,
                'refund_id': refund['refund_id'],
                'amount': refund['refund_amount'],
                'status': refund['refund_status'],
                'gateway_data': refund
            }
        except Exception as e:
            raise RefundError(f"Cashfree refund failed: {str(e)}", 'cashfree')
    
    def handle_webhook(self, payload: Dict[str, Any], signature: str = None) -> Dict[str, Any]:
        """Handle Cashfree webhook"""
        try:
            # Verify webhook signature
            if signature:
                computed_signature = base64.b64encode(
                    hmac.new(
                        self.secret_key.encode('utf-8'),
                        str(payload).encode('utf-8'),
                        hashlib.sha256
                    ).digest()
                ).decode()
                
                if not hmac.compare_digest(signature, computed_signature):
                    raise PaymentGatewayError("Invalid webhook signature", 'cashfree')
            
            event_type = payload.get('type')
            data = payload.get('data', {})
            order = data.get('order', {})
            
            return {
                'success': True,
                'event_type': event_type,
                'payment_id': order.get('cf_order_id'),
                'order_id': order.get('order_id'),
                'amount': order.get('order_amount', 0),
                'status': order.get('order_status'),
                'gateway_data': payload
            }
        except Exception as e:
            raise PaymentGatewayError(f"Cashfree webhook handling failed: {str(e)}", 'cashfree')
