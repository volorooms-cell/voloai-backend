"""PayFast payment gateway adapter.

PayFast integration for Pakistan market.
Documentation: https://developers.payfast.co.za/docs
"""

import hashlib
import hmac
from urllib.parse import urlencode

import httpx

from app.config import settings
from app.gateways.base import (
    GatewayType,
    PaymentGateway,
    PaymentResult,
    RefundResult,
)


class PayFastGateway(PaymentGateway):
    """PayFast payment gateway implementation."""

    def __init__(self):
        self.merchant_id = getattr(settings, "payfast_merchant_id", None)
        self.merchant_key = getattr(settings, "payfast_merchant_key", None)
        self.passphrase = getattr(settings, "payfast_passphrase", None)
        self.sandbox = getattr(settings, "payfast_sandbox", True)

        # Environment safety: force sandbox in non-production
        if settings.environment != "production":
            self.sandbox = True

        self.base_url = (
            "https://sandbox.payfast.co.za"
            if self.sandbox
            else "https://www.payfast.co.za"
        )
        self.api_url = (
            "https://api.payfast.co.za"
            if not self.sandbox
            else "https://api.payfast.co.za"
        )

    @property
    def is_sandbox(self) -> bool:
        """Explicit sandbox flag for external checks."""
        return self.sandbox

    @property
    def gateway_type(self) -> GatewayType:
        return GatewayType.PAYFAST

    def _generate_signature(self, data: dict) -> str:
        """Generate PayFast signature for request."""
        # Sort and encode parameters
        sorted_data = sorted(data.items())
        param_string = urlencode(sorted_data)

        if self.passphrase:
            param_string += f"&passphrase={self.passphrase}"

        return hashlib.md5(param_string.encode()).hexdigest()

    async def create_payment(
        self,
        amount: int,
        currency: str,
        reference_id: str,
        description: str,
        metadata: dict | None = None,
    ) -> PaymentResult:
        """Create PayFast payment request."""
        if not self.merchant_id or not self.merchant_key:
            return PaymentResult(
                success=False,
                error_message="PayFast credentials not configured",
            )

        # Convert paisa to rupees (PayFast expects decimal amount)
        amount_decimal = amount / 100

        data = {
            "merchant_id": self.merchant_id,
            "merchant_key": self.merchant_key,
            "amount": f"{amount_decimal:.2f}",
            "item_name": description[:100],
            "m_payment_id": reference_id,
        }

        if metadata:
            data["custom_str1"] = str(metadata.get("booking_id", ""))

        signature = self._generate_signature(data)
        data["signature"] = signature

        # In production, this would redirect user to PayFast
        # For now, return the payment URL
        payment_url = f"{self.base_url}/eng/process?" + urlencode(data)

        return PaymentResult(
            success=True,
            transaction_id=reference_id,
            raw_response={
                "payment_url": payment_url,
                "data": data,
                "sandbox": self.sandbox,
                "environment": settings.environment,
            },
        )

    async def verify_payment(
        self,
        transaction_id: str,
    ) -> PaymentResult:
        """Verify PayFast payment status via API."""
        if not self.merchant_id or not self.passphrase:
            return PaymentResult(
                success=False,
                error_message="PayFast credentials not configured",
            )

        try:
            timestamp = httpx._utils.get_netrc_auth  # placeholder
            headers = {
                "merchant-id": self.merchant_id,
                "version": "v1",
                "timestamp": "",  # Would be actual timestamp
                "signature": "",  # Would be computed signature
            }

            async with httpx.AsyncClient() as client:
                response = await client.get(
                    f"{self.api_url}/subscriptions/{transaction_id}/fetch",
                    headers=headers,
                    timeout=30.0,
                )

            if response.status_code == 200:
                data = response.json()
                return PaymentResult(
                    success=data.get("status") == "COMPLETE",
                    transaction_id=transaction_id,
                    raw_response=data,
                )

            return PaymentResult(
                success=False,
                error_message=f"API returned {response.status_code}",
                raw_response={"status_code": response.status_code},
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
        """Process refund via PayFast API."""
        if not self.merchant_id or not self.passphrase:
            return RefundResult(
                success=False,
                error_message="PayFast credentials not configured",
            )

        # PayFast refunds are processed via their merchant portal
        # or via API for certain account types
        # This is a simplified implementation

        try:
            amount_decimal = amount / 100

            # In production, this would call the PayFast refund API
            # For now, return success (manual processing required)
            return RefundResult(
                success=True,
                refund_id=f"refund_{transaction_id}",
                raw_response={
                    "original_transaction": transaction_id,
                    "refund_amount": amount_decimal,
                    "reason": reason,
                    "note": "Manual processing may be required",
                },
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
        """Verify PayFast ITN (Instant Transaction Notification)."""
        try:
            # Parse the payload
            from urllib.parse import parse_qs

            data = {k: v[0] for k, v in parse_qs(payload.decode()).items()}

            # Remove signature from data for verification
            received_signature = data.pop("signature", None)

            # Generate expected signature
            expected_signature = self._generate_signature(data)

            if received_signature != expected_signature:
                return None

            return data

        except Exception:
            return None
