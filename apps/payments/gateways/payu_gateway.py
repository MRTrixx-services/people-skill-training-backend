import requests
import hashlib
from decimal import Decimal
from typing import Dict, Any
from django.conf import settings
from .base import PaymentGatewayBase, PaymentGatewayError, PaymentVerificationError, RefundError


class PayUGateway(PaymentGatewayBase):
    """PayU payment gateway implementation"""
    
    def __init__(self, config: Dict[str, Any]):
        super().__init__(config)
        self.merchant_key = config.get('merchant_key', settings.PAYU_MERCHANT_KEY)
        self.merchant_salt = config.get('merchant_salt', settings.PAYU_MERCHANT_SALT)
        self.sandbox = config.get('sandbox', settings.PAYU_SANDBOX)
        self.base_url = 'https://sandboxsecure.payu.in' if self.sandbox else 'https://secure.payu.in'
    
    def get_required_config_fields(self) -> list:
        return ['merchant_key', 'merchant_salt']
    
    def generate_hash(self, data: str) -> str:
        """Generate PayU hash"""
        return hashlib.sha512((data + self.merchant_salt).encode('utf-8')).hexdigest()
    
    def create_order(self, amount: Decimal, currency: str, order_data: Dict[str, Any]) -> Dict[str, Any]:
        """Create PayU order"""
        try:
            txnid = order_data.get('receipt', f"order_{order_data.get('user_id')}_{order_data.get('webinar_id')}")
            
            # PayU hash calculation: key|txnid|amount|productinfo|firstname|email|||||||||||salt
            hash_string = f"{self.merchant_key}|{txnid}|{amount}|{order_data.get('description', 'Webinar Purchase')}|{order_data.get('customer_name', 'Customer')}|{order_data.get('customer_email', 'customer@example.com')}|||||||||||"
            hash_value = self.generate_hash(hash_string)
            
            payment_data = {
                'key': self.merchant_key,
                'txnid': txnid,
                'amount': str(amount),
                'productinfo': order_data.get('description', 'Webinar Purchase'),
                'firstname': order_data.get('customer_name', 'Customer'),
                'email': order_data.get('customer_email', 'customer@example.com'),
                'phone': order_data.get('customer_phone', '9999999999'),
                'surl': order_data.get('return_url', 'https://example.com/success'),
                'furl': order_data.get('cancel_url', 'https://example.com/failure'),
                'hash': hash_value,
                'service_provider': 'payu_paisa'
            }
            
            return {
                'success': True,
                'order_id': txnid,
                'amount': amount,
                'currency': currency,
                'payment_url': f"{self.base_url}/_payment",
                'payment_data': payment_data,
                'gateway_data': payment_data
            }
        except Exception as e:
            raise PaymentGatewayError(f"Failed to create PayU order: {str(e)}", 'payu')
    
    def verify_payment(self, payment_data: Dict[str, Any]) -> Dict[str, Any]:
        """Verify PayU payment"""
        try:
            # PayU sends response via POST to success/failure URL
            # This method would typically be called from the webhook/callback handler
            
            txnid = payment_data.get('txnid')
            amount = payment_data.get('amount')
            productinfo = payment_data.get('productinfo')
            firstname = payment_data.get('firstname')
            email = payment_data.get('email')
            status = payment_data.get('status')
            received_hash = payment_data.get('hash')
            
            # Verify hash for response: salt|status||||||||||email|firstname|productinfo|amount|txnid|key
            hash_string = f"{status}||||||||||{email}|{firstname}|{productinfo}|{amount}|{txnid}|{self.merchant_key}"
            expected_hash = self.generate_hash(hash_string)
            
            if received_hash != expected_hash:
                raise PaymentVerificationError("Invalid hash in PayU response", 'payu')
            
            if status == 'success':
                return {
                    'success': True,
                    'payment_id': payment_data.get('mihpayid'),
                    'order_id': txnid,
                    'amount': float(amount),
                    'currency': 'INR',  # PayU primarily supports INR
                    'status': status,
                    'gateway_data': payment_data
                }
            else:
                raise PaymentVerificationError(f"PayU payment failed: {status}", 'payu')
                
        except Exception as e:
            raise PaymentVerificationError(f"PayU payment verification failed: {str(e)}", 'payu')
    
    def process_refund(self, payment_id: str, amount: Decimal, reason: str = None) -> Dict[str, Any]:
        """Process PayU refund"""
        try:
            # PayU refund API endpoint
            url = f"{self.base_url}/merchant/postservice?form=2"
            
            refund_data = {
                'key': self.merchant_key,
                'command': 'cancel_refund_transaction',
                'var1': payment_id,
                'var2': str(amount),
                'var3': reason or 'Refund requested',
                'hash': self.generate_hash(f"{self.merchant_key}|cancel_refund_transaction|{payment_id}")
            }
            
            response = requests.post(url, data=refund_data)
            response.raise_for_status()
            
            # PayU returns response in a specific format, parse accordingly
            result = response.text
            
            return {
                'success': True,
                'refund_id': f"refund_{payment_id}",
                'amount': amount,
                'status': 'initiated',
                'gateway_data': {'response': result}
            }
        except Exception as e:
            raise RefundError(f"PayU refund failed: {str(e)}", 'payu')
    
    def handle_webhook(self, payload: Dict[str, Any], signature: str = None) -> Dict[str, Any]:
        """Handle PayU webhook"""
        try:
            # PayU doesn't have traditional webhooks, but handles callbacks via success/failure URLs
            # This method processes the callback data
            
            return {
                'success': True,
                'event_type': 'payment_callback',
                'payment_id': payload.get('mihpayid'),
                'order_id': payload.get('txnid'),
                'amount': float(payload.get('amount', 0)),
                'status': payload.get('status'),
                'gateway_data': payload
            }
        except Exception as e:
            raise PaymentGatewayError(f"PayU webhook handling failed: {str(e)}", 'payu')
