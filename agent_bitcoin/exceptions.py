class AgentBitcoinError(Exception):
    """Base exception for the agent-bitcoin package"""
    pass


class LNDException(AgentBitcoinError):
    """Raised when LND gRPC calls fail"""
    pass


class InvoiceCreationError(AgentBitcoinError):
    """Raised when creating an invoice fails"""
    pass


class PaymentError(AgentBitcoinError):
    """Raised when a Lightning payment fails"""
    pass


class MacaroonError(AgentBitcoinError):
    """Raised when there is a problem loading or using the macaroon"""
    pass


class InsufficientBalanceError(AgentBitcoinError):
    """Raised when wallet balance is insufficient"""
    pass


class NoRouteError(AgentBitcoinError):
    """Raised when no route can be found for a payment"""
    pass


class ConfigurationError(AgentBitcoinError):
    """Raised for missing or invalid configuration"""
    pass