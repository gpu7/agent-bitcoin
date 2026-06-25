class AgentBitcoinError(Exception):
    """Base exception for all Agent-Bitcoin SDK errors."""

    pass


class LightningConnectionError(AgentBitcoinError):
    """Raised when unable to connect to LND node."""

    pass


class InvoiceCreationError(AgentBitcoinError):
    """Raised when invoice creation fails."""

    pass


class PaymentError(AgentBitcoinError):
    """Raised when a payment fails."""

    def __init__(self, message: str, payment_hash: str = None, status: str = None):
        self.payment_hash = payment_hash
        self.status = status
        super().__init__(message)


class InsufficientBalanceError(PaymentError):
    """Raised when the payer doesn't have enough balance."""

    pass


class NoRouteError(PaymentError):
    """Raised when no route can be found to the recipient."""

    pass


class InvoiceExpiredError(AgentBitcoinError):
    """Raised when trying to pay an expired invoice."""

    pass


class MacaroonError(AgentBitcoinError):
    """Raised when there's an issue with the macaroon (auth)."""

    pass


class ValidationError(AgentBitcoinError):
    """Raised when input validation fails."""

    pass
