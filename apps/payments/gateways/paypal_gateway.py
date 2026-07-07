# apps/payments/gateways/paypal_gateway.py
import requests
import json
from decimal import Decimal
from typing import Dict, Any
from django.conf import settings
from .base import PaymentGatewayBase, PaymentGatewayError, PaymentVerificationError, RefundError
import logging


logger = logging.getLogger(__name__)


class PayPalGateway(PaymentGatewayBase):
    """PayPal payment gateway implementation"""
    
    def __init__(self, config: Dict[str, Any]):
        super().__init__(config)
        self.client_id = config.get('client_id', getattr(settings, 'PAYPAL_CLIENT_ID', None))
        self.client_secret = config.get('client_secret', getattr(settings, 'PAYPAL_CLIENT_SECRET', None))
        
        # ✅ FIX: Use is_test_mode from config (matches your admin field)
        self.sandbox = config.get('is_test_mode', getattr(settings, 'PAYPAL_SANDBOX', True))
        
        # ✅ This will now use correct API based on is_test_mode
        self.base_url = 'https://api.sandbox.paypal.com' if self.sandbox else 'https://api.paypal.com'
        self.access_token = None
        
        logger.info(f"🔧 PayPal Gateway initialized:")
        logger.info(f"   Mode: {'SANDBOX' if self.sandbox else 'LIVE'}")
        logger.info(f"   API URL: {self.base_url}")
    
    def validate_config(self) -> bool:
        """Validate PayPal configuration"""
        is_valid = bool(self.client_id and self.client_secret)
        if not is_valid:
            logger.error("❌ PayPal configuration is incomplete:")
            logger.error(f"   Client ID present: {bool(self.client_id)}")
            logger.error(f"   Client Secret present: {bool(self.client_secret)}")
        return is_valid
    
    def get_required_config_fields(self) -> list:
        """Get required configuration fields"""
        return ['client_id', 'client_secret']
    
    def get_supported_currencies(self) -> list:
        """Get list of supported currencies"""
        return ['USD', 'EUR', 'GBP', 'CAD', 'AUD', 'JPY', 'INR']
    
    def get_client_config(self) -> Dict[str, Any]:
        """Get configuration for frontend PayPal SDK"""
        return {
            'client_id': self.client_id,
            'mode': 'sandbox' if self.sandbox else 'live',
            'currency': 'USD',
            'intent': 'capture'
        }
    
    def get_access_token(self) -> str:
        """Get PayPal access token"""
        if self.access_token:
            return self.access_token
        
        try:
            url = f"{self.base_url}/v1/oauth2/token"
            headers = {
                'Accept': 'application/json',
                'Accept-Language': 'en_US',
            }
            data = 'grant_type=client_credentials'
            
            logger.info(f"🔑 Requesting PayPal access token...")
            logger.debug(f"   URL: {url}")
            logger.debug(f"   Mode: {'SANDBOX' if self.sandbox else 'LIVE'}")
            
            response = requests.post(
                url, 
                headers=headers, 
                data=data,
                auth=(self.client_id, self.client_secret),
                timeout=10
            )
            
            if response.status_code == 401:
                logger.error("❌ PayPal authentication failed (401 Unauthorized)")
                logger.error(f"   Mode: {'SANDBOX' if self.sandbox else 'LIVE'}")
                logger.error(f"   URL: {url}")
                logger.error(f"   Make sure you're using the correct credentials for this mode")
                
                raise PaymentGatewayError(
                    f"PayPal {'sandbox' if self.sandbox else 'live'} credentials are invalid. "
                    f"Please verify your Client ID and Secret in Django admin.",
                    'paypal'
                )
            
            response.raise_for_status()
            token_data = response.json()
            self.access_token = token_data['access_token']
            
            logger.info("✅ PayPal access token obtained successfully")
            return self.access_token
            
        except PaymentGatewayError:
            raise
            
        except Exception as e:
            logger.error(f"❌ Error getting PayPal access token: {str(e)}")
            raise PaymentGatewayError(f"PayPal authentication error: {str(e)}", 'paypal')
    
    def create_order(self, amount: Decimal, currency: str, order_data: Dict[str, Any]) -> Dict[str, Any]:
        """Create PayPal order (frontend integration)"""
        try:
            transaction_id = order_data.get('transaction_id')
            
            logger.info(f"📦 PayPal order prepared for frontend: {transaction_id}")
            logger.info(f"   Amount: {currency} {amount}")
            
            return {
                'success': True,
                'order_id': f'PAYPAL_{transaction_id}',
                'amount': float(amount),
                'currency': currency,
                'transaction_id': transaction_id,
                'client_id': self.client_id,
                'mode': 'sandbox' if self.sandbox else 'live'
            }
            
        except Exception as e:
            logger.error(f"❌ PayPal order preparation failed: {str(e)}")
            raise PaymentGatewayError(f"Failed to create PayPal order: {str(e)}", 'paypal')
    
    def verify_payment(self, payment_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Verify PayPal payment - Trust frontend capture if already completed
        """
        try:
            # ✅ Check if frontend already sent capture details
            capture_details = payment_data.get('capture_details', {})
            
            if capture_details and capture_details.get('status') == 'COMPLETED':
                # ✅ Payment was already captured on frontend - trust it
                capture = capture_details['purchase_units'][0]['payments']['captures'][0]
                order_id = capture_details['id']
                
                logger.info(f"✅ PayPal payment verified from frontend capture: {capture['id']}")
                logger.info(f"   Order ID: {order_id}")
                logger.info(f"   Amount: {capture['amount']['value']} {capture['amount']['currency_code']}")
                logger.info(f"   Status: {capture['status']}")
                
                return {
                    'success': True,
                    'verified': True,
                    'payment_id': capture['id'],
                    'order_id': order_id,
                    'amount': float(capture['amount']['value']),
                    'currency': capture['amount']['currency_code'],
                    'status': 'completed',
                    'gateway_data': capture_details
                }
            
            # ✅ Fallback: Verify with PayPal API if needed
            access_token = self.get_access_token()
            order_id = payment_data.get('order_id') or payment_data.get('orderID') or payment_data.get('paypal_order_id')
            
            if not order_id:
                raise PaymentVerificationError("PayPal order ID is required", 'paypal')
            
            url = f"{self.base_url}/v2/checkout/orders/{order_id}"
            headers = {
                'Content-Type': 'application/json',
                'Authorization': f'Bearer {access_token}',
            }
            
            logger.info(f"🔍 Verifying PayPal order with API: {order_id}")
            
            response = requests.get(url, headers=headers, timeout=10)
            response.raise_for_status()
            
            order_data = response.json()
            
            if order_data['status'] == 'COMPLETED':
                capture = order_data['purchase_units'][0]['payments']['captures'][0]
                
                logger.info(f"✅ PayPal payment verified via API: {capture['id']}")
                
                return {
                    'success': True,
                    'verified': True,
                    'payment_id': capture['id'],
                    'order_id': order_id,
                    'amount': float(capture['amount']['value']),
                    'currency': capture['amount']['currency_code'],
                    'status': 'completed',
                    'gateway_data': order_data
                }
            
            elif order_data['status'] == 'APPROVED':
                # Capture on backend
                capture_url = f"{self.base_url}/v2/checkout/orders/{order_id}/capture"
                capture_response = requests.post(capture_url, headers=headers, timeout=10)
                capture_response.raise_for_status()
                
                capture_data = capture_response.json()
                capture = capture_data['purchase_units'][0]['payments']['captures'][0]
                
                logger.info(f"✅ PayPal payment captured: {capture['id']}")
                
                return {
                    'success': True,
                    'verified': True,
                    'payment_id': capture['id'],
                    'order_id': order_id,
                    'amount': float(capture['amount']['value']),
                    'currency': capture['amount']['currency_code'],
                    'status': 'completed',
                    'gateway_data': capture_data
                }
            else:
                raise PaymentVerificationError(f"Payment status: {order_data['status']}", 'paypal')
                
        except PaymentGatewayError as e:
            raise PaymentVerificationError(str(e), 'paypal')
            
        except Exception as e:
            logger.error(f"❌ PayPal verification failed: {str(e)}", exc_info=True)
            raise PaymentVerificationError(f"PayPal verification failed: {str(e)}", 'paypal')

    def process_refund(self, payment_id: str, amount: Decimal, reason: str = None) -> Dict[str, Any]:
        """Process PayPal refund"""
        try:
            access_token = self.get_access_token()
            
            url = f"{self.base_url}/v2/payments/captures/{payment_id}/refund"
            headers = {
                'Content-Type': 'application/json',
                'Authorization': f'Bearer {access_token}',
            }
            
            payload = {
                'amount': {
                    'value': str(amount),
                    'currency_code': 'USD'
                }
            }
            
            if reason:
                payload['note_to_payer'] = reason
            
            logger.info(f"♻️ Processing PayPal refund: {payment_id} - ${amount}")
            
            response = requests.post(url, headers=headers, json=payload, timeout=10)
            response.raise_for_status()
            
            refund = response.json()
            
            logger.info(f"✅ PayPal refund completed: {refund['id']}")
            
            return {
                'success': True,
                'refund_id': refund['id'],
                'amount': float(refund['amount']['value']),
                'status': refund['status'],
                'gateway_data': refund
            }
            
        except Exception as e:
            logger.error(f"❌ PayPal refund failed: {str(e)}")
            raise RefundError(f"PayPal refund failed: {str(e)}", 'paypal')
    
    def handle_webhook(self, payload: Dict[str, Any], signature: str = None) -> Dict[str, Any]:
        """Handle PayPal webhook"""
        try:
            event_type = payload.get('event_type')
            resource = payload.get('resource', {})
            
            logger.info(f"📨 PayPal webhook received: {event_type}")
            
            return {
                'success': True,
                'event_type': event_type,
                'payment_id': resource.get('id'),
                'amount': float(resource.get('amount', {}).get('value', 0)),
                'status': resource.get('status'),
                'gateway_data': payload
            }
            
        except Exception as e:
            logger.error(f"❌ PayPal webhook handling failed: {str(e)}")
            raise PaymentGatewayError(f"PayPal webhook handling failed: {str(e)}", 'paypal')
