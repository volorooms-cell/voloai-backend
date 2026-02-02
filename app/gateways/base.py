"""Base payment gateway interface.

All gateway adapters must implement this interface.
Business logic should NOT live in adapters - only gateway communication.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from enum import Enum


class GatewayType(str, Enum):
    """Supported payment gateways."""

    PAYFAST = "payfast"
    STRIPE = "stripe"
    JAZZCASH = "jazzcash"
    EASYPAISA = "easypaisa"
    MANUAL = "manual"


@dataclass
class PaymentResult:
    """Result of a payment operation."""

    success: bool
    transaction_id: str | None = None
    error_message: str | None = None
    raw_response: dict | None = None


@dataclass
class RefundResult:
    """Result of a refund operation."""

    success: bool
    refund_id: str | None = None
    error_message: str | None = None
    raw_response: dict | None = None


class PaymentGateway(ABC):
    """Abstract base class for payment gateways."""

    @property
    @abstractmethod
    def gateway_type(self) -> GatewayType:
        """Return the gateway type."""
        pass

    @abstractmethod
    async def create_payment(
        self,
        amount: int,
        currency: str,
        reference_id: str,
        description: str,
        metadata: dict | None = None,
    ) -> PaymentResult:
        """Create a payment intent/request.

        Args:
            amount: Amount in smallest currency unit (paisa)
            currency: Currency code (PKR)
            reference_id: Internal reference (payment_id)
            description: Payment description
            metadata: Additional metadata

        Returns:
            PaymentResult with transaction details
        """
        pass

    @abstractmethod
    async def verify_payment(
        self,
        transaction_id: str,
    ) -> PaymentResult:
        """Verify a payment status.

        Args:
            transaction_id: Gateway transaction ID

        Returns:
            PaymentResult with current status
        """
        pass

    @abstractmethod
    async def process_refund(
        self,
        transaction_id: str,
        amount: int,
        reason: str,
    ) -> RefundResult:
        """Process a refund.

        Args:
            transaction_id: Original payment transaction ID
            amount: Refund amount in smallest currency unit
            reason: Refund reason

        Returns:
            RefundResult with refund details
        """
        pass

    @abstractmethod
    def verify_webhook(
        self,
        payload: bytes,
        signature: str,
    ) -> dict | None:
        """Verify webhook signature and parse payload.

        Args:
            payload: Raw request body
            signature: Webhook signature header

        Returns:
            Parsed event dict if valid, None if invalid
        """
        pass
