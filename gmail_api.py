"""Gmail OAuth2 integration: explicit user consent and explicit send confirmation."""
import base64
import json
import os
import time
from email.message import EmailMessage
from urllib.parse import urlencode

import httpx
from cryptography.fernet import Fernet, InvalidToken

SCOPES = 'https://www.googleapis.com/auth/gmail.readonly https://www.googleapis.com/auth/gmail.send'


def configured():
    return all(os.getenv(k) for k in ('GOOGLE_CLIENT_ID','GOOGLE_CLIENT_SECRET','JARVIS_PUBLIC_URL','JARVIS_TOKEN_KEY'))


def redirect_uri():
    return os.environ['JARVIS_PUBLIC_URL'].rstrip('/') + '/api/gmail/callback'


def authorization_url(state):
    return 'https://accounts.google.com/o/oauth2/v2/auth?' + urlencode({
        'client_id':os.environ['GOOGLE_CLIENT_ID'], 'redirect_uri':redirect_uri(),
        'response_type':'code', 'scope':SCOPES, 'state':state,
        'access_type':'offline', 'prompt':'consent'})


def _fernet():
    return Fernet(os.environ['JARVIS_TOKEN_KEY'].encode())


def _save(store, token):
    store.set_secret('gmail', _fernet().encrypt(json.dumps(token).encode()).decode())


def connected(store):
    return configured() and bool(store.get_secret('gmail'))


async def exchange_code(store, code):
    async with httpx.AsyncClient(timeout=20) as client:
        resp = await client.post('https://oauth2.googleapis.com/token', data={
            'code':code, 'client_id':os.environ['GOOGLE_CLIENT_ID'],
            'client_secret':os.environ['GOOGLE_CLIENT_SECRET'],
            'redirect_uri':redirect_uri(), 'grant_type':'authorization_code'})
        resp.raise_for_status()
    token = resp.json()
    if 'access_token' not in token or 'refresh_token' not in token:
        raise ValueError('Missing access token or refresh token; reconnect with consent')
    token['expires_at'] = time.time() + token.get('expires_in',3600)
    _save(store, token)


async def access_token(store):
    encrypted = store.get_secret('gmail')
    if not encrypted:
        raise ValueError('Gmail non collegato')
    try:
        token = json.loads(_fernet().decrypt(encrypted.encode()))
    except (InvalidToken, ValueError) as exc:
        raise ValueError('La chiave di cifratura Gmail non corrisponde') from exc
    if token.get('expires_at',0) > time.time()+90:
        return token['access_token']
    if not token.get('refresh_token'):
        raise ValueError('Ricollega Gmail per autorizzare la sessione')
    async with httpx.AsyncClient(timeout=20) as client:
        resp = await client.post('https://oauth2.googleapis.com/token', data={
            'client_id':os.environ['GOOGLE_CLIENT_ID'],
            'client_secret':os.environ['GOOGLE_CLIENT_SECRET'],
            'refresh_token':token['refresh_token'], 'grant_type':'refresh_token'})
        resp.raise_for_status()
    new = resp.json()
    token['access_token'] = new['access_token']
    token['expires_at'] = time.time() + new.get('expires_in',3600)
    _save(store,token)
    return token['access_token']


async def request(store, method, route, body=None, params=None):
    auth = {'Authorization':'Bearer '+await access_token(store)}
    async with httpx.AsyncClient(timeout=25) as client:
        resp = await client.request(method, 'https://gmail.googleapis.com/gmail/v1/users/me/'+route,
                                     headers=auth, json=body, params=params)
        resp.raise_for_status()
        return resp.json()


async def inbox(store):
    result = await request(store, 'GET', 'labels/INBOX')
    unread = result.get('messagesUnread', 0)
    listed = await request(store, 'GET', 'messages', params={'maxResults': 8, 'q':'in:inbox is:unread'})
    messages = []
    for item in listed.get('messages', []):
        msg = await request(store, 'GET', 'messages/'+item['id'],
                            params={'format':'metadata', 'metadataHeaders':['From','Subject','Date']})
        headers = {h['name'].lower():h['value'] for h in msg.get('payload',{}).get('headers',[])}
        messages.append({'id':item['id'], 'from':headers.get('from',''),
                         'subject':headers.get('subject','(senza oggetto)'),
                         'snippet':msg.get('snippet','')})
    return {'unread':unread, 'messages':messages}


async def send_message(store, recipient, subject, body):
    msg = EmailMessage()
    msg['To'] = recipient
    msg['Subject'] = subject
    msg.set_content(body)
    raw = base64.urlsafe_b64encode(msg.as_bytes()).decode()
    return await request(store, 'POST', 'messages/send', {'raw':raw})
