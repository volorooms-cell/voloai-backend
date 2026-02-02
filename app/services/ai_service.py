"""AI service using Claude API for assistive features.

CRITICAL: AI is ASSISTIVE ONLY. Never autonomous.
- AI suggests, human decides
- All AI outputs require host review before use
- AI cannot make bookings, payments, or policy changes
"""

import json
from typing import Any

from anthropic import AsyncAnthropic

from app.config import settings


class AIService:
    """AI assistance service using Claude API."""

    def __init__(self) -> None:
        """Initialize the AI service."""
        self.client = AsyncAnthropic(api_key=settings.anthropic_api_key) if settings.anthropic_api_key else None
        self.model = settings.claude_model
        self.max_tokens = settings.claude_max_tokens

    def _check_client(self) -> None:
        """Ensure API client is configured."""
        if not self.client:
            raise ValueError("Claude API key not configured")

    async def generate_listing_titles(
        self,
        listing_type: str,
        location: str,
        bedrooms: int,
        amenities: list[str],
    ) -> list[str]:
        """Generate title suggestions for a listing.

        Args:
            listing_type: Type of listing (e.g., 'entire_apartment')
            location: City/area name
            bedrooms: Number of bedrooms
            amenities: List of key amenities

        Returns:
            list[str]: 3 title suggestions for host to choose from
        """
        self._check_client()

        # Format listing type for display
        listing_type_display = listing_type.replace("_", " ").title()
        amenities_str = ", ".join(amenities[:5]) if amenities else "standard amenities"

        prompt = f"""Generate 3 compelling Airbnb-style listing titles for a vacation rental:

Property Details:
- Type: {listing_type_display}
- Location: {location}, Pakistan
- Bedrooms: {bedrooms}
- Key amenities: {amenities_str}

Requirements:
- Maximum 50 characters each
- Highlight unique selling points
- Use engaging, descriptive language
- Suitable for the Pakistani market
- Do NOT use emojis

Return exactly 3 titles, one per line, with no numbering or bullet points."""

        response = await self.client.messages.create(
            model=self.model,
            max_tokens=200,
            messages=[{"role": "user", "content": prompt}],
        )

        # Parse response
        text = response.content[0].text.strip()
        titles = [t.strip() for t in text.split("\n") if t.strip()]
        return titles[:3]

    async def generate_listing_description(
        self,
        listing_type: str,
        location: str,
        bedrooms: int,
        bathrooms: float,
        amenities: list[str],
        house_rules: list[str] | None = None,
        nearby_attractions: str | None = None,
    ) -> str:
        """Generate a description for a listing.

        Args:
            listing_type: Type of listing
            location: City/area name
            bedrooms: Number of bedrooms
            bathrooms: Number of bathrooms
            amenities: List of amenities
            house_rules: List of house rules
            nearby_attractions: Description of nearby places

        Returns:
            str: Generated description for host to review and edit
        """
        self._check_client()

        listing_type_display = listing_type.replace("_", " ").title()
        amenities_str = ", ".join(amenities) if amenities else "basic amenities"
        rules_str = ", ".join(house_rules) if house_rules else "standard rules"
        nearby_str = nearby_attractions or "various local attractions"

        prompt = f"""Write an engaging Airbnb-style listing description for a vacation rental:

Property Details:
- Type: {listing_type_display}
- Location: {location}, Pakistan
- Bedrooms: {bedrooms}
- Bathrooms: {bathrooms}
- Amenities: {amenities_str}
- House rules: {rules_str}
- Nearby: {nearby_str}

Requirements:
- 150-250 words
- Warm, welcoming tone
- Highlight unique features
- Include practical information for guests
- Do NOT make up facts not provided
- Suitable for the Pakistani market
- Do NOT use emojis

Write the description directly, no headers or formatting:"""

        response = await self.client.messages.create(
            model=self.model,
            max_tokens=500,
            messages=[{"role": "user", "content": prompt}],
        )

        return response.content[0].text.strip()

    async def suggest_price_adjustment(
        self,
        base_price: int,
        date: str,
        day_of_week: str,
        local_events: list[str] | None = None,
        occupancy_rate: float = 0.5,
        competitor_prices: list[int] | None = None,
    ) -> dict[str, Any]:
        """Suggest a dynamic price adjustment for a specific date.

        Args:
            base_price: Base nightly rate in PKR
            date: Date string (YYYY-MM-DD)
            day_of_week: Day name (e.g., 'Friday')
            local_events: List of local events on that date
            occupancy_rate: Current occupancy rate (0-1)
            competitor_prices: List of competitor prices in PKR

        Returns:
            dict: Suggested price and reasoning (host must approve)
        """
        self._check_client()

        events_str = ", ".join(local_events) if local_events else "None"
        competitors_str = (
            ", ".join(f"PKR {p:,}" for p in competitor_prices)
            if competitor_prices
            else "Unknown"
        )

        prompt = f"""Analyze pricing for a vacation rental in Pakistan and suggest an adjustment:

Current Pricing:
- Base price: PKR {base_price:,}
- Date: {date} ({day_of_week})
- Local events: {events_str}
- Current occupancy rate: {occupancy_rate:.0%}
- Competitor prices: {competitors_str}

Analyze the factors and suggest a price adjustment.

Return your response as valid JSON with this exact structure:
{{
    "suggested_price": <number in PKR>,
    "adjustment_percent": <number, positive for increase, negative for decrease>,
    "reasoning": "<brief 1-2 sentence explanation>"
}}

Only return the JSON, no other text."""

        response = await self.client.messages.create(
            model=self.model,
            max_tokens=200,
            messages=[{"role": "user", "content": prompt}],
        )

        try:
            result = json.loads(response.content[0].text.strip())
            return {
                "suggested_price": int(result.get("suggested_price", base_price)),
                "adjustment_percent": float(result.get("adjustment_percent", 0)),
                "reasoning": str(result.get("reasoning", "No specific adjustment needed")),
                "requires_host_approval": True,  # Always require approval
            }
        except (json.JSONDecodeError, KeyError, TypeError):
            return {
                "suggested_price": base_price,
                "adjustment_percent": 0,
                "reasoning": "Unable to generate suggestion",
                "requires_host_approval": True,
            }

    async def generate_response_suggestion(
        self,
        guest_message: str,
        listing_title: str,
        host_name: str,
        context: str | None = None,
    ) -> str:
        """Generate a suggested response to a guest message.

        Args:
            guest_message: The guest's message
            listing_title: Title of the listing
            host_name: Name of the host
            context: Optional context about the conversation

        Returns:
            str: Suggested response for host to review and customize
        """
        self._check_client()

        context_str = f"\nAdditional context: {context}" if context else ""

        prompt = f"""Generate a suggested response for a vacation rental host:

Guest's message: "{guest_message}"

Listing: {listing_title}
Host name: {host_name}{context_str}

Requirements:
- Professional and friendly tone
- Address the guest's question or concern
- Keep response concise (2-4 sentences)
- Sign off appropriately
- Do NOT make commitments the host hasn't approved
- Do NOT provide specific pricing (tell guest to check listing)

Generate a response the host can review and customize:"""

        response = await self.client.messages.create(
            model="claude-haiku-4-20250514",  # Use faster model for chat
            max_tokens=200,
            messages=[{"role": "user", "content": prompt}],
        )

        return response.content[0].text.strip()


class WhatsAppAIService:
    """WhatsApp assistant for guest inquiries.

    CRITICAL RULES:
    - NEVER complete bookings
    - ALWAYS redirect to VOLO app/web
    - Escalate to human on request
    - Can be disabled by host
    """

    ESCALATION_KEYWORDS = [
        "speak to human",
        "real person",
        "talk to host",
        "help",
        "problem",
        "issue",
        "complaint",
        "urgent",
        "emergency",
    ]

    def __init__(self) -> None:
        """Initialize the WhatsApp AI service."""
        self.client = AsyncAnthropic(api_key=settings.anthropic_api_key) if settings.anthropic_api_key else None

    async def handle_inquiry(
        self,
        message: str,
        listing_title: str,
        listing_city: str,
        max_guests: int,
        check_in_time: str,
        check_out_time: str,
        direct_booking_slug: str,
        whatsapp_ai_enabled: bool = True,
    ) -> dict[str, Any]:
        """Handle a guest inquiry via WhatsApp.

        Args:
            message: Guest's message
            listing_title: Title of the listing
            listing_city: City of the listing
            max_guests: Maximum guests allowed
            check_in_time: Check-in time
            check_out_time: Check-out time
            direct_booking_slug: Slug for direct booking link
            whatsapp_ai_enabled: Whether AI is enabled for this listing

        Returns:
            dict: Action to take and response text
        """
        # If AI is disabled, forward to host
        if not whatsapp_ai_enabled:
            return {
                "action": "forward_to_host",
                "response": None,
            }

        # Check for escalation keywords
        message_lower = message.lower()
        if any(keyword in message_lower for keyword in self.ESCALATION_KEYWORDS):
            return {
                "action": "escalate",
                "response": "I'm connecting you with the host. They'll respond to you shortly!",
            }

        # Check if API is configured
        if not self.client:
            return {
                "action": "forward_to_host",
                "response": None,
            }

        # Generate helpful response
        prompt = f"""You are a helpful assistant for a vacation rental listing on VOLO AI.

Listing Information:
- Title: {listing_title}
- Location: {listing_city}, Pakistan
- Max guests: {max_guests}
- Check-in: {check_in_time}
- Check-out: {check_out_time}

Guest's WhatsApp message: "{message}"

Requirements:
- Answer the guest's question helpfully
- Keep response under 100 words
- Do NOT claim to make bookings
- Do NOT give specific prices (they may change)
- ALWAYS end with: "To book this property, please visit: voloai.pk/book/{direct_booking_slug}"
- Be friendly and professional

Generate the response:"""

        try:
            response = await self.client.messages.create(
                model="claude-haiku-4-20250514",
                max_tokens=150,
                messages=[{"role": "user", "content": prompt}],
            )

            return {
                "action": "respond",
                "response": response.content[0].text.strip(),
                "redirect_link": f"https://voloai.pk/book/{direct_booking_slug}",
            }
        except Exception:
            return {
                "action": "forward_to_host",
                "response": None,
            }


# Service instances
ai_service = AIService()
whatsapp_ai_service = WhatsAppAIService()
