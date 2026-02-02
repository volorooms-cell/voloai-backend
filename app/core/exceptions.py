"""Custom application exceptions."""

from typing import Any

from fastapi import HTTPException, status


class AppException(HTTPException):
    """Base application exception."""

    def __init__(
        self,
        status_code: int = status.HTTP_500_INTERNAL_SERVER_ERROR,
        detail: str = "An unexpected error occurred",
        headers: dict[str, str] | None = None,
    ) -> None:
        super().__init__(status_code=status_code, detail=detail, headers=headers)


class ValidationError(AppException):
    """Validation error exception."""

    def __init__(self, detail: str = "Validation failed", errors: list[dict[str, Any]] | None = None) -> None:
        self.errors = errors
        super().__init__(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=detail)


class NotFoundError(AppException):
    """Resource not found exception."""

    def __init__(self, resource: str = "Resource", identifier: str | None = None) -> None:
        detail = f"{resource} not found"
        if identifier:
            detail = f"{resource} with ID '{identifier}' not found"
        super().__init__(status_code=status.HTTP_404_NOT_FOUND, detail=detail)


class AuthenticationError(AppException):
    """Authentication failed exception."""

    def __init__(self, detail: str = "Authentication failed") -> None:
        super().__init__(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=detail,
            headers={"WWW-Authenticate": "Bearer"},
        )


class AuthorizationError(AppException):
    """Authorization denied exception."""

    def __init__(self, detail: str = "You don't have permission to access this resource") -> None:
        super().__init__(status_code=status.HTTP_403_FORBIDDEN, detail=detail)


class ListingNotAvailable(AppException):
    """Listing not available exception."""

    def __init__(self, detail: str = "This listing is not available") -> None:
        super().__init__(status_code=status.HTTP_400_BAD_REQUEST, detail=detail)


class DatesNotAvailable(AppException):
    """Dates not available exception."""

    def __init__(self, detail: str = "The selected dates are not available") -> None:
        super().__init__(status_code=status.HTTP_409_CONFLICT, detail=detail)


class InvalidBookingStatus(AppException):
    """Invalid booking status for operation."""

    def __init__(self, detail: str = "This operation is not allowed for the current booking status") -> None:
        super().__init__(status_code=status.HTTP_400_BAD_REQUEST, detail=detail)


class PaymentError(AppException):
    """Payment processing error."""

    def __init__(self, detail: str = "Payment processing failed") -> None:
        super().__init__(status_code=status.HTTP_402_PAYMENT_REQUIRED, detail=detail)


class InsufficientBalance(AppException):
    """Insufficient balance for payout."""

    def __init__(self, detail: str = "Insufficient balance for this operation") -> None:
        super().__init__(status_code=status.HTTP_400_BAD_REQUEST, detail=detail)


class RateLimitExceeded(AppException):
    """Rate limit exceeded exception."""

    def __init__(self, detail: str = "Too many requests. Please try again later.") -> None:
        super().__init__(status_code=status.HTTP_429_TOO_MANY_REQUESTS, detail=detail)


class ExternalServiceError(AppException):
    """External service error."""

    def __init__(self, service: str, detail: str | None = None) -> None:
        message = f"External service '{service}' is unavailable"
        if detail:
            message = f"{message}: {detail}"
        super().__init__(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=message)
