"""Payment gateway service.

Routes payment operations to the appropriate gateway adapter.
No business logic here - only gateway coordination.
"""

from app.config import settings
from app.gateways.base import (
    GatewayType,
    PaymentGateway,
    PaymentResult,
    RefundResult,
)
from app.gateways.manual import ManualGateway
from app.gateways.payfast import PayFastGateway
from app.gateways.stripe_gateway import StripeGateway


def _is_production() -> bool:
    """Check if running in production environment."""
    return settings.environment == "production"


def _assert_production_for_real_gateway(gateway_type: GatewayType) -> None:
    """Block real gateway operations in non-production environments.

    Raises:
        RuntimeError: If attempting real gateway operation outside production
    """
    if gateway_type in (GatewayType.STRIPE, GatewayType.PAYFAST, GatewayType.JAZZCASH, GatewayType.EASYPAISA):
        if not _is_production():
            # Allow if sandbox mode is explicitly enabled for PayFast
            if gateway_type == GatewayType.PAYFAST and settings.payfast_sandbox:
                return
            # Block real gateway operations in non-production
            if gateway_type != GatewayType.PAYFAST:
                raise RuntimeError(
                    f"Cannot execute real {gateway_type.value} gateway operations "
                    f"in {settings.environment} environment. Set ENV=production or use sandbox mode."
                )


class GatewayService:
    """Service for managing payment gateway operations."""

    def __init__(self):
        self._gateways: dict[GatewayType, PaymentGateway] = {}

    def _get_gateway(self, gateway_type: str | GatewayType) -> PaymentGateway:
        """Get or create gateway instance."""
        if isinstance(gateway_type, str):
            try:
                gateway_type = GatewayType(gateway_type)
            except ValueError:
                gateway_type = GatewayType.MANUAL

        if gateway_type not in self._gateways:
            if gateway_type == GatewayType.STRIPE:
                self._gateways[gateway_type] = StripeGateway()
            elif gateway_type == GatewayType.PAYFAST:
                self._gateways[gateway_type] = PayFastGateway()
            else:
                self._gateways[gateway_type] = ManualGateway()

        return self._gateways[gateway_type]

    async def create_payment(
        self,
        gateway_type: str | GatewayType,
        amount: int,
        currency: str,
        reference_id: str,
        description: str,
        metadata: dict | None = None,
    ) -> PaymentResult:
        """Create payment via specified gateway."""
        gateway = self._get_gateway(gateway_type)
        # Environment safety: block real gateway in non-production
        _assert_production_for_real_gateway(gateway.gateway_type)
        return await gateway.create_payment(
            amount=amount,
            currency=currency,
            reference_id=reference_id,
            description=description,
            metadata=metadata,
        )

    async def verify_payment(
        self,
        gateway_type: str | GatewayType,
        transaction_id: str,
    ) -> PaymentResult:
        """Verify payment status via gateway."""
        gateway = self._get_gateway(gateway_type)
        return await gateway.verify_payment(transaction_id)

    async def process_refund(
        self,
        gateway_type: str | GatewayType,
        transaction_id: str,
        amount: int,
        reason: str,
    ) -> RefundResult:
        """Process refund via gateway."""
        gateway = self._get_gateway(gateway_type)
        # Environment safety: block real gateway in non-production
        _assert_production_for_real_gateway(gateway.gateway_type)
        return await gateway.process_refund(
            transaction_id=transaction_id,
            amount=amount,
            reason=reason,
        )

    def verify_webhook(
        self,
        gateway_type: str | GatewayType,
        payload: bytes,
        signature: str,
    ) -> dict | None:
        """Verify webhook from gateway."""
        gateway = self._get_gateway(gateway_type)
        return gateway.verify_webhook(payload, signature)


# Singleton instance
gateway_service = GatewayService()
