"""Authenticated Jarvis sessions and browser defenses.

No raw session value is persisted on the server: only a SHA256 digest.
The long-lived owner token remains server-side in Railway variables.
"""
import hashlib
import os
import secrets
import time

from fastapi import HTTPException

COOKIE_NAME = "__Host-jarvis_session"
SESSION_SECONDS = 8 * 60 * 60
WINDOW_SECONDS = 15 * 60
MAX_FAILED_ATTEMPTS = 6


def digest(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def token_fingerprint() -> str:
    return digest(os.getenv("JARVIS_ACCESS_TOKEN", ""))


def initialize(store):
    with store.db() as con:
        con.executescript("""
        CREATE TABLE IF NOT EXISTS auth_sessions (
            digest TEXT PRIMARY KEY,
            token_fingerprint TEXT NOT NULL,
            created_at INTEGER NOT NULL,
            expires_at INTEGER NOT NULL
        );
        CREATE INDEX IF NOT EXISTS auth_sessions_expires ON auth_sessions(expires_at);
        CREATE TABLE IF NOT EXISTS auth_failures (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            peer_digest TEXT NOT NULL,
            created_at INTEGER NOT NULL
        );
        CREATE INDEX IF NOT EXISTS auth_failures_peer ON auth_failures(peer_digest, created_at);
        """)


def _peer_digest(request):
    # Do not trust arbitrary forwarded headers supplied by callers.
    address = request.client.host if request.client else "unknown"
    return digest("jarvis-login:" + address)


def login(store, request, token):
    configured = os.getenv("JARVIS_ACCESS_TOKEN", "")
    if len(configured) < 24:
        raise HTTPException(503, "Accesso non configurato su Railway.")
    initialize(store)
    now = int(time.time())
    peer = _peer_digest(request)
    refused = False
    throttled = False
    session = None
    with store.db() as con:
        con.execute("DELETE FROM auth_sessions WHERE expires_at<=?", (now,))
        con.execute("DELETE FROM auth_failures WHERE created_at<=?", (now - WINDOW_SECONDS,))
        n = con.execute(
            "SELECT COUNT(*) AS n FROM auth_failures WHERE peer_digest=? AND created_at>?",
            (peer, now - WINDOW_SECONDS),
        ).fetchone()["n"]
        if n >= MAX_FAILED_ATTEMPTS:
            throttled = True
        elif not (
            len(token) == len(configured)
            and secrets.compare_digest(token, configured)
        ):
            con.execute(
                "INSERT INTO auth_failures(peer_digest,created_at) VALUES(?,?)",
                (peer, now),
            )
            refused = True
        else:
            con.execute("DELETE FROM auth_failures WHERE peer_digest=?", (peer,))
            session = secrets.token_urlsafe(48)
            con.execute(
                "INSERT INTO auth_sessions(digest,token_fingerprint,created_at,expires_at)"
                " VALUES(?,?,?,?)",
                (digest(session), token_fingerprint(), now, now + SESSION_SECONDS),
            )
    if throttled:
        raise HTTPException(
            429, "Troppi tentativi di accesso. Riprova più tardi.",
            headers={"Retry-After": str(WINDOW_SECONDS)},
        )
    if refused:
        raise HTTPException(401, "Credenziali non valide.")
    return session


def session_exists(store, raw):
    if not raw or len(raw) > 256:
        return False
    initialize(store)
    now = int(time.time())
    with store.db() as con:
        row = con.execute(
            "SELECT expires_at,token_fingerprint FROM auth_sessions WHERE digest=?",
            (digest(raw),),
        ).fetchone()
    return bool(
        row and row["expires_at"] > now
        and secrets.compare_digest(row["token_fingerprint"], token_fingerprint())
    )


def revoke(store, raw):
    if not raw or len(raw) > 256:
        return
    initialize(store)
    with store.db() as con:
        con.execute("DELETE FROM auth_sessions WHERE digest=?", (digest(raw),))


def revoke_all(store):
    initialize(store)
    with store.db() as con:
        con.execute("DELETE FROM auth_sessions")


def enforce_origin(request):
    """Require explicit same-origin browser requests for cookie state changes."""
    if request.headers.get("x-jarvis-request") != "1":
        raise HTTPException(403, "Protezione anti-CSRF: intestazione mancante.")
    expected = os.getenv("JARVIS_PUBLIC_URL", "").rstrip("/")
    if not expected:
        expected = str(request.base_url).rstrip("/")
    origin = request.headers.get("origin", "").rstrip("/")
    if not origin or not secrets.compare_digest(origin, expected):
        raise HTTPException(403, "Origine della richiesta non autorizzata.")


def harden_response(request, response):
    headers = response.headers
    headers["X-Content-Type-Options"] = "nosniff"
    headers["X-Frame-Options"] = "DENY"
    headers["Referrer-Policy"] = "no-referrer"
    headers["Permissions-Policy"] = (
        "camera=(), geolocation=(), payment=(), usb=(), microphone=(self)"
    )
    headers["Content-Security-Policy"] = (
        "default-src 'self'; script-src 'self'; style-src 'self'; "
        "img-src 'self' data:; font-src 'self'; connect-src 'self'; "
        "worker-src 'self'; object-src 'none'; base-uri 'none'; "
        "frame-ancestors 'none'; form-action 'self'; upgrade-insecure-requests"
    )
    headers["Cross-Origin-Resource-Policy"] = "same-origin"
    if request.url.scheme == "https" or request.headers.get("x-forwarded-proto") == "https":
        headers["Strict-Transport-Security"] = "max-age=31536000"
    if request.url.path.startswith("/api/") or request.url.path == "/ask":
        headers["Cache-Control"] = "no-store"
        headers["Pragma"] = "no-cache"
    return response
