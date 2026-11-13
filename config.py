"""Database settings. Values come from the .env file (see .env.example)."""
import os
from dotenv import load_dotenv

load_dotenv()

DB_CONFIG = {
    "host": os.getenv("DB_HOST", "localhost"),
    "port": int(os.getenv("DB_PORT", "3306")),
    "user": os.getenv("DB_USER", "root"),
    "password": os.getenv("DB_PASSWORD", ""),
    "charset": "utf8mb4",
    "collation": "utf8mb4_unicode_ci",
}
DB_NAME = os.getenv("DB_NAME", "placement_db")
SECRET_KEY = os.getenv("SECRET_KEY", "dev-secret-change-me")
