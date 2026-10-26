"""Natural voice, private audio and non-repeating greeting regression tests."""
from pathlib import Path
import sys

import pytest
from fastapi.testclient import TestClient
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))

import main
import natural_voice
from greeting_style import clean_repeated_greeting
from storage import Store


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(main, 'store', Store(str(tmp_path/'tts.sqlite3')))
    monkeypatch.setenv('JARVIS_ACCESS_TOKEN', 'very_long_private_token_for_tests_only_1234')
    return TestClient(main.app)


def auth():
    return {'Authorization': 'Bearer very_long_private_token_for_tests_only_1234'}


def test_repeated_greeting_removed():
    assert clean_repeated_greeting('Buongiorno Moed, ecco la risposta.', 4) == 'Ecco la risposta.'
    assert clean_repeated_greeting('Ciao, posso aiutarti.', 0) == 'Ciao, posso aiutarti.'
    assert clean_repeated_greeting('Sono pronto.', 9) == 'Sono pronto.'


def test_speech_endpoint_authenticated_and_never_cached(client, monkeypatch):
    assert client.post('/api/voice/speak', json={'text':'Ciao'}).status_code == 401
    async def voice(text, speaker):
        assert text == 'Sono qui, ti ascolto'
        assert speaker == 'Orus'
        return b'RIFF' + b'\x00\x00\x00\x00WAVE'+b'fake-audio'
    monkeypatch.setattr(main, 'create_voice', voice)
    result = client.post('/api/voice/speak', headers=auth(),
                         json={'text':'Sono qui, ti ascolto'})
    assert result.status_code == 200
    assert result.headers['content-type'].startswith('audio/wav')
    assert result.headers['cache-control'] == 'no-store'
    assert main.store.history() == []


def test_tts_invalid_voice_rejected(client, monkeypatch):
    async def fake(text, speaker):
        raise ValueError('Invalid voice')
    monkeypatch.setattr(main, 'create_voice', fake)
    assert client.post('/api/voice/speak', headers=auth(),
                       json={'text':'ciao', 'voice':'invalid'}).status_code == 422


def test_tts_unavailable_uses_safe_http_response(client, monkeypatch):
    async def fake(text, speaker):
        raise natural_voice.VoiceUnavailable('service unavailable')
    monkeypatch.setattr(main, 'create_voice', fake)
    r = client.post('/api/voice/speak', headers=auth(), json={'text':'Ciao'})
    assert r.status_code == 503
    assert 'service unavailable' not in r.text


def test_natural_voice_model_is_listed(monkeypatch):
    monkeypatch.delenv('JARVIS_GEMINI_TTS_MODEL', raising=False)
    assert natural_voice._model() == 'gemini-3.8-flash-lite-tts'
