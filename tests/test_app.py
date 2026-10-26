import os
import sys
from pathlib import Path

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import pytest
from fastapi.testclient import TestClient
import main
from storage import Store


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(main, 'store', Store(str(tmp_path/'db.sqlite3')))
    monkeypatch.setenv('JARVIS_ACCESS_TOKEN', 'test_secret_longer_than_twenty_four_chars')
    monkeypatch.delenv('GOOGLE_CLIENT_ID',raising=False)
    monkeypatch.delenv('GOOGLE_CLIENT_SECRET',raising=False)
    monkeypatch.delenv('JARVIS_PUBLIC_URL',raising=False)
    monkeypatch.delenv('JARVIS_TOKEN_KEY',raising=False)
    return TestClient(main.app)


def headers():
    return {'Authorization':'Bearer test_secret_longer_than_twenty_four_chars'}


def test_health_and_index_available_without_token(client):
    assert client.get('/health').json()['status']=='ok'
    assert '<title>Jarvis' in client.get('/').text
    assert client.get('/static/manifest.webmanifest').status_code == 200


def test_private_routes_protected_even_legacy(client):
    for route in ('/api/history','/api/memory','/api/briefing','/api/gmail/inbox'):
        assert client.get(route).status_code==401
    assert client.post('/ask',json={'prompt':'Ciao'}).status_code==401
    assert client.post('/api/chat',json={'text':'Ciao'}).status_code==401
    assert client.get('/api/history',headers={'Authorization':'Bearer wrong'}).status_code==401


def test_chat_saves_history_and_deletes(client,monkeypatch):
    async def provider(prompt,sys=None): return 'Risposta di test'
    monkeypatch.setattr(main, 'omnipotent_ask',provider)
    assert client.post('/api/chat',headers=headers(),json={'text':'Ciao'}).json()['reply']=='Risposta di test'
    h=client.get('/api/history',headers=headers()).json()['messages']
    assert [x['role'] for x in h]==['user','assistant']
    assert [x['content'] for x in h]==['Ciao','Risposta di test']
    assert client.delete('/api/history',headers=headers()).json()['ok'] is True
    assert client.get('/api/history',headers=headers()).json()['messages']==[]


def test_no_fake_reply_when_ai_unconfigured(client,monkeypatch):
    async def none(prompt,sys=None): return None
    monkeypatch.setattr(main,'omnipotent_ask',none)
    assert client.post('/api/chat',headers=headers(),json={'text':'Ciao'}).status_code==502
    assert client.get('/api/history',headers=headers()).json()['messages']==[]


def test_legacy_endpoint_now_authenticated(client,monkeypatch):
    async def provider(prompt,sys=None): return 'Sì, funziono.'
    monkeypatch.setattr(main,'omnipotent_ask',provider)
    assert client.post('/ask',headers=headers(),json={'prompt':'Ci sei?'}).json()['reply']=='Sì, funziono.'


def test_memory_crud(client):
    payload={'key':'lingua','value':'Italiano'}
    assert client.put('/api/memory',headers=headers(),json=payload).status_code==200
    assert client.get('/api/memory',headers=headers()).json()['memories']=={'lingua':'Italiano'}
    client.delete('/api/memory/lingua',headers=headers())
    assert client.get('/api/memory',headers=headers()).json()['memories']=={}


def test_memory_persistence_between_instances(tmp_path):
    path=str(tmp_path/'db.sqlite3')
    Store(path).remember('preferenza','Italia')
    assert Store(path).memories()=={'preferenza':'Italia'}


def test_mail_no_send_without_explicit_confirm(client,monkeypatch):
    monkeypatch.setattr(main.gmail_api,'connected',lambda store: True)
    async def fail_send(*args): raise AssertionError('No send without confirmation')
    monkeypatch.setattr(main.gmail_api,'send_message',fail_send)
    prepare=client.post('/api/gmail/prepare',headers=headers(),json={
        'to':'someone@example.com','subject':'Ciao','body':'Test email'})
    assert prepare.status_code==200
    uid=prepare.json()['draft_id']
    assert client.post('/api/gmail/send',headers=headers(),json={'draft_id':uid,'confirmation':'NO'}).status_code==403
    assert client.post('/api/gmail/send',json={'draft_id':uid,'confirmation':'INVIA'}).status_code==401


def test_mail_one_time_send(client,monkeypatch):
    monkeypatch.setattr(main.gmail_api,'connected',lambda store: True)
    sent=[]
    async def fake_send(store,recipient,subject,body):
        sent.append(recipient)
        return {'id':'sent-test-id'}
    monkeypatch.setattr(main.gmail_api,'send_message',fake_send)
    uid=client.post('/api/gmail/prepare',headers=headers(),json={
        'to':'someone@example.com','subject':'Prova','body':'Messaggio'}).json()['draft_id']
    payload={'draft_id':uid,'confirmation':'INVIA'}
    assert client.post('/api/gmail/send',headers=headers(),json=payload).json()['sent'] is True
    assert client.post('/api/gmail/send',headers=headers(),json=payload).status_code==409
    assert sent==['someone@example.com']


def test_draft_expiry_and_invalid_email(client,monkeypatch):
    monkeypatch.setattr(main.gmail_api,'connected',lambda store: True)
    assert client.post('/api/gmail/prepare',headers=headers(),json={
        'to':'evil@example.com\r\nBcc: bad@example.com','subject':'X','body':'Y'}).status_code==422
    uid=main.store.make_draft('someone@example.com','S','B')
    with main.store.db() as con:
        con.execute("UPDATE mail_drafts SET created_at='2024-01-01T00:00:00+00:00' WHERE id=?",(uid,))
    assert client.post('/api/gmail/send',headers=headers(),json={'draft_id':uid,'confirmation':'INVIA'}).status_code==409


def test_not_configured_server_fail_closed(client,monkeypatch):
    monkeypatch.delenv('JARVIS_ACCESS_TOKEN',raising=False)
    assert client.get('/api/history',headers=headers()).status_code==503


def test_mail_header_validation(client,monkeypatch):
    c=client
    monkeypatch.setattr(main.gmail_api,'connected',lambda _: True)
    r=c.post('/api/gmail/prepare',headers=headers(),json={'to':'person@example.org','subject':'bad\nheader','body':'Hi'})
    assert r.status_code==422
    r=c.post('/api/gmail/prepare',headers=headers(),json={'to':'evil@example.org\nBCC:someone@example.net','body':'Hi'})
    assert r.status_code==422
