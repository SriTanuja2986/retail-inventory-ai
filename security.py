import os
import secrets
import sqlite3
from datetime import timedelta
from pathlib import Path

from flask import (
    abort, redirect, render_template_string, request, session
)
from flask_wtf.csrf import CSRFProtect
from werkzeug.security import check_password_hash


def register_security(app, db_path):
    # Preserve the local session key across application restarts.
    key_file = Path(db_path).parent / ".session_key"

    if os.environ.get("SECRET_KEY"):
        app.secret_key = os.environ["SECRET_KEY"]
    else:
        if not key_file.exists():
            key_file.write_text(
                secrets.token_hex(32), encoding="utf-8"
            )
        app.secret_key = key_file.read_text(
            encoding="utf-8"
        ).strip()

    app.config.update(
        SESSION_COOKIE_HTTPONLY=True,
        SESSION_COOKIE_SAMESITE="Lax",
        SESSION_COOKIE_SECURE=os.environ.get("HTTPS_ENABLED") == "1",
        PERMANENT_SESSION_LIFETIME=timedelta(minutes=30)
    )

    CSRFProtect(app)

    with sqlite3.connect(db_path) as connection:
        connection.execute("""
            CREATE TABLE IF NOT EXISTS users (
                username TEXT PRIMARY KEY,
                password_hash TEXT NOT NULL,
                role TEXT NOT NULL CHECK (role IN ('owner', 'staff'))
            )
        """)

    @app.before_request
    def protect_routes():
        if request.endpoint in {"login", "static"}:
            return

        username = session.get("username")

        with sqlite3.connect(db_path) as connection:
            user = connection.execute(
                "SELECT role FROM users WHERE username = ?",
                (username,)
            ).fetchone()

        if not user:
            session.clear()
            return redirect("/login")

        # Staff may view inventory and record sales.
        owner_only = {"add_product", "import_sales", "forecast"}
        if request.endpoint in owner_only and user[0] != "owner":
            abort(403, description="Only the owner can access this feature.")

    @app.route("/login", methods=["GET", "POST"])
    def login():
        error = ""

        if request.method == "POST":
            username = request.form.get("username", "").strip()
            password = request.form.get("password", "")

            with sqlite3.connect(db_path) as connection:
                user = connection.execute("""
                    SELECT password_hash
                    FROM users WHERE username = ?
                """, (username,)).fetchone()

            if user and check_password_hash(user[0], password):
                session.clear()
                session["username"] = username
                session.permanent = True
                return redirect("/")

            error = "Invalid username or password."

        return render_template_string("""
            <!DOCTYPE html>
            <html>
            <head><title>Retail Inventory Login</title></head>
            <body style="font-family:Arial;max-width:450px;margin:70px auto">
                <h1>Retail Inventory AI</h1>
                <h2>Secure Login</h2>
                <p>{{ error }}</p>
                <form method="post">
                    <input type="hidden" name="csrf_token"
                           value="{{ csrf_token() }}">
                    <p><input name="username"
                              placeholder="Username" required></p>
                    <p><input type="password" name="password"
                              placeholder="Password" required></p>
                    <button type="submit">Login</button>
                </form>
            </body>
            </html>
        """, error=error)

    @app.route("/logout", methods=["POST"])
    def logout():
        session.clear()
        return redirect("/login")