"""Regression tests for private, deterministic chat updates."""
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import pytest
from fastapi.testclient import TestClient

import main
import assistant_briefing
from storage import Store


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(main, 'store', Store(str(tmp_path/'briefings.sqlite3')))
    monkeypatch.setenv('JARVIS_ACCESS_TOKEN', 'a-long-test-token-never-used-in-production')
    return TestClient(main.app)


def _headers():
    return {'Authorization': 'Bearer a-long-test-token-never-used-in-production'}


def test_classification_avoids_unrelated_chats():
    assert assistant_briefing.classify('dammi qualche aggiornamento') == 'overview'
    assert assistant_briefing.classify('Controlla le mie email') == 'mail'
    assert assistant_briefing.classify('Scrivimi una poesia sulle email') is None


def test_personal_update_without_gmail(client, monkeypatch):
    monkeypatch.setattr(assistant_briefing.gmail_api, 'connected', lambda store: False)
    async def never_call_ai(prompt, sys=None):
        raise AssertionError('Do not call external AI for private briefing')
    monkeypatch.setattr(main, 'omnipotent_ask', never_call_ai)
    result = client.post('/api/chat', headers=_headers(), json={'text': 'dammi qualche aggiornamento'})
    assert result.status_code == 200
    assert 'Gmail non è ancora collegato' in result.json()['reply']
    assert len(client.get('/api/history', headers=_headers()).json()['messages']) == 2


def test_personal_update_reads_consented_inbox_without_ai(client, monkeypatch):
    monkeypatch.setattr(assistant_briefing.gmail_api, 'connected', lambda store: True)
    async def fake_inbox(store):
        return {'unread': 3, 'messages': [
            {'from': 'Agenzia@example.org', 'subject': 'Risposta candidatura', 'snippet': 'Controlla allegato'},
        ]}
    monkeypatch.setattr(assistant_briefing.gmail_api, 'inbox', fake_inbox)
    async def never_call_ai(prompt, sys=None):
        raise AssertionError('Email subjects must not be sent to LLM')
    monkeypatch.setattr(main, 'omnipotent_ask', never_call_ai)
    result = client.post('/api/chat', headers=_headers(), json={'text': 'dammi qualche aggiornamento'})
    assert result.status_code == 200
    assert '3 messaggi non letti' in result.json()['reply']
    assert 'Risposta candidatura' in result.json()['reply']
