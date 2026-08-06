"""
Seed script — creates the default admin and employee users.
Run inside the API container: python scripts/seed.py
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
        "password": "admin",
        "role": UserRole.admin,
    },
    {
        "email": "employee@example.com",
        "password": "employee",
        "role": UserRole.employee,
    },
]


def seed():
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
