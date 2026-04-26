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
import certifi

load_dotenv()

MONGO_URI = os.getenv("MONGO_URI")
DB_NAME   = os.getenv("DB_NAME")

_client: MongoClient | None = None

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def get_db():
    global _client
    if _client is None:
        _client = MongoClient(MONGO_URI, tlsCAFile=certifi.where())
    return _client[DB_NAME]


def get_users_collection() -> Collection:
    return get_db()["users"]


def hash_password(plain: str) -> str:
    return pwd_context.hash(plain[:72])


def verify_password(plain: str, hashed: str) -> bool:
    return pwd_context.verify(plain, hashed)


def seed_admin_user():
    users = get_users_collection()
    if users.count_documents({}) == 0:
        email    = os.getenv("ADMIN_EMAIL")
        password = os.getenv("ADMIN_PASSWORD")
        users.insert_one({
            "email":          email,
            "hashed_password": hash_password(password),
            "role":           "admin",
            "active":         True,
        })
        print(f"✓ Seeded admin user: {email}")
    else:
        print("✓ Users collection already populated — skipping seed")
