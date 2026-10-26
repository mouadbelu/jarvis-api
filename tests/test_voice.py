"""iPhone voice input must stay protected and never persist raw audio."""
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from fastapi.testclient import TestClient
import pytest
import main
from storage import Store


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(main, 'store', Store(str(tmp_path / 'voice.sqlite3')))
    monkeypatch.setenv('JARVIS_ACCESS_TOKEN', 'test_voice_token_more_than_twenty_four_characters')
    return TestClient(main.app)


def auth_headers():
    return {'Authorization': 'Bearer test_voice_token_more_than_twenty_four_characters',
            'Content-Type': 'audio/mp4'}


def test_voice_endpoint_denies_anonymous_upload(client):
    response = client.post('/api/voice/transcribe', content=b'0' * 256,
                           headers={'Content-Type': 'audio/mp4'})
    assert response.status_code == 401


def test_voice_endpoint_validates_media_format(client):
    response = client.post('/api/voice/transcribe', content=b'0' * 256,
                           headers={'Authorization': auth_headers()['Authorization'],
                                    'Content-Type': 'text/plain'})
    assert response.status_code == 415


def test_voice_endpoint_rejects_empty_recording(client):
    response = client.post('/api/voice/transcribe', content=b'12', headers=auth_headers())
    assert response.status_code == 422


def test_voice_endpoint_transcribes_without_storing_raw_audio(client, monkeypatch):
    audio = b'\x01' * 800
    async def fake_transcribe(body, mime):
        assert body == audio
        assert mime == 'audio/mp4'
        return 'Ciao Jarvis, sei pronto?'
    monkeypatch.setattr(main, 'transcribe_audio', fake_transcribe)
    r = client.post('/api/voice/transcribe', content=audio, headers=auth_headers())
    assert r.status_code == 200
    assert r.json() == {'text': 'Ciao Jarvis, sei pronto?'}
    history = client.get('/api/history', headers={
        'Authorization': auth_headers()['Authorization'],
    }).json()
    assert history['messages'] == []


def test_voice_endpoint_reports_unavailable_transcriber(client, monkeypatch):
    async def unavailable(body, mime):
        return None
    monkeypatch.setattr(main, 'transcribe_audio', unavailable)
    r = client.post('/api/voice/transcribe', content=b'2' * 512, headers=auth_headers())
    assert r.status_code == 503
