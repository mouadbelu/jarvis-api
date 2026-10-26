"""Regression checks for full-duplex hands-free voice and WebSocket protections."""
import json
from pathlib import Path
import sys

import pytest
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import main
import live_voice
from storage import Store


@pytest.fixture
def client(monkeypatch, tmp_path):
    monkeypatch.setenv('JARVIS_ACCESS_TOKEN', 'a_fake_long_test_access_token_12345678')
    monkeypatch.setenv('JARVIS_GEMINI_KEY', 'fake_gemini_key_for_tests')
    monkeypatch.delenv('JARVIS_PUBLIC_URL', raising=False)
    monkeypatch.setattr(main, 'store', Store(str(tmp_path / 'voice.sqlite3')))
    return TestClient(main.app)


def test_live_page_has_auto_start_and_exit(client):
    page = client.get('/').text
    assert 'id="live-exit"' in page
    assert '/static/live-client.js' in page
    js = client.get('/static/live-client.js').text
    assert "ev.detail.name === 'voice'" in js
    assert "void startLive()" in js
    assert "visibilitychange" in js
    assert "pagehide" in js
    assert "WebSocket" in js
    assert 'getUserMedia' in js
    assert 'sessionStorage.setItem' not in js
    assert 'JARVIS_GEMINI_KEY' not in js


def test_live_websocket_anonymous_denied(client):
    with pytest.raises(WebSocketDisconnect) as err:
        with client.websocket_connect('/api/live/voice', headers={'origin': 'https://testserver'}):
            pass
    assert err.value.code == 4403


def test_live_websocket_wrong_origin_denied(client):
    login = client.post('/api/auth/login',
                        json={'token': 'a_fake_long_test_access_token_12345678'},
                        headers={'Origin': 'http://testserver', 'X-Jarvis-Request': '1'})
    assert login.status_code == 200
    with pytest.raises(WebSocketDisconnect) as err:
        with client.websocket_connect('/api/live/voice', headers={'origin':'https://evil.example'}):
            pass
    assert err.value.code == 4403


def test_gemini_live_model_and_safety_instructions(monkeypatch):
    monkeypatch.delenv('JARVIS_GEMINI_LIVE_MODEL', raising=False)
    setup = live_voice.setup_message()['setup']
    assert setup['model'] == 'models/gemini-3.8-live'
    assert setup['generationConfig']['responseModalities'] == ['AUDIO']
    assert 'NON salutare' in setup['systemInstruction']['parts'][0]['text']
    assert 'JARVIS_GEMINI_KEY' not in json.dumps(setup)


def test_event_filter_only_speech_and_audio():
    raw = json.dumps({
        'serverContent': {
            'interrupted': True,
            'inputTranscription': {'text': 'Sono qui'},
            'outputTranscription': {'text': 'Ti ascolto'},
            'modelTurn': {'parts': [{'inlineData': {'data': 'AAACAw=='}}]},
            'turnComplete': True,
        },
        'toolCall': {'functionCalls': [{'name': 'delete_database'}]},
    })
    values = live_voice.safe_live_message(raw)
    assert {'interrupted': True} in values
    assert {'input': 'Sono qui'} in values
    assert {'output': 'Ti ascolto'} in values
    assert {'turnComplete': True} in values
    assert {'audio': 'AAACAw=='} in values
    assert all('toolCall' not in x for x in values)


def test_invalid_model_rejected(monkeypatch):
    monkeypatch.setenv('JARVIS_GEMINI_LIVE_MODEL', '../../malicious')
    with pytest.raises(ValueError):
        live_voice.setup_message()


def test_session_limits_are_bounded():
    assert live_voice.MAX_SESSION_SECONDS <= 20*60
    assert live_voice.MAX_PCM_FRAME <= 16384
    assert live_voice.MAX_AUDIO_RESPONSE <= 500000
