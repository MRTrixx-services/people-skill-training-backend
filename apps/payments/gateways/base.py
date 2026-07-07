from abc import ABC, abstractmethod
from typing import Dict, Any, Optional
from decimal import Decimal


class PaymentGatewayBase(ABC):
    """Base class for all payment gateways"""
    
    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.gateway_name = self.__class__.__name__.lower().replace('gateway', '')
    
    @abstractmethod
    def create_order(self, amount: Decimal, currency: str, order_data: Dict[str, Any]) -> Dict[str, Any]:
        """Create a payment order"""
        pass
    
    @abstractmethod
    def verify_payment(self, payment_data: Dict[str, Any]) -> Dict[str, Any]:
        """Verify payment completion"""
        pass
    
    @abstractmethod
    def process_refund(self, payment_id: str, amount: Decimal, reason: str = None) -> Dict[str, Any]:
        """Process a refund"""
        pass
    
    @abstractmethod
    def handle_webhook(self, payload: Dict[str, Any], signature: str = None) -> Dict[str, Any]:
        """Handle webhook notifications"""
        pass
    
    def get_supported_currencies(self) -> list:
        """Get list of supported currencies"""
        return ['USD', 'INR', 'EUR', 'GBP']
    
    def validate_config(self) -> bool:
        """Validate gateway configuration"""
        required_fields = self.get_required_config_fields()
        return all(field in self.config for field in required_fields)
    
    @abstractmethod
    def get_required_config_fields(self) -> list:
        """Get required configuration fields"""
        pass


class PaymentGatewayError(Exception):
    """Base exception for payment gateway errors"""
    
    def __init__(self, message: str, gateway: str = None, error_code: str = None):
        self.message = message
        self.gateway = gateway
        self.error_code = error_code
        super().__init__(self.message)


class PaymentVerificationError(PaymentGatewayError):
    """Exception for payment verification failures"""
    pass


class RefundError(PaymentGatewayError):
    """Exception for refund processing failures"""
    pass
