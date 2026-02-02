"""Commission calculation service.

CRITICAL BUSINESS LOGIC:
- VOLO charges a flat 9% commission on all VOLO bookings
- This 9% INCLUDES all payment processing costs (gateway fees absorbed by VOLO)
- Guests see no gateway fees - only the total amount
- Hosts see only a single 9% VOLO fee
- Direct bookings (custom link, WhatsApp): 0% commission
- Extensions inherit the original booking source for commission calculation
"""

from decimal import Decimal
from enum import Enum


# Flat VOLO commission rate (includes all gateway fees)
VOLO_COMMISSION_RATE = Decimal("9.00")


class BookingSource(str, Enum):
    """Booking source types."""

    AIRBNB = "AIRBNB"
    BOOKING_COM = "BOOKING_COM"
    VOLO_MARKETPLACE = "VOLO_MARKETPLACE"
    DIRECT_LINK = "DIRECT_LINK"
    DIRECT_WHATSAPP = "DIRECT_WHATSAPP"


# Commission rates by booking source
COMMISSION_RATES: dict[BookingSource, Decimal] = {
    BookingSource.AIRBNB: Decimal("0.00"),  # External, just calendar sync
    BookingSource.BOOKING_COM: Decimal("0.00"),  # External, just calendar sync
    BookingSource.VOLO_MARKETPLACE: VOLO_COMMISSION_RATE,  # Flat 9% (includes gateway fees)
    BookingSource.DIRECT_LINK: Decimal("0.00"),  # 0% for direct
    BookingSource.DIRECT_WHATSAPP: Decimal("0.00"),  # 0% for direct
}


class CommissionService:
    """Service for calculating booking commissions and payouts."""

    def get_commission_rate(self, source: str | BookingSource) -> Decimal:
        """Get commission rate percentage for a booking source.

        Args:
            source: The booking source (string or enum)

        Returns:
            Decimal: Commission rate as percentage (e.g., 9.00 for 9%)
        """
        if isinstance(source, str):
            try:
                source = BookingSource(source)
            except ValueError:
                # Default to marketplace rate for unknown sources
                return VOLO_COMMISSION_RATE
        return COMMISSION_RATES.get(source, VOLO_COMMISSION_RATE)

    def calculate_commission(self, source: str | BookingSource, total_amount: int) -> int:
        """Calculate commission amount in smallest currency unit.

        Commission is calculated on total_amount (what guest pays).

        Args:
            source: The booking source
            total_amount: Total booking amount in paisa (what guest pays)

        Returns:
            int: Commission amount in paisa
        """
        rate = self.get_commission_rate(source)
        commission = (Decimal(total_amount) * rate / Decimal("100")).quantize(Decimal("1"))
        return int(commission)

    def calculate_booking_amounts(
        self,
        source: str | BookingSource,
        nightly_rate: int,
        nights: int,
        cleaning_fee: int = 0,
    ) -> dict:
        """Calculate all booking amounts including commission and host payout.

        VOLO charges flat 9% commission on total_amount.
        - total_amount = subtotal + cleaning_fee (what guest pays)
        - volo_commission = 9% of total_amount
        - host_payout = total_amount - volo_commission

        Guests see no gateway fees. Hosts see only 9% VOLO fee.

        Args:
            source: The booking source
            nightly_rate: Price per night in paisa
            nights: Number of nights
            cleaning_fee: One-time cleaning fee in paisa

        Returns:
            dict: All calculated amounts
        """
        # Calculate subtotal (accommodation cost)
        subtotal = nightly_rate * nights

        # Total price paid by guest (no separate service fees shown)
        total_price = subtotal + cleaning_fee

        # Commission is calculated on total_price (what guest pays)
        commission_rate = self.get_commission_rate(source)
        commission_amount = self.calculate_commission(source, total_price)

        # Host payout = total_price - commission
        host_payout = total_price - commission_amount

        return {
            "nightly_rate": nightly_rate,
            "nights": nights,
            "subtotal": subtotal,
            "cleaning_fee": cleaning_fee,
            "service_fee": 0,  # No separate service fee - included in 9%
            "total_price": total_price,
            "commission_rate": float(commission_rate),
            "commission_amount": commission_amount,
            "host_payout_amount": host_payout,
        }

    def calculate_extension_commission(
        self,
        original_source: str | BookingSource,
        additional_nights: int,
        nightly_rate: int,
    ) -> dict:
        """Calculate commission for a booking extension.

        IMPORTANT: Extensions ALWAYS inherit the original booking source.
        - If original was marketplace, extension is also 9%
        - If original was direct, extension is also 0%

        Commission is calculated on additional_amount (what guest pays for extension).

        Args:
            original_source: The original booking's source
            additional_nights: Number of additional nights
            nightly_rate: Price per night in paisa

        Returns:
            dict: Extension pricing details
        """
        additional_amount = nightly_rate * additional_nights
        commission_amount = self.calculate_commission(original_source, additional_amount)

        return {
            "additional_nights": additional_nights,
            "additional_amount": additional_amount,
            "commission_amount": commission_amount,
            "host_payout_additional": additional_amount - commission_amount,
        }

    def is_direct_booking(self, source: str | BookingSource) -> bool:
        """Check if a booking source is a direct booking (0% commission).

        Args:
            source: The booking source

        Returns:
            bool: True if direct booking with 0% commission
        """
        if isinstance(source, str):
            try:
                source = BookingSource(source)
            except ValueError:
                return False
        return source in (BookingSource.DIRECT_LINK, BookingSource.DIRECT_WHATSAPP)

    def is_external_booking(self, source: str | BookingSource) -> bool:
        """Check if a booking source is external (Airbnb/Booking.com).

        Args:
            source: The booking source

        Returns:
            bool: True if external OTA booking
        """
        if isinstance(source, str):
            try:
                source = BookingSource(source)
            except ValueError:
                return False
        return source in (BookingSource.AIRBNB, BookingSource.BOOKING_COM)
