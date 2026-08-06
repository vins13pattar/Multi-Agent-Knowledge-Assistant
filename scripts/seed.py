"""
Seed script — creates the default admin and employee demo users.
Run inside the API container: python scripts/seed.py

Gated behind SEED_DEMO_USERS (default "true", matching the documented
single-container demo flow) and always refused when ENVIRONMENT=production,
since these accounts use well-known passwords. Override SEED_ADMIN_PASSWORD /
SEED_EMPLOYEE_PASSWORD to seed with a non-default password instead.
"""
import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from src.database.session import db_session
from src.database.models import User, UserRole, UserStatus
from src.auth.jwt_handler import get_password_hash


SEED_USERS = [
    {
        "email": "admin@example.com",
        "password": os.getenv("SEED_ADMIN_PASSWORD", "admin"),
        "role": UserRole.admin,
    },
    {
        "email": "employee@example.com",
        "password": os.getenv("SEED_EMPLOYEE_PASSWORD", "employee"),
        "role": UserRole.employee,
    },
]


def seed():
    if os.getenv("ENVIRONMENT", "development") == "production":
        print("ENVIRONMENT=production — refusing to seed demo users. "
              "Create the first admin via POST /api/v1/users instead.")
        return
    if os.getenv("SEED_DEMO_USERS", "true").lower() != "true":
        print("SEED_DEMO_USERS is not 'true' — skipping demo user seeding.")
        return

    print("Seeding demo users with default/env-configured passwords — "
          "do not do this in a production deployment.")
    with db_session() as db:
        for user_data in SEED_USERS:
            existing = db.query(User).filter(User.email == user_data["email"]).first()
            if existing:
                print(f"User {user_data['email']} already exists, skipping.")
                continue
            user = User(
                email=user_data["email"],
                password_hash=get_password_hash(user_data["password"]),
                role=user_data["role"],
                status=UserStatus.active,
            )
            db.add(user)
            print(f"Created user: {user_data['email']} ({user_data['role'].value})")
    print("Seeding complete.")


if __name__ == "__main__":
    seed()
