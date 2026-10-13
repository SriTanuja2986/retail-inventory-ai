import sqlite3
from getpass import getpass
from pathlib import Path

from werkzeug.security import generate_password_hash

db_path = Path(__file__).resolve().parent / "inventory.db"

username = input("Username: ").strip()
role = input("Role (owner/staff): ").strip().lower()
password = getpass("Password (at least 12 characters): ")
confirmation = getpass("Confirm password: ")

if not username or len(username) > 100:
    raise SystemExit("Enter a username between 1 and 100 characters.")

if role not in {"owner", "staff"}:
    raise SystemExit("Role must be owner or staff.")

if len(password) < 12 or password != confirmation:
    raise SystemExit("Passwords must match and contain at least 12 characters.")

with sqlite3.connect(db_path) as connection:
    connection.execute("""
        CREATE TABLE IF NOT EXISTS users (
            username TEXT PRIMARY KEY,
            password_hash TEXT NOT NULL,
            role TEXT NOT NULL CHECK (role IN ('owner', 'staff'))
        )
    """)

    try:
        connection.execute(
            "INSERT INTO users VALUES (?, ?, ?)",
            (username, generate_password_hash(password), role)
        )
    except sqlite3.IntegrityError:
        raise SystemExit("That username already exists.")

print("Account created. Password stored as a hash.")