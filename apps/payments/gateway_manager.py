from typing import Dict, Any, Optional
from decimal import Decimal
from django.conf import settings
from .gateways.base import PaymentGatewayBase, PaymentGatewayError
from .gateways.razorpay_gateway import RazorpayGateway
from .gateways.paypal_gateway import PayPalGateway
from .gateways.cashfree_gateway import CashfreeGateway
from .gateways.payu_gateway import PayUGateway
from .gateways.stripe_gateway import StripeGateway
import logging

logger = logging.getLogger(__name__)


class PaymentGatewayManager:
    """Manager class for handling multiple payment gateways"""
    
    GATEWAY_CLASSES = {
        'razorpay': RazorpayGateway,
        'paypal': PayPalGateway,
        'cashfree': CashfreeGateway,
        'payu': PayUGateway,
        'stripe': StripeGateway,
    }
    
    def __init__(self):
        self.gateways = {}
        self._initialized = False
    
    def _ensure_initialized(self):
        """Lazy initialization - only initialize when first accessed"""
        if not self._initialized:
            logger.info("🔄 Performing lazy initialization of payment gateways...")
            self._initialize_gateways()
            self._initialized = True
    
    def _initialize_gateways(self):
        """Initialize all configured payment gateways from database"""
        try:
            # Check if Django is ready
            import django
            if not django.apps.apps.ready:
                logger.warning("⚠️ Django apps not ready, using fallback configuration")
                self._initialize_from_settings()
                return
            
            # Import inside method to avoid circular imports
            from .models import PaymentGateway
            
            # Get active gateways from database (is_active = True)
            active_gateways = PaymentGateway.objects.filter(is_active=True)
            
            logger.info(f"🔧 Initializing payment gateways from database...")
            logger.info(f"   Found {active_gateways.count()} active gateways")
            
            for gateway_model in active_gateways:
                gateway_name = gateway_model.gateway_id
                
                if gateway_name in self.GATEWAY_CLASSES:
                    try:
                        # Build config from database model
                        config = {
                            'enabled': gateway_model.is_active,
                            'sandbox': gateway_model.is_test_mode,
                            **gateway_model.configuration
                        }
                        
                        logger.info(f"   🔧 Configuring {gateway_model.display_name}...")
                        logger.debug(f"      Config keys: {list(config.keys())}")
                        
                        gateway_class = self.GATEWAY_CLASSES[gateway_name]
                        gateway_instance = gateway_class(config)
                        
                        if gateway_instance.validate_config():
                            self.gateways[gateway_name] = gateway_instance
                            logger.info(f"   ✅ {gateway_model.display_name} initialized successfully")
                        else:
                            logger.warning(f"   ⚠️ Invalid configuration for {gateway_model.display_name}")
                            logger.warning(f"      Required fields: {gateway_instance.get_required_config_fields()}")
                            
                    except Exception as e:
                        logger.error(f"   ❌ Error initializing {gateway_model.display_name}: {str(e)}", exc_info=True)
                else:
                    logger.warning(f"   ⚠️ Gateway class not found for: {gateway_name}")
            
            logger.info(f"✅ Payment gateways initialized: {list(self.gateways.keys())}")
            
            if not self.gateways:
                logger.warning("⚠️ No gateways were initialized! Trying fallback...")
                self._initialize_from_settings()
            
        except Exception as e:
            logger.error(f"❌ Failed to initialize gateways from database: {str(e)}", exc_info=True)
            logger.info("   Falling back to settings.py configuration...")
            self._initialize_from_settings()
    
    def _initialize_from_settings(self):
        """Fallback: Initialize from settings.py"""
        gateway_configs = getattr(settings, 'PAYMENT_GATEWAYS', {})
        
        logger.info(f"🔧 Initializing from settings.py...")
        logger.info(f"   Found {len(gateway_configs)} gateway configs in settings")
        
        for gateway_name, config in gateway_configs.items():
            if gateway_name in self.GATEWAY_CLASSES and config.get('enabled', False):
                try:
                    gateway_class = self.GATEWAY_CLASSES[gateway_name]
                    gateway_instance = gateway_class(config)
                    
                    if gateway_instance.validate_config():
                        self.gateways[gateway_name] = gateway_instance
                        logger.info(f"   ✅ {gateway_name} initialized from settings")
                    else:
                        logger.warning(f"   ⚠️ Invalid configuration for {gateway_name}")
                except Exception as e:
                    logger.error(f"   ❌ Error initializing {gateway_name}: {str(e)}", exc_info=True)
    
    def get_gateway(self, gateway_name: str) -> Optional[PaymentGatewayBase]:
        """Get a specific payment gateway instance"""
        self._ensure_initialized()  # ✅ Lazy load on first access
        
        gateway = self.gateways.get(gateway_name)
        if gateway:
            logger.debug(f"✅ Gateway found: {gateway_name}")
        else:
            logger.warning(f"⚠️ Gateway not found: {gateway_name}")
            logger.warning(f"   Available gateways: {list(self.gateways.keys())}")
            logger.warning(f"   Initialized: {self._initialized}")
        return gateway
    
    def get_available_gateways(self) -> Dict[str, PaymentGatewayBase]:
        """Get all available payment gateways"""
        self._ensure_initialized()  # ✅ Lazy load on first access
        return self.gateways.copy()
    
    def create_order(self, gateway_name: str, amount: Decimal, currency: str, order_data: Dict[str, Any]) -> Dict[str, Any]:
        """Create order using specified gateway"""
        gateway = self.get_gateway(gateway_name)
        if not gateway:
            raise PaymentGatewayError(f"Gateway '{gateway_name}' not available")
        
        return gateway.create_order(amount, currency, order_data)
    
    def verify_payment(self, gateway_name: str, payment_data: Dict[str, Any]) -> Dict[str, Any]:
        """Verify payment using specified gateway"""
        gateway = self.get_gateway(gateway_name)
        if not gateway:
            raise PaymentGatewayError(f"Gateway '{gateway_name}' not available")
        
        return gateway.verify_payment(payment_data)
    
    def process_refund(self, gateway_name: str, payment_id: str, amount: Decimal, reason: str = None) -> Dict[str, Any]:
        """Process refund using specified gateway"""
        gateway = self.get_gateway(gateway_name)
        if not gateway:
            raise PaymentGatewayError(f"Gateway '{gateway_name}' not available")
        
        return gateway.process_refund(payment_id, amount, reason)
    
    def handle_webhook(self, gateway_name: str, payload: Dict[str, Any], signature: str = None) -> Dict[str, Any]:
        """Handle webhook using specified gateway"""
        gateway = self.get_gateway(gateway_name)
        if not gateway:
            raise PaymentGatewayError(f"Gateway '{gateway_name}' not available")
        
        return gateway.handle_webhook(payload, signature)
    
    def get_gateway_info(self) -> Dict[str, Dict[str, Any]]:
        """Get information about all available gateways"""
        self._ensure_initialized()  # ✅ Lazy load on first access
        info = {}
        for name, gateway in self.gateways.items():
            info[name] = {
                'name': name,
                'supported_currencies': gateway.get_supported_currencies(),
                'required_fields': gateway.get_required_config_fields()
            }
        return info


# Global instance
payment_gateway_manager = PaymentGatewayManager()
