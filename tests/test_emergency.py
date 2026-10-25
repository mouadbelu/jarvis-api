import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import pytest
from fastapi.testclient import TestClient
import main
from storage import Store

OWNER = "test-owner-token-with-very-long-entropy-123456"
RECOVERY = "Purple-lantern-glass-bird-October-2026"
BASE = "https://jarvis-api-production-82f7.up.railway.app"
BROWSER = {"Origin": BASE, "X-Jarvis-Request": "1"}
BEARER = {"Authorization": "Bearer " + OWNER}

@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(main, "store", Store(str(tmp_path / "private.sqlite3")))
    monkeypatch.setenv("JARVIS_ACCESS_TOKEN", OWNER)
    monkeypatch.setenv("JARVIS_PUBLIC_URL", BASE)
    return TestClient(main.app, base_url=BASE)

def owner_data():
    return {"owner_token": OWNER, "recovery_phrase": RECOVERY}

def test_session_has_secure_cookie(client):
    assert client.post("/api/auth/login", json={"token": OWNER}).status_code == 403
    response = client.post("/api/auth/login", headers=BROWSER, json={"token": OWNER})
    assert response.status_code == 200
    cookie = response.headers["set-cookie"].lower()
    assert "httponly" in cookie and "secure" in cookie and "samesite=strict" in cookie
    assert client.get("/api/history").status_code == 200

def test_emergency_lock_and_unlock(client):
    assert client.post("/api/auth/login", headers=BROWSER, json={"token": OWNER}).status_code == 200
    setup = client.post("/api/emergency/enroll", headers=BROWSER, json=owner_data())
    assert setup.status_code == 200, setup.text
    assert client.post("/api/emergency/lock", headers=BROWSER,
            json={**owner_data(), "confirmation": "WRONG"}).status_code == 422
    locked = client.post("/api/emergency/lock", headers=BROWSER,
            json={**owner_data(), "confirmation": "BLOCCA JARVIS"})
    assert locked.status_code == 200, locked.text
    assert client.get("/api/history", headers=BEARER).status_code == 423
    assert client.post("/api/auth/login", headers=BROWSER, json={"token": OWNER}).status_code == 423
    assert client.get("/recovery").status_code == 200
    unlocked = client.post("/api/emergency/unlock", headers=BROWSER, json=owner_data())
    assert unlocked.status_code == 200
    assert client.get("/api/history").status_code == 401

def test_emergency_data_cleanup(client):
    assert client.post("/api/emergency/enroll", headers=BROWSER, json=owner_data()).status_code == 200
    main.store.remember("demo", "private example")
    r = client.post("/api/emergency/wipe", headers=BROWSER,
                    json={**owner_data(), "confirmation": "CANCELLA TUTTO"})
    assert r.status_code == 200, r.text
    assert main.store.memories() == {}
    assert r.json()["external_keys_revoked"] is False
