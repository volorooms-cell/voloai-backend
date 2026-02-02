"""Manual payment gateway adapter for bank transfers."""

from app.gateways.base import (
    GatewayType,
    PaymentGateway,
    PaymentResult,
    RefundResult,
)


class ManualGateway(PaymentGateway):
    """Manual payment gateway for bank transfers.

    All operations return success but require manual admin verification.
    """

    @property
    def gateway_type(self) -> GatewayType:
        return GatewayType.MANUAL

    async def create_payment(
        self,
        amount: int,
        currency: str,
        reference_id: str,
        description: str,
        metadata: dict | None = None,
    ) -> PaymentResult:
        """Create manual payment request (always succeeds)."""
        return PaymentResult(
            success=True,
            transaction_id=f"manual_{reference_id}",
            raw_response={
                "type": "bank_transfer",
                "status": "pending_verification",
                "instructions": "Please transfer to VOLO bank account and upload receipt",
            },
        )

    async def verify_payment(
        self,
        transaction_id: str,
    ) -> PaymentResult:
        """Verify manual payment (requires admin verification)."""
        return PaymentResult(
            success=False,
            transaction_id=transaction_id,
            error_message="Manual verification required by admin",
        )

    async def process_refund(
        self,
        transaction_id: str,
        amount: int,
        reason: str,
    ) -> RefundResult:
        """Process manual refund (requires admin action)."""
        return RefundResult(
            success=True,
            refund_id=f"refund_{transaction_id}",
            raw_response={
                "type": "manual_refund",
                "status": "pending",
                "note": "Admin must process refund manually via bank transfer",
                "amount": amount,
                "reason": reason,
            },
        )

    def verify_webhook(
        self,
        payload: bytes,
        signature: str,
    ) -> dict | None:
        """Manual gateway doesn't have webhooks."""
        return None
