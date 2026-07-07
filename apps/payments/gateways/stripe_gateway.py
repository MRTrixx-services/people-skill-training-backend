# apps/payments/gateways/stripe_gateway.py
import logging
from decimal import Decimal
from typing import Dict, Any
from django.conf import settings

try:
    import stripe
    STRIPE_AVAILABLE = True
except ImportError:
    STRIPE_AVAILABLE = False
    stripe = None

from .base import PaymentGatewayBase, PaymentGatewayError, PaymentVerificationError, RefundError

logger = logging.getLogger(__name__)

class StripeGateway(PaymentGatewayBase):
    """Stripe payment gateway implementation - PayPal-style flow"""
    
    def __init__(self, config: Dict[str, Any]):
        super().__init__(config)
        
        if not STRIPE_AVAILABLE:
            logger.error("❌ Stripe library not available. Install with: pip install stripe")
            raise ImportError("Stripe library is not installed")
        
        # Get keys from config (matches PayPal pattern)
        self.secret_key = config.get('secret_key', getattr(settings, 'STRIPE_SECRET_KEY', None))
        self.publishable_key = config.get('publishable_key', getattr(settings, 'STRIPE_PUBLISHABLE_KEY', None))
        self.webhook_secret = config.get('webhook_secret', getattr(settings, 'STRIPE_WEBHOOK_SECRET', None))
        
        # ✅ FIX: Use is_test_mode from config (NOT the key prefix!)
        # This ensures we respect the Django admin setting
        self.sandbox = config.get('is_test_mode', getattr(settings, 'STRIPE_SANDBOX', True))
        
        # Set Stripe API key
        if self.secret_key and stripe:
            stripe.api_key = self.secret_key
        
        logger.info(f"🔧 Stripe Gateway initialized:")
        logger.info(f"   Mode: {'TEST' if self.sandbox else 'LIVE'}")
        logger.info(f"   Secret Key: {self.secret_key[:20] if self.secret_key else 'None'}...")
        logger.info(f"   Publishable Key: {self.publishable_key[:20] if self.publishable_key else 'None'}...")
    
    def validate_config(self) -> bool:
        """Validate Stripe configuration"""
        if not STRIPE_AVAILABLE:
            logger.error("❌ Stripe library not installed")
            return False
            
        is_valid = bool(self.secret_key and self.publishable_key)
        if not is_valid:
            logger.error("❌ Stripe configuration is incomplete:")
            logger.error(f"   Secret Key present: {bool(self.secret_key)}")
            logger.error(f"   Publishable Key present: {bool(self.publishable_key)}")
        return is_valid
    
    def get_required_config_fields(self) -> list:
        return ['secret_key', 'publishable_key']
    
    def get_supported_currencies(self) -> list:
        """Get list of supported currencies"""
        return ['USD', 'EUR', 'GBP', 'CAD', 'AUD', 'JPY', 'INR', 'CHF', 'SGD']
    
    def get_client_config(self) -> Dict[str, Any]:
        """Get configuration for frontend Stripe.js (matches PayPal pattern)"""
        return {
            'publishable_key': self.publishable_key,
            'mode': 'test' if self.sandbox else 'live',
            'currency': 'USD'
        }
    
    def create_order(self, amount: Decimal, currency: str, order_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Create Stripe PaymentIntent (similar to PayPal order creation)
        Frontend will handle the payment confirmation
        """
        if not STRIPE_AVAILABLE or not stripe:
            raise PaymentGatewayError("Stripe library is not available", 'stripe')

        try:
            transaction_id = order_data.get('transaction_id')
            
            logger.info(f"📦 Creating Stripe PaymentIntent: {transaction_id}")
            logger.info(f"   Amount: {currency} {amount}")
            logger.info(f"   Mode: {'TEST' if self.sandbox else 'LIVE'}")

            # Convert Decimal to cents (Stripe uses smallest currency unit)
            amount_cents = int(amount * 100)

            # Prepare PaymentIntent parameters
            intent_params = {
                'amount': amount_cents,
                'currency': currency.lower(),
                'automatic_payment_methods': {
                    'enabled': True,
                },
                'metadata': {
                    'transaction_id': transaction_id,
                    'user_id': str(order_data.get('user_id')),
                    'user_email': order_data.get('user_email'),
                    'platform_id': order_data.get('platform_id', 'default')
                },
                'description': f"Payment for {transaction_id}",
                'receipt_email': order_data.get('user_email'),
            }

            # Add billing/shipping info if available
            billing_info = order_data.get('billing_info', {})
            if billing_info:
                customer_name = order_data.get('user_name') or \
                    f"{billing_info.get('firstName', '')} {billing_info.get('lastName', '')}".strip() or "Customer"

                shipping_address = {
                    'line1': billing_info.get('billingAddress') or 'Address not provided',
                    'city': billing_info.get('city') or 'Unknown',
                    'state': billing_info.get('state') or 'Unknown',
                    'postal_code': billing_info.get('zipCode') or '000000',
                    'country': billing_info.get('country') or 'US',
                }

                intent_params['shipping'] = {
                    'name': customer_name,
                    'address': shipping_address,
                }
                
                logger.info(f"📦 Added billing info: {customer_name}, {shipping_address['country']}")

            # Create PaymentIntent
            intent = stripe.PaymentIntent.create(**intent_params)

            logger.info(f"✅ Stripe PaymentIntent created successfully:")
            logger.info(f"   Payment Intent ID: {intent.id}")
            logger.info(f"   Client Secret: {intent.client_secret[:20]}...")
            logger.info(f"   Status: {intent.status}")

            # ✅ Return response matching PayPal structure
            return {
                'success': True,
                'order_id': f'STRIPE_{transaction_id}',  # Keep your transaction ID format
                'payment_intent_id': intent.id,  # Actual Stripe PaymentIntent ID
                'client_secret': intent.client_secret,  # ✅ CRITICAL for frontend
                'amount': float(amount),
                'currency': currency,
                'transaction_id': transaction_id,
                'gateway_data': {
                    'id': intent.id,
                    'status': intent.status,
                    'amount': intent.amount,
                    'currency': intent.currency,
                    'client_secret': intent.client_secret  # Store for resume
                }
            }

        except stripe.error.AuthenticationError as e:
            logger.error(f"❌ Stripe authentication failed: {str(e)}")
            logger.error(f"   Mode: {'TEST' if self.sandbox else 'LIVE'}")
            logger.error(f"   Secret Key: {self.secret_key[:20]}...")
            raise PaymentGatewayError(
                f"Stripe {'test' if self.sandbox else 'live'} credentials are invalid. "
                f"Please verify your API keys in Django admin.",
                'stripe'
            )
        
        except stripe.error.StripeError as e:
            logger.error(f"❌ Stripe API error: {str(e)}")
            raise PaymentGatewayError(f"Stripe error: {str(e)}", 'stripe')
        
        except Exception as e:
            logger.error(f"❌ Unexpected error creating Stripe PaymentIntent: {str(e)}", exc_info=True)
            raise PaymentGatewayError(f"Failed to create Stripe payment: {str(e)}", 'stripe')
    
    def verify_payment(self, payment_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Verify Stripe payment - Trust frontend confirmation (like PayPal)
        """
        if not STRIPE_AVAILABLE or not stripe:
            raise PaymentVerificationError("Stripe library is not available", 'stripe')
        
        try:
            # ✅ Check if frontend already sent payment_intent details (like PayPal capture_details)
            payment_intent_data = payment_data.get('payment_intent_details', {})
            
            if payment_intent_data and payment_intent_data.get('status') == 'succeeded':
                # ✅ Payment was already confirmed on frontend - trust it
                payment_intent_id = payment_intent_data['id']
                amount = payment_intent_data['amount'] / 100  # Convert cents to dollars
                
                logger.info(f"✅ Stripe payment verified from frontend confirmation: {payment_intent_id}")
                logger.info(f"   Amount: {amount} {payment_intent_data.get('currency', 'USD').upper()}")
                logger.info(f"   Status: {payment_intent_data['status']}")
                
                return {
                    'success': True,
                    'verified': True,
                    'payment_id': payment_intent_id,
                    'order_id': f"STRIPE_{payment_intent_id}",
                    'amount': float(amount),
                    'currency': payment_intent_data.get('currency', 'USD').upper(),
                    'status': 'completed',
                    'gateway_data': payment_intent_data
                }
            
            # ✅ Fallback: Verify with Stripe API if needed
            payment_intent_id = (
                payment_data.get('payment_intent_id') or 
                payment_data.get('paymentIntentId') or 
                payment_data.get('id')
            )
            
            if not payment_intent_id:
                raise PaymentVerificationError("Stripe payment_intent_id is required", 'stripe')
            
            logger.info(f"🔍 Verifying Stripe PaymentIntent with API: {payment_intent_id}")
            
            # Retrieve PaymentIntent from Stripe
            intent = stripe.PaymentIntent.retrieve(payment_intent_id)
            
            if intent.status == 'succeeded':
                amount = intent.amount / 100  # Convert cents to dollars
                
                logger.info(f"✅ Stripe payment verified via API: {intent.id}")
                logger.info(f"   Amount: {amount} {intent.currency.upper()}")
                logger.info(f"   Status: {intent.status}")
                
                return {
                    'success': True,
                    'verified': True,
                    'payment_id': intent.id,
                    'order_id': f"STRIPE_{intent.id}",
                    'amount': float(amount),
                    'currency': intent.currency.upper(),
                    'status': 'completed',
                    'gateway_data': {
                        'id': intent.id,
                        'status': intent.status,
                        'amount': intent.amount,
                        'currency': intent.currency,
                        'payment_method': intent.payment_method
                    }
                }
            
            else:
                raise PaymentVerificationError(
                    f"Payment status: {intent.status}",
                    'stripe'
                )
                
        except stripe.error.StripeError as e:
            logger.error(f"❌ Stripe verification error: {str(e)}", exc_info=True)
            raise PaymentVerificationError(f"Stripe verification failed: {str(e)}", 'stripe')
        
        except PaymentVerificationError:
            raise
        
        except Exception as e:
            logger.error(f"❌ Stripe verification failed: {str(e)}", exc_info=True)
            raise PaymentVerificationError(f"Stripe verification failed: {str(e)}", 'stripe')
    
    def process_refund(self, payment_id: str, amount: Decimal, reason: str = None) -> Dict[str, Any]:
        """Process Stripe refund"""
        if not STRIPE_AVAILABLE or not stripe:
            raise RefundError("Stripe library is not available", 'stripe')
        
        try:
            amount_cents = int(amount * 100)  # Convert to cents
            
            refund_data = {
                'payment_intent': payment_id,
                'amount': amount_cents
            }
            
            if reason:
                refund_data['reason'] = 'requested_by_customer'
                refund_data['metadata'] = {'reason': reason}
            
            logger.info(f"♻️ Processing Stripe refund: {payment_id} - ${amount}")
            
            refund = stripe.Refund.create(**refund_data)
            
            logger.info(f"✅ Stripe refund completed: {refund.id}")
            logger.info(f"   Status: {refund.status}")
            
            return {
                'success': True,
                'refund_id': refund.id,
                'amount': float(refund.amount / 100),
                'status': refund.status,
                'gateway_data': {
                    'id': refund.id,
                    'status': refund.status,
                    'amount': refund.amount,
                    'currency': refund.currency
                }
            }
            
        except stripe.error.StripeError as e:
            logger.error(f"❌ Stripe refund error: {str(e)}")
            raise RefundError(f"Stripe refund failed: {str(e)}", 'stripe')
        
        except Exception as e:
            logger.error(f"❌ Unexpected refund error: {str(e)}")
            raise RefundError(f"Stripe refund failed: {str(e)}", 'stripe')
    
    def handle_webhook(self, payload: Dict[str, Any], signature: str = None) -> Dict[str, Any]:
        """Handle Stripe webhook"""
        if not STRIPE_AVAILABLE or not stripe:
            raise PaymentGatewayError("Stripe library is not available", 'stripe')
        
        try:
            # Verify webhook signature if webhook secret is configured
            if self.webhook_secret and signature:
                logger.info("🔐 Verifying Stripe webhook signature...")
                event = stripe.Webhook.construct_event(
                    payload, signature, self.webhook_secret
                )
            else:
                logger.warning("⚠️ Stripe webhook signature verification skipped (no secret configured)")
                event = payload
            
            event_type = event['type']
            event_data = event['data']['object']
            
            logger.info(f"📨 Stripe webhook received: {event_type}")
            
            return {
                'success': True,
                'event_type': event_type,
                'payment_id': event_data.get('id'),
                'amount': event_data.get('amount', 0) / 100 if event_data.get('amount') else 0,
                'status': event_data.get('status'),
                'gateway_data': event
            }
            
        except stripe.error.SignatureVerificationError as e:
            logger.error(f"❌ Stripe webhook signature verification failed: {str(e)}")
            raise PaymentGatewayError(f"Invalid webhook signature: {str(e)}", 'stripe')
        
        except Exception as e:
            logger.error(f"❌ Stripe webhook handling failed: {str(e)}")
            raise PaymentGatewayError(f"Stripe webhook handling failed: {str(e)}", 'stripe')
