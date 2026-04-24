"""
database.py
MongoDB connection + first-run user seeding.

On startup, seeds the admin user if the users collection is empty.
Credentials come from environment variables (see .env.example).
"""

import os
from pymongo import MongoClient
from pymongo.collection import Collection
from passlib.context import CryptContext
from dotenv import load_dotenv

load_dotenv()

MONGO_URI = os.getenv("MONGO_URI", "mongodb://localhost:27017")
DB_NAME   = os.getenv("DB_NAME", "vassure")

_client: MongoClient | None = None

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def get_db():
    global _client
    if _client is None:
        _client = MongoClient(MONGO_URI)
    return _client[DB_NAME]


def get_users_collection() -> Collection:
    return get_db()["users"]


def hash_password(plain: str) -> str:
    return pwd_context.hash(plain[:72])


def verify_password(plain: str, hashed: str) -> bool:
    return pwd_context.verify(plain, hashed)


def seed_admin_user():
    """
    Insert the default admin user on first run if no users exist.
    Override via environment variables:
      ADMIN_EMAIL    (default: admin@spotline.com)
      ADMIN_PASSWORD (default: 1234)
    """
    users = get_users_collection()
    if users.count_documents({}) == 0:
        email    = os.getenv("ADMIN_EMAIL",    "admin@spotline.com")
        password = os.getenv("ADMIN_PASSWORD", "1234")
        users.insert_one({
            "email":          email,
            "hashed_password": hash_password(password),
            "role":           "admin",
            "active":         True,
        })
        print(f"✓ Seeded admin user: {email}")
    else:
        print("✓ Users collection already populated — skipping seed")
