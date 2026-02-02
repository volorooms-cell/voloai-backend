#!/usr/bin/env python3
"""
Login to VOLO API and store access token.

Usage:
    python scripts/auth_login.py
    python scripts/auth_login.py --email admin@volo.ai --password Admin@123
"""

import argparse
import sys
from pathlib import Path

import httpx

BASE_URL = "http://localhost:8000"
TOKEN_FILE = Path(__file__).parent.parent / ".token"


def login(email: str, password: str) -> str:
    """Authenticate and return access token."""
    response = httpx.post(
        f"{BASE_URL}/api/v1/auth/login",
        json={"email": email, "password": password},
        timeout=10.0,
    )

    if response.status_code != 200:
        print(f"ERROR: Login failed with status {response.status_code}")
        print(response.text)
        sys.exit(1)

    data = response.json()
    token = data["access_token"]

    TOKEN_FILE.write_text(token)

    print("Login successful")
    print(f"Token: {token}")

    return token


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Login to VOLO API")
    parser.add_argument("--email", default="guest@volo.ai")
    parser.add_argument("--password", default="Test@1234")
    args = parser.parse_args()

    login(args.email, args.password)
