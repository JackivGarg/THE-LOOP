"""Password hashing and revocable cookie sessions; no tokens in localStorage."""
import hashlib
import hmac
import secrets
import time

from fastapi import HTTPException, Request

SESSION_COOKIE = "loop_session"
SESSION_SECONDS = 7 * 24 * 60 * 60


def hash_password(password):
    salt = secrets.token_hex(16)
    digest = hashlib.scrypt(password.encode(), salt=bytes.fromhex(salt), n=16384, r=8, p=1).hex()
    return f"scrypt${salt}${digest}"


def verify_password(password, stored):
    try:
        algorithm, salt, digest = stored.split("$")
        if algorithm != "scrypt":
            return False
        computed = hashlib.scrypt(password.encode(), salt=bytes.fromhex(salt), n=16384, r=8, p=1).hex()
        return hmac.compare_digest(computed, digest)
    except ValueError:
        return False


def session_hash(token):
    return hashlib.sha256(token.encode()).hexdigest()


def create_session(db, user_id, response, secure):
    token = secrets.token_urlsafe(32)
    db.execute("DELETE FROM sessions WHERE expires_at < ?", (time.time(),))
    db.execute("INSERT INTO sessions VALUES (?, ?, ?)", (session_hash(token), user_id, time.time() + SESSION_SECONDS))
    response.set_cookie(SESSION_COOKIE, token, max_age=SESSION_SECONDS, httponly=True,
                        secure=secure, samesite="lax", path="/api")


def current_user(request: Request):
    token = request.cookies.get(SESSION_COOKIE, "")
    user = request.app.state.db.one(
        "SELECT u.id, u.email, u.name, u.created_at FROM sessions s JOIN users u ON u.id=s.user_id WHERE s.token_hash=? AND s.expires_at>?",
        (session_hash(token), time.time()),
    )
    if not user:
        raise HTTPException(401, "Sign in to continue.")
    return user


def throttle(db, bucket, *, limit=8, seconds=60):
    """Atomic local throttle for login/signup attempts, including failed attempts."""
    now = time.time()
    with db.connection() as connection:
        connection.execute("BEGIN IMMEDIATE")
        connection.execute("DELETE FROM rate_limits WHERE reset_at < ?", (now,))
        row = connection.execute("SELECT * FROM rate_limits WHERE bucket=?", (bucket,)).fetchone()
        if row and row["attempts"] >= limit:
            raise HTTPException(429, "Too many attempts. Try again in a minute.")
        connection.execute(
            "INSERT INTO rate_limits VALUES (?, 1, ?) ON CONFLICT(bucket) DO UPDATE SET attempts=attempts+1",
            (bucket, now + seconds),
        )
