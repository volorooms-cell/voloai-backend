"""Custom validation utilities."""

import re


def validate_cnic(cnic: str) -> bool:
    """Validate Pakistani CNIC number.

    CNIC format: XXXXX-XXXXXXX-X (13 digits with dashes)
    or: XXXXXXXXXXXXX (13 digits without dashes)

    Args:
        cnic: CNIC number to validate

    Returns:
        bool: True if valid CNIC format
    """
    # Remove dashes if present
    cleaned = cnic.replace("-", "")

    # Must be exactly 13 digits
    if not cleaned.isdigit() or len(cleaned) != 13:
        return False

    return True


def format_cnic(cnic: str) -> str:
    """Format CNIC number with dashes.

    Args:
        cnic: CNIC number (with or without dashes)

    Returns:
        str: Formatted CNIC like XXXXX-XXXXXXX-X
    """
    cleaned = cnic.replace("-", "")
    if len(cleaned) != 13:
        return cnic
    return f"{cleaned[:5]}-{cleaned[5:12]}-{cleaned[12]}"


def validate_pakistani_phone(phone: str) -> bool:
    """Validate Pakistani phone number.

    Accepted formats:
    - +923001234567 (international)
    - 03001234567 (local)
    - 0300-1234567 (local with dash)

    Args:
        phone: Phone number to validate

    Returns:
        bool: True if valid Pakistani phone format
    """
    # Remove spaces, dashes, and parentheses
    cleaned = re.sub(r"[\s\-\(\)]", "", phone)

    # International format with +92
    if cleaned.startswith("+92"):
        return len(cleaned) == 13 and cleaned[3:].isdigit() and cleaned[3] == "3"

    # Local format starting with 03
    if cleaned.startswith("03"):
        return len(cleaned) == 11 and cleaned.isdigit()

    return False


def normalize_phone(phone: str) -> str:
    """Normalize phone number to international format.

    Args:
        phone: Phone number in any format

    Returns:
        str: Phone number in +92XXXXXXXXXX format
    """
    # Remove non-digits except +
    cleaned = re.sub(r"[^\d+]", "", phone)

    # Already international format
    if cleaned.startswith("+92"):
        return cleaned

    # Local format starting with 0
    if cleaned.startswith("0"):
        return "+92" + cleaned[1:]

    # Just digits starting with 3
    if cleaned.startswith("3") and len(cleaned) == 10:
        return "+92" + cleaned

    return phone  # Return as-is if can't normalize


def validate_iban(iban: str) -> bool:
    """Validate Pakistani IBAN.

    Pakistani IBAN format: PK followed by 22 characters

    Args:
        iban: IBAN to validate

    Returns:
        bool: True if valid Pakistani IBAN format
    """
    # Remove spaces
    cleaned = iban.replace(" ", "").upper()

    # Must start with PK and be 24 characters total
    if not cleaned.startswith("PK"):
        return False

    if len(cleaned) != 24:
        return False

    # Check if remaining characters are alphanumeric
    return cleaned[2:].isalnum()


def mask_sensitive_data(data: str, visible_chars: int = 4) -> str:
    """Mask sensitive data showing only last few characters.

    Args:
        data: Sensitive data to mask
        visible_chars: Number of characters to show at end

    Returns:
        str: Masked string like '********7890'
    """
    if len(data) <= visible_chars:
        return "*" * len(data)

    masked_length = len(data) - visible_chars
    return "*" * masked_length + data[-visible_chars:]
