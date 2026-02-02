#!/usr/bin/env python3
"""
Make authenticated API requests using stored token.

Usage:
    python scripts/auth_request.py
    python scripts/auth_request.py GET /api/v1/users/me
    python scripts/auth_request.py POST /api/v1/listings --data '{"title": "Test"}'
"""

import argparse
import json
import sys
from pathlib import Path

import httpx

BASE_URL = "http://localhost:8000"
TOKEN_FILE = Path(__file__).parent.parent / ".token"


def get_token() -> str:
    """Read stored access token."""
    if not TOKEN_FILE.exists():
        print("ERROR: No token found. Run auth_login.py first.")
        sys.exit(1)

    token = TOKEN_FILE.read_text().strip()
    if not token:
        print("ERROR: Token file is empty. Run auth_login.py first.")
        sys.exit(1)

    return token


def request(method: str, endpoint: str, data: str | None = None) -> None:
    """Make authenticated API request."""
    token = get_token()
    headers = {"Authorization": f"Bearer {token}"}

    url = f"{BASE_URL}{endpoint}"

    if method == "GET":
        response = httpx.get(url, headers=headers, timeout=10.0, follow_redirects=True)
    elif method == "POST":
        body = json.loads(data) if data else {}
        response = httpx.post(url, headers=headers, json=body, timeout=10.0, follow_redirects=True)
    elif method == "PUT":
        body = json.loads(data) if data else {}
        response = httpx.put(url, headers=headers, json=body, timeout=10.0, follow_redirects=True)
    elif method == "PATCH":
        body = json.loads(data) if data else {}
        response = httpx.patch(url, headers=headers, json=body, timeout=10.0, follow_redirects=True)
    elif method == "DELETE":
        response = httpx.delete(url, headers=headers, timeout=10.0, follow_redirects=True)
    else:
        print(f"ERROR: Unknown method {method}")
        sys.exit(1)

    print(f"Status: {response.status_code}")
    try:
        print(json.dumps(response.json(), indent=2))
    except json.JSONDecodeError:
        print(response.text)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Make authenticated API request")
    parser.add_argument("method", nargs="?", default="GET")
    parser.add_argument("endpoint", nargs="?", default="/api/v1/auth/me")
    parser.add_argument("--data", "-d", help="JSON request body")
    args = parser.parse_args()

    request(args.method.upper(), args.endpoint, args.data)
