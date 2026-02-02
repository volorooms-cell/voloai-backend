#!/usr/bin/env python3
"""
Refund and cancellation flow test script.

DO NOT ADD BUSINESS LOGIC HERE.
This script only orchestrates API calls.
All rules live in the backend.

Usage:
    python scripts/flow_refund_and_cancel.py --listing-id <UUID> --check-in 2026-06-01 --check-out 2026-06-04
    python scripts/flow_refund_and_cancel.py --listing-id ac5b90b6-ce18-4c2c-bb6e-fe064db6bf28 --check-in 2026-06-01 --check-out 2026-06-04 --partial

Flow:
    1. Login as traveler
    2. Create booking
    3. Initiate payment
    4. Login as admin
    5. Mark payment as paid
    6. Confirm booking
    7. Process refund (full or partial)
    8. Cancel booking
"""

import argparse
import json
import sys
from pathlib import Path

import httpx

BASE_URL = "http://localhost:8000"
TOKEN_FILE = Path(__file__).parent.parent / ".token"

# Test credentials
TRAVELER_EMAIL = "traveler@volo.ai"
TRAVELER_PASSWORD = "Test@1234"
ADMIN_EMAIL = "guest@volo.ai"
ADMIN_PASSWORD = "Test@1234"


def login(email: str, password: str) -> str:
    """Login and return token."""
    response = httpx.post(
        f"{BASE_URL}/api/v1/auth/login",
        json={"email": email, "password": password},
        timeout=10.0,
    )
    if response.status_code != 200:
        print(f"ERROR: Login failed for {email}: {response.status_code}")
        print(response.text)
        sys.exit(1)

    token = response.json()["access_token"]
    TOKEN_FILE.write_text(token)
    return token


def api_request(token: str, method: str, endpoint: str, data: dict | None = None) -> dict:
    """Make authenticated API request."""
    headers = {"Authorization": f"Bearer {token}"}
    url = f"{BASE_URL}{endpoint}"

    if method == "GET":
        response = httpx.get(url, headers=headers, timeout=10.0, follow_redirects=True)
    elif method == "POST":
        response = httpx.post(url, headers=headers, json=data or {}, timeout=10.0, follow_redirects=True)
    else:
        raise ValueError(f"Unknown method: {method}")

    return {"status": response.status_code, "data": response.json() if response.text else {}}


def print_step(step: int, title: str):
    """Print step header."""
    print(f"\n{'='*60}")
    print(f"STEP {step}: {title}")
    print("="*60)


def print_result(result: dict, fields: list[str] | None = None):
    """Print result, optionally filtering fields."""
    if result["status"] >= 400:
        print(f"ERROR ({result['status']}): {json.dumps(result['data'], indent=2)}")
        return False

    print(f"Status: {result['status']}")
    if fields:
        filtered = {k: result["data"].get(k) for k in fields if k in result["data"]}
        print(json.dumps(filtered, indent=2))
    else:
        print(json.dumps(result["data"], indent=2))
    return True


def main():
    parser = argparse.ArgumentParser(description="Refund and cancellation flow")
    parser.add_argument("--listing-id", required=True, help="Listing UUID")
    parser.add_argument("--check-in", required=True, help="Check-in date (YYYY-MM-DD)")
    parser.add_argument("--check-out", required=True, help="Check-out date (YYYY-MM-DD)")
    parser.add_argument("--adults", type=int, default=2, help="Number of adults")
    parser.add_argument("--partial", action="store_true", help="Process partial refund (50%) instead of full")
    parser.add_argument("--cancel-reason", default="Guest requested cancellation due to change in travel plans", help="Cancellation reason")
    args = parser.parse_args()

    # Step 1: Login as traveler
    print_step(1, "Login as traveler")
    traveler_token = login(TRAVELER_EMAIL, TRAVELER_PASSWORD)
    print(f"Logged in as {TRAVELER_EMAIL}")

    # Step 2: Create booking
    print_step(2, "Create booking")
    booking_result = api_request(traveler_token, "POST", "/api/v1/bookings", {
        "listing_id": args.listing_id,
        "check_in": args.check_in,
        "check_out": args.check_out,
        "adults": args.adults,
    })
    if not print_result(booking_result, ["id", "booking_number", "total_price", "commission_amount", "host_payout_amount", "status", "payment_status"]):
        sys.exit(1)

    booking_id = booking_result["data"]["id"]
    booking_number = booking_result["data"]["booking_number"]
    total_price = booking_result["data"]["total_price"]
    print(f"\nBooking created: {booking_number}")

    # Step 3: Initiate payment
    print_step(3, "Initiate payment")
    payment_result = api_request(traveler_token, "POST", "/api/v1/payments/initiate", {
        "booking_id": booking_id,
        "payment_method": "bank_transfer",
    })
    if not print_result(payment_result, ["id", "amount", "status"]):
        sys.exit(1)

    payment_id = payment_result["data"]["id"]
    print(f"\nPayment initiated: {payment_id}")

    # Step 4: Login as admin
    print_step(4, "Login as admin")
    admin_token = login(ADMIN_EMAIL, ADMIN_PASSWORD)
    print(f"Logged in as {ADMIN_EMAIL}")

    # Step 5: Mark payment as paid
    print_step(5, "Mark payment as paid")
    mark_paid_result = api_request(admin_token, "POST", f"/api/v1/payments/{payment_id}/mark-paid")
    if not print_result(mark_paid_result, ["id", "status", "completed_at"]):
        sys.exit(1)
    print("\nPayment marked as PAID")

    # Step 6: Confirm booking
    print_step(6, "Confirm booking")
    confirm_result = api_request(admin_token, "POST", f"/api/v1/bookings/{booking_id}/confirm", {})
    if not print_result(confirm_result, ["id", "booking_number", "status", "payment_status"]):
        sys.exit(1)
    print("\nBooking CONFIRMED")

    # Step 7: Process refund via payment endpoint
    refund_amount = total_price // 2 if args.partial else None  # None = full refund
    refund_type = "PARTIAL (50%)" if args.partial else "FULL"

    print_step(7, f"Process {refund_type} refund")
    if refund_amount:
        print(f"Refund amount: {refund_amount:,} paisa ({refund_amount/100:,.0f} PKR)")
    else:
        print(f"Refund amount: FULL ({total_price:,} paisa)")

    refund_data = {"reason": f"{refund_type} refund processed for cancellation"}
    if refund_amount:
        refund_data["amount"] = refund_amount

    refund_result = api_request(admin_token, "POST", f"/api/v1/payments/{payment_id}/refund", refund_data)
    if not print_result(refund_result, ["id", "booking_id", "payment_id", "amount", "reason", "status"]):
        sys.exit(1)
    actual_refund = refund_result["data"].get("amount", total_price)
    print(f"\nRefund processed: {actual_refund:,} paisa")

    # Step 8: Cancel booking (as guest)
    print_step(8, "Cancel booking")
    traveler_token = login(TRAVELER_EMAIL, TRAVELER_PASSWORD)  # Re-login as traveler
    cancel_result = api_request(traveler_token, "POST", f"/api/v1/bookings/{booking_id}/cancel", {
        "reason": args.cancel_reason,
    })
    if not print_result(cancel_result, ["id", "booking_number", "status", "payment_status", "cancelled_by", "refund_amount", "cancelled_at"]):
        sys.exit(1)
    print("\nBooking CANCELLED")

    # Final summary
    print("\n" + "="*60)
    print("REFUND & CANCEL FLOW COMPLETE")
    print("="*60)
    print(f"Booking:        {booking_number}")
    print(f"Original Total: {total_price:,} paisa")
    print(f"Refund Type:    {refund_type}")
    print(f"Refund Amount:  {actual_refund:,} paisa")
    print(f"Final Status:   CANCELLED")


if __name__ == "__main__":
    main()
