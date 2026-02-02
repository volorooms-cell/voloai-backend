"""Stripe payment gateway adapter."""

from app.config import settings
from app.gateways.base import (
    GatewayType,
    PaymentGateway,
    PaymentResult,
    RefundResult,
)


class StripeGateway(PaymentGateway):
    """Stripe payment gateway implementation."""

    def __init__(self):
        self.secret_key = settings.stripe_secret_key
        self.webhook_secret = settings.stripe_webhook_secret

    @property
    def gateway_type(self) -> GatewayType:
        return GatewayType.STRIPE

    async def create_payment(
        self,
        amount: int,
        currency: str,
        reference_id: str,
        description: str,
        metadata: dict | None = None,
    ) -> PaymentResult:
        """Create Stripe PaymentIntent."""
        if not self.secret_key:
            return PaymentResult(
                success=False,
                error_message="Stripe not configured",
            )

        try:
            import stripe

            stripe.api_key = self.secret_key

            intent = stripe.PaymentIntent.create(
                amount=amount,
                currency=currency.lower(),
                description=description,
                metadata={"reference_id": reference_id, **(metadata or {})},
            )

            return PaymentResult(
                success=True,
                transaction_id=intent.id,
                raw_response={
                    "client_secret": intent.client_secret,
                    "id": intent.id,
                },
            )

        except Exception as e:
            return PaymentResult(
                success=False,
                error_message=str(e),
            )

    async def verify_payment(
        self,
        transaction_id: str,
    ) -> PaymentResult:
        """Verify Stripe payment status."""
        if not self.secret_key:
            return PaymentResult(
                success=False,
                error_message="Stripe not configured",
            )

        try:
            import stripe

            stripe.api_key = self.secret_key

            intent = stripe.PaymentIntent.retrieve(transaction_id)

            return PaymentResult(
                success=intent.status == "succeeded",
                transaction_id=transaction_id,
                raw_response={"status": intent.status},
            )

        except Exception as e:
            return PaymentResult(
                success=False,
                error_message=str(e),
            )

    async def process_refund(
        self,
        transaction_id: str,
        amount: int,
        reason: str,
    ) -> RefundResult:
        """Process Stripe refund."""
        if not self.secret_key:
            return RefundResult(
                success=False,
                error_message="Stripe not configured",
            )

        try:
            import stripe

            stripe.api_key = self.secret_key

            refund = stripe.Refund.create(
                payment_intent=transaction_id,
                amount=amount,
                reason="requested_by_customer",
                metadata={"reason": reason[:500]},
            )

            return RefundResult(
                success=refund.status == "succeeded",
                refund_id=refund.id,
                raw_response={"status": refund.status, "id": refund.id},
            )

        except Exception as e:
            return RefundResult(
                success=False,
                error_message=str(e),
            )

    def verify_webhook(
        self,
        payload: bytes,
        signature: str,
    ) -> dict | None:
        """Verify Stripe webhook signature."""
        if not self.webhook_secret:
            return None

        try:
            import stripe

            event = stripe.Webhook.construct_event(
                payload,
                signature,
                self.webhook_secret,
            )
            return event

        except Exception:
            return None
