"""Regression tests: Jarvis detects faults and only performs bounded safe recoveries."""
import asyncio
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import httpx
import pytest
from fastapi.testclient import TestClient

import main
import provider_omnipotent
import self_healing
from storage import Store


@pytest.fixture(autouse=True)
def clean_breakers():
    self_healing.reset_for_tests()
    yield
    self_healing.reset_for_tests()


def test_credit_exhaustion_pauses_only_offending_provider(monkeypatch):
    monkeypatch.setenv('JARVIS_OPENAI_KEY', 'fake-test-key')
    clock = [100.0]
    monkeypatch.setattr(self_healing.time, 'monotonic', lambda: clock[0])
    assert self_healing.may_try('OpenAI')
    self_healing.provider_failed('OpenAI', 429, 'credit_balance_exhausted')
    assert not self_healing.may_try('OpenAI')
    assert self_healing.may_try('Gemini')
    snap = self_healing.snapshot()
    assert snap['providers']['OpenAI']['status'] == 'pausa_automatica'
    assert snap['providers']['OpenAI']['retry_in_seconds'] >= 21590
    clock[0] += 21601
    assert self_healing.may_try('OpenAI')
    self_healing.provider_ok('OpenAI')
    assert self_healing.snapshot()['providers']['OpenAI']['status'] == 'online'


def test_transient_retry_then_recovery(monkeypatch):
    clock = [20.0]
    monkeypatch.setattr(self_healing.time, 'monotonic', lambda: clock[0])
    self_healing.provider_failed('Gemini', 503)
    assert not self_healing.may_try('Gemini')
    clock[0] += 20
    assert self_healing.may_try('Gemini')
    self_healing.provider_ok('Gemini')
    assert any(e['kind'] == 'recovered' for e in self_healing.snapshot()['events'])


def test_db_integrity_check_never_deletes_personal_data(tmp_path):
    store = Store(str(tmp_path / 'health.sqlite3'))
    store.remember('important', 'Do not delete')
    store.add_message('main', 'user', 'Ciao')
    assert self_healing.check_database(store)
    health = self_healing.snapshot()
    assert health['database'] == 'ok'
    assert store.memories()['important'] == 'Do not delete'
    assert store.history('main')[0]['content'] == 'Ciao'


def test_database_failure_does_not_delete_or_migrate(tmp_path):
    store = Store(str(tmp_path / 'healthy.sqlite3'))
    class BrokenStore:
        def db(self):
            raise OSError('not available')
    assert self_healing.check_database(BrokenStore()) is False
    assert self_healing.snapshot()['database'] == 'non_disponibile'
    assert store.memories() == {}


def test_diagnostics_private_and_scrubbed(tmp_path, monkeypatch):
    token = 'a-secret-token-much-longer-than-24-characters'
    monkeypatch.setattr(main, 'store', Store(str(tmp_path / 'private.sqlite3')))
    monkeypatch.setenv('JARVIS_ACCESS_TOKEN', token)
    monkeypatch.setenv('JARVIS_GEMINI_KEY', 'gemini-test-key-never-expose')
    client = TestClient(main.app)
    assert client.get('/api/diagnostics').status_code == 401
    result = client.get('/api/diagnostics', headers={'Authorization': 'Bearer ' + token})
    assert result.status_code == 200
    data = result.json()
    assert data['database'] == 'ok'
    assert data['providers']['Gemini']['status'] == 'unknown'
    assert data['capabilities']['can_edit_code_or_secrets'] is False
    raw = json.dumps(data)
    assert token not in raw and 'gemini-test-key-never-expose' not in raw


def test_openai_credit_failure_falls_back_to_gemini_once(monkeypatch):
    monkeypatch.setenv('JARVIS_OPENAI_KEY', 'not-real-openai')
    monkeypatch.setenv('JARVIS_GEMINI_KEY', 'not-real-gemini')
    monkeypatch.delenv('JARVIS_CLAUDE_KEY', raising=False)
    called = {'openai': 0, 'gemini': 0}
    def handle(request):
        if 'openai.com' in str(request.url):
            called['openai'] += 1
            return httpx.Response(429, json={'error': {'code': 'credit_balance_exhausted'}})
        called['gemini'] += 1
        return httpx.Response(200, json={'candidates': [{'content': {'parts': [{'text': 'Sono attivo.'}]}}]})
    transport = httpx.MockTransport(handle)
    actual = httpx.AsyncClient
    monkeypatch.setattr(provider_omnipotent.httpx, 'AsyncClient',
                        lambda *a, **kw: actual(transport=transport, **kw))
    first = asyncio.run(provider_omnipotent.omnipotent_ask('Ciao'))
    second = asyncio.run(provider_omnipotent.omnipotent_ask('Ancora'))
    assert first == second == 'Sono attivo.'
    assert called['openai'] == 1  # circuit breaker avoids repeated failed paid requests
    assert called['gemini'] == 2


def test_http_503_retried_once_not_indefinitely(monkeypatch):
    monkeypatch.setenv('JARVIS_OPENAI_KEY', 'fake-key')
    monkeypatch.delenv('JARVIS_GEMINI_KEY', raising=False)
    monkeypatch.delenv('JARVIS_CLAUDE_KEY', raising=False)
    attempts = [0]
    def handle(request):
        attempts[0] += 1
        if attempts[0] == 1:
            return httpx.Response(503, json={'error': {'code': 'server_busy'}})
        return httpx.Response(200, json={'choices': [{'message': {'content': 'Recuperato'}}]})
    transport = httpx.MockTransport(handle)
    actual = httpx.AsyncClient
    monkeypatch.setattr(provider_omnipotent.httpx, 'AsyncClient',
                        lambda *a, **kw: actual(transport=transport, **kw))
    answer = asyncio.run(provider_omnipotent.omnipotent_ask('Test'))
    assert answer == 'Recuperato'
    assert attempts[0] == 2
