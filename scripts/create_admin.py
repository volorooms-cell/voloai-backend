#!/usr/bin/env python3
"""Create an admin user with properly hashed password."""

import asyncio
import sys
from uuid import uuid4

# Add parent directory to path for imports
sys.path.insert(0, "/app")

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import get_password_hash
from app.database import AsyncSessionLocal
from app.models.user import User


async def create_admin(
    email: str = "admin@volo.ai",
    password: str = "Admin@123",
    first_name: str = "VOLO",
    last_name: str = "Admin",
) -> None:
    """Create an admin user if it doesn't exist."""
    async with AsyncSessionLocal() as session:

        # Check if admin already exists
        result = await session.execute(
            select(User).where(User.email == email)
        )
        existing = result.scalar_one_or_none()

        if existing:
            # Update password hash to use Argon2
            existing.password_hash = get_password_hash(password)
            existing.role = "admin"
            existing.is_verified = True
            existing.is_active = True
            existing.first_name = first_name
            existing.last_name = last_name
            await session.commit()
            print(f"Updated existing admin user: {email}")
        else:
            # Create new admin
            admin = User(
                id=uuid4(),
                email=email,
                password_hash=get_password_hash(password),
                role="admin",
                first_name=first_name,
                last_name=last_name,
                is_verified=True,
                is_active=True,
                is_email_verified=True,
            )
            session.add(admin)
            await session.commit()
            print(f"Created admin user: {email}")

        print(f"Email: {email}")
        print(f"Password: {password}")
        print("Role: admin")


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Create an admin user")
    parser.add_argument("--email", default="admin@volo.ai", help="Admin email")
    parser.add_argument("--password", default="Admin@123", help="Admin password")
    parser.add_argument("--first-name", default="VOLO", help="First name")
    parser.add_argument("--last-name", default="Admin", help="Last name")

    args = parser.parse_args()

    asyncio.run(
        create_admin(
            email=args.email,
            password=args.password,
            first_name=args.first_name,
            last_name=args.last_name,
        )
    )
