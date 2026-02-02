#!/usr/bin/env python3
"""
Complete booking and payment flow test script.

DO NOT ADD BUSINESS LOGIC HERE.
This script only orchestrates API calls.
All rules live in the backend.

Usage:
    python scripts/flow_book_and_pay.py --listing-id <UUID> --check-in 2026-04-01 --check-out 2026-04-04
    python scripts/flow_book_and_pay.py --listing-id ac5b90b6-ce18-4c2c-bb6e-fe064db6bf28 --check-in 2026-05-01 --check-out 2026-05-05

Flow:
    1. Login as traveler
    2. Calculate booking price
    3. Create booking
    4. Initiate payment
    5. Login as admin
    6. Mark payment as paid
    7. Confirm booking (as host)
    8. Check-in guest
    9. Complete booking
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
HOST_EMAIL = "guest@volo.ai"
HOST_PASSWORD = "Test@1234"


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
    elif method == "PATCH":
        response = httpx.patch(url, headers=headers, json=data or {}, timeout=10.0, follow_redirects=True)
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
    parser = argparse.ArgumentParser(description="Complete booking and payment flow")
    parser.add_argument("--listing-id", required=True, help="Listing UUID")
    parser.add_argument("--check-in", required=True, help="Check-in date (YYYY-MM-DD)")
    parser.add_argument("--check-out", required=True, help="Check-out date (YYYY-MM-DD)")
    parser.add_argument("--adults", type=int, default=2, help="Number of adults")
    parser.add_argument("--skip-complete", action="store_true", help="Skip check-in and complete steps")
    args = parser.parse_args()

    # Step 1: Login as traveler
    print_step(1, "Login as traveler")
    traveler_token = login(TRAVELER_EMAIL, TRAVELER_PASSWORD)
    print(f"Logged in as {TRAVELER_EMAIL}")

    # Step 2: Calculate booking price
    print_step(2, "Calculate booking price")
    calc_result = api_request(traveler_token, "POST", "/api/v1/bookings/calculate", {
        "listing_id": args.listing_id,
        "check_in": args.check_in,
        "check_out": args.check_out,
        "guests": args.adults,
    })
    if not print_result(calc_result):
        sys.exit(1)

    if not calc_result["data"].get("available"):
        print(f"ERROR: Listing not available - {calc_result['data'].get('unavailable_reason')}")
        sys.exit(1)

    breakdown = calc_result["data"]["price_breakdown"]
    print(f"\nPricing Summary:")
    print(f"  Total Price:    {breakdown['total_price']:,} paisa ({breakdown['total_price']/100:,.0f} PKR)")
    print(f"  Commission:     {breakdown['commission_amount']:,} paisa ({breakdown['commission_rate']}%)")
    print(f"  Host Payout:    {breakdown['host_payout_amount']:,} paisa")

    # Step 3: Create booking
    print_step(3, "Create booking")
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
    print(f"\nBooking created: {booking_number}")

    # Step 4: Initiate payment
    print_step(4, "Initiate payment")
    payment_result = api_request(traveler_token, "POST", "/api/v1/payments/initiate", {
        "booking_id": booking_id,
        "payment_method": "bank_transfer",
    })
    if not print_result(payment_result, ["id", "amount", "currency", "payment_method", "gateway", "status"]):
        sys.exit(1)

    payment_id = payment_result["data"]["id"]
    print(f"\nPayment initiated: {payment_id}")

    # Step 5: Login as host/admin to mark payment as paid
    print_step(5, "Login as host/admin and mark payment as paid")
    host_token = login(HOST_EMAIL, HOST_PASSWORD)
    print(f"Logged in as {HOST_EMAIL}")

    mark_paid_result = api_request(host_token, "POST", f"/api/v1/payments/{payment_id}/mark-paid")
    if not print_result(mark_paid_result, ["id", "status", "completed_at"]):
        sys.exit(1)
    print("\nPayment marked as PAID")

    # Step 6: Confirm booking
    print_step(6, "Confirm booking (as host)")
    confirm_result = api_request(host_token, "POST", f"/api/v1/bookings/{booking_id}/confirm", {})
    if not print_result(confirm_result, ["id", "booking_number", "status", "payment_status", "confirmed_at"]):
        sys.exit(1)
    print("\nBooking CONFIRMED")

    if args.skip_complete:
        print("\n" + "="*60)
        print("FLOW COMPLETE (skipped check-in and complete)")
        print("="*60)
        return

    # Step 7: Check-in guest
    print_step(7, "Check-in guest")
    checkin_result = api_request(host_token, "POST", f"/api/v1/bookings/{booking_id}/check-in")
    if not print_result(checkin_result, ["id", "booking_number", "status"]):
        sys.exit(1)
    print("\nGuest CHECKED IN")

    # Step 8: Complete booking
    print_step(8, "Complete booking")
    complete_result = api_request(host_token, "POST", f"/api/v1/bookings/{booking_id}/complete")
    if not print_result(complete_result, ["id", "booking_number", "status", "completed_at"]):
        sys.exit(1)
    print("\nBooking COMPLETED")

    # Final summary
    print("\n" + "="*60)
    print("FULL FLOW COMPLETE")
    print("="*60)
    print(f"Booking:        {booking_number}")
    print(f"Total Paid:     {breakdown['total_price']:,} paisa")
    print(f"VOLO Commission: {breakdown['commission_amount']:,} paisa (9%)")
    print(f"Host Payout:    {breakdown['host_payout_amount']:,} paisa")


if __name__ == "__main__":
    main()
