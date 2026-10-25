"""Server-side break-glass controls.

These controls mitigate stolen sessions and runaway application features.
They do not survive compromise of Railway/GitHub credentials or host privileges.
The recovery phrase is never stored in plaintext.
"""
import hashlib
import hmac
import os
import secrets
from datetime import datetime, timezone

from fastapi import HTTPException

ITERATIONS = 600_000
SALT_BYTES = 24
CONFIRM_LOCK = "BLOCCA JARVIS"
CONFIRM_WIPE = "CANCELLA TUTTO"


def _init(store):
    with store.db() as db:
        db.execute("""
            CREATE TABLE IF NOT EXISTS emergency_control (
                id INTEGER PRIMARY KEY CHECK(id=1),
                salt TEXT NOT NULL,
                verifier TEXT NOT NULL,
                locked INTEGER NOT NULL DEFAULT 0,
                changed_at TEXT NOT NULL
            )
        """)


def _owner_token_valid(value):
    owner_token = os.getenv("JARVIS_ACCESS_TOKEN", "")
    return bool(
        len(owner_token) >= 24
        and len(value) == len(owner_token)
        and secrets.compare_digest(value, owner_token)
    )


def _phrase_hash(phrase, salt):
    return hashlib.pbkdf2_hmac(
        "sha256", phrase.encode("utf-8"), bytes.fromhex(salt), ITERATIONS
    ).hex()


def _verify_phrase(row, phrase):
    if not isinstance(phrase, str) or len(phrase) < 20 or len(phrase) > 256:
        return False
    try:
        return hmac.compare_digest(row["verifier"], _phrase_hash(phrase, row["salt"]))
    except (ValueError, TypeError):
        return False


def _row(store):
    _init(store)
    with store.db() as db:
        return db.execute("SELECT * FROM emergency_control WHERE id=1").fetchone()


def status(store):
    # If storage fails, callers must fail closed rather than assume unlocked.
    row = _row(store)
    return {"configured": bool(row), "locked": bool(row["locked"]) if row else False}


def assert_unlocked(store):
    if status(store)["locked"]:
        raise HTTPException(423, "Jarvis è in BLOCCO DI EMERGENZA.")


def _validate_owner_and_phrase(owner_token, phrase, row):
    if not _owner_token_valid(owner_token) or not _verify_phrase(row, phrase):
        raise HTTPException(403, "Verifica proprietario non riuscita.")


def enroll(store, owner_token, phrase):
    if not _owner_token_valid(owner_token):
        raise HTTPException(403, "Verifica proprietario non riuscita.")
    if not isinstance(phrase, str) or not 20 <= len(phrase) <= 256:
        raise HTTPException(422, "Usa una frase di recupero di 20-256 caratteri.")
    if phrase == owner_token or phrase.strip() != phrase:
        raise HTTPException(422, "Scegli una frase diversa dal token e senza spazi ai bordi.")
    if len(set(phrase)) < 8:
        raise HTTPException(422, "La frase è troppo prevedibile.")
    _init(store)
    salt = secrets.token_hex(SALT_BYTES)
    verifier = _phrase_hash(phrase, salt)
    stamp = datetime.now(timezone.utc).isoformat()
    with store.db() as db:
        existing = db.execute("SELECT 1 FROM emergency_control WHERE id=1").fetchone()
        if existing:
            raise HTTPException(409, "Protezione già attivata. Non sovrascrivibile dall'app.")
        db.execute(
            "INSERT INTO emergency_control(id,salt,verifier,locked,changed_at) "
            "VALUES(1,?,?,0,?)", (salt, verifier, stamp)
        )
    return {"configured": True, "locked": False}


def _check_action(store, owner_token, phrase, typed, expected):
    row = _row(store)
    if not row:
        raise HTTPException(409, "Attiva prima il protocollo di emergenza.")
    _validate_owner_and_phrase(owner_token, phrase, row)
    if typed != expected:
        raise HTTPException(422, "Conferma testuale non valida.")
    return row


def lock(store, owner_token, phrase, typed):
    _check_action(store, owner_token, phrase, typed, CONFIRM_LOCK)
    with store.db() as db:
        db.execute(
            "UPDATE emergency_control SET locked=1, changed_at=? WHERE id=1",
            (datetime.now(timezone.utc).isoformat(),),
        )
        # Server sessions are destroyed, including the initiating device.
        db.execute("DELETE FROM auth_sessions")
    return {"locked": True, "sessions_revoked": True}


def unlock(store, owner_token, phrase):
    row = _row(store)
    if not row:
        raise HTTPException(409, "Protezione non attivata.")
    _validate_owner_and_phrase(owner_token, phrase, row)
    with store.db() as db:
        db.execute(
            "UPDATE emergency_control SET locked=0, changed_at=? WHERE id=1",
            (datetime.now(timezone.utc).isoformat(),),
        )
        db.execute("DELETE FROM auth_sessions")
    return {"locked": False, "sessions_revoked": True}


def wipe(store, owner_token, phrase, typed):
    _check_action(store, owner_token, phrase, typed, CONFIRM_WIPE)
    # Keep recovery verifier so the owner can unlock after local data deletion.
    # Failure rolls back the operation; no partial wipe is declared complete.
    with store.db() as db:
        db.execute("UPDATE emergency_control SET locked=1, changed_at=? WHERE id=1",
                   (datetime.now(timezone.utc).isoformat(),))
        for table in (
            "messages", "memories", "secrets", "mail_drafts",
            "growth_profile", "growth_tasks", "growth_ideas", "auth_sessions",
        ):
            db.execute('DELETE FROM "' + table + '"')
    return {
        "locked": True,
        "local_data_deleted": True,
        "sessions_revoked": True,
        "external_keys_revoked": False,
        "backups_deleted": False,
    }
