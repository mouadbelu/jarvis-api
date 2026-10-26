"""Fault-tolerant AI providers with server-only secrets and safe diagnostics."""
import asyncio
import os
import re

import httpx
import self_healing

SYSTEM_PROMPT = (
    'Sei Jarvis, l’assistente personale di Mouad. Rispondi in italiano, con precisione, '
    'senza inventare accesso a email o app. Saluta solo all’inizio di una nuova conversazione; '+
    'non ripetere buongiorno o il nome dell’utente a ogni risposta. Non affermare di aver inviato messaggi '
    'o compiuto azioni se non le hai realmente completate. Quando un’azione ha '
    'conseguenze esterne, ricorda che richiede conferma esplicita.'
)


def _safe_error_code(response):
    try:
        error = response.json().get('error', {})
        code = error.get('code') or error.get('status') or error.get('type') if isinstance(error, dict) else ''
        value = str(code or 'unspecified')
        return value[:64] if re.fullmatch(r'[a-zA-Z0-9_.-]{1,64}', value) else 'redacted'
    except (ValueError, AttributeError, TypeError):
        return 'unspecified'


async def _post(client, url, headers, json):
    """Retry *one* transient AI request; never retry authentication or quota errors."""
    for attempt in range(2):
        try:
            response = await client.post(url, headers=headers, json=json)
            response.raise_for_status()
            return response
        except httpx.HTTPStatusError as exc:
            if attempt == 0 and exc.response.status_code in (500, 502, 503, 504):
                await asyncio.sleep(0.35)
                continue
            raise
        except httpx.TransportError:
            if attempt == 0:
                await asyncio.sleep(0.35)
                continue
            raise


def _failure(provider, exc, model=None):
    if isinstance(exc, httpx.HTTPStatusError):
        status = exc.response.status_code
        code = _safe_error_code(exc.response)
        print(f'Jarvis recovery: {provider} HTTP {status} code={code}', flush=True)
        self_healing.provider_failed(provider, status, code)
    else:
        print(f'Jarvis recovery: {provider} {type(exc).__name__}', flush=True)
        self_healing.provider_failed(provider)


async def omnipotent_ask(prompt: str, sys: str | None = None) -> str | None:
    system = (sys or SYSTEM_PROMPT)[:10000]
    async with httpx.AsyncClient(timeout=httpx.Timeout(35.0)) as client:
        key = os.getenv('JARVIS_OPENAI_KEY') or os.getenv('OPENAI_API_KEY')
        if key and self_healing.may_try('OpenAI'):
            try:
                response = await _post(
                    client, 'https://api.openai.com/v1/chat/completions',
                    {'Authorization': 'Bearer ' + key},
                    {'model': os.getenv('JARVIS_OPENAI_MODEL', 'gpt-4o-mini'),
                     'messages': [{'role': 'system', 'content': system},
                                  {'role': 'user', 'content': prompt}]})
                answer = response.json()['choices'][0]['message']['content']
                if isinstance(answer, str) and answer.strip():
                    self_healing.provider_ok('OpenAI')
                    return answer
                raise ValueError('Empty provider reply')
            except (httpx.HTTPError, ValueError, KeyError, IndexError, TypeError) as exc:
                _failure('OpenAI', exc)

        key = os.getenv('JARVIS_GEMINI_KEY')
        if key and self_healing.may_try('Gemini'):
            configured = os.getenv('JARVIS_GEMINI_MODEL', '').strip()
            # The first default is known to work for this deployment. Other
            # configured models are not silently overridden.
            candidates = [configured] if configured else [
                'gemini-3.5-flash-lite', 'gemini-3.8-flash', 'gemini-3.6-flash'
            ]
            last_error = None
            for model in candidates:
                try:
                    response = await _post(
                        client,
                        'https://generativelanguage.googleapis.com/v1beta/models/'
                        + model + ':generateContent',
                        {'x-goog-api-key': key},
                        {'systemInstruction': {'parts': [{'text': system}]},
                         'contents': [{'parts': [{'text': prompt}]}]})
                    answer = response.json()['candidates'][0]['content']['parts'][0]['text']
                    if isinstance(answer, str) and answer.strip():
                        self_healing.provider_ok('Gemini')
                        return answer
                    raise ValueError('Empty provider reply')
                except (httpx.HTTPError, ValueError, KeyError, IndexError, TypeError) as exc:
                    last_error = exc
                    # Retry alternate model only when the model is missing.
                    if not (isinstance(exc, httpx.HTTPStatusError)
                            and exc.response.status_code == 404):
                        break
            if last_error is not None:
                _failure('Gemini', last_error)

        key = os.getenv('JARVIS_CLAUDE_KEY')
        if key and self_healing.may_try('Claude'):
            try:
                response = await _post(
                    client, 'https://api.anthropic.com/v1/messages',
                    {'x-api-key': key, 'anthropic-version': '2023-06-01'},
                    {'model': os.getenv('JARVIS_CLAUDE_MODEL', 'claude-sonnet-4-5'),
                     'max_tokens': 1000, 'system': system,
                     'messages': [{'role': 'user', 'content': prompt}]})
                answer = response.json()['content'][0]['text']
                if isinstance(answer, str) and answer.strip():
                    self_healing.provider_ok('Claude')
                    return answer
                raise ValueError('Empty provider reply')
            except (httpx.HTTPError, ValueError, KeyError, IndexError, TypeError) as exc:
                _failure('Claude', exc)
    return None


ask_omnipotent = omnipotent_ask
