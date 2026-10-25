"""Voice page regression tests: dedicated UI, authentication and isolation."""
import os
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pytest
from fastapi.testclient import TestClient
import main
from storage import Store


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(main, 'store', Store(str(tmp_path / 'voice.sqlite3')))
    monkeypatch.setenv('JARVIS_ACCESS_TOKEN', 'test_voice_token_that_is_at_least_24_chars')
    return TestClient(main.app)


def test_voice_section_is_separate_and_assets_load(client):
    html = client.get('/').text
    assert 'id="voice"' in html
    assert 'data-page="voice"' in html
    assert 'id="voice-mic"' in html
    assert 'id="voice-repeat"' in html
    assert '/static/voice.js' in html
    assert client.get('/static/voice.js').status_code == 200
    assert "conversation: 'voice'" in client.get('/static/voice.js').text
    assert "jarvis:pagechange" in client.get('/static/app.js').text


def test_separate_voice_history_respects_auth(client, monkeypatch):
    async def answer(prompt, sys=None):
        return 'Ciao, ti ascolto.'
    monkeypatch.setattr(main, 'omnipotent_ask', answer)
    body = {'text': 'Ciao Jarvis', 'conversation': 'voice'}
    assert client.post('/api/chat', json=body).status_code == 401
    headers = {'Authorization': 'Bearer test_voice_token_that_is_at_least_24_chars'}
    response = client.post('/api/chat', headers=headers, json=body)
    assert response.status_code == 200
    assert response.json()['reply'] == 'Ciao, ti ascolto.'
    voice = client.get('/api/history?conversation=voice', headers=headers).json()['messages']
    written = client.get('/api/history?conversation=main', headers=headers).json()['messages']
    assert len(voice) == 2
    assert written == []


def test_voice_recognition_has_safe_controls(client):
    js = client.get('/static/voice.js').text
    assert 'recognizer.stop()' in js
    assert 'cancelRecognition()' in js
    assert "document.hidden" in js
    assert 'SpeechSynthesisUtterance' in js
    assert 'credentials:' not in js  # uses authenticated shared API wrapper
