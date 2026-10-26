"""Server-side, size-limited speech transcription. Never store or log speech contents."""
import base64
import os

import httpx

MAX_AUDIO_BYTES = 6 * 1024 * 1024
SUPPORTED_MIME = {
    'audio/mp4': 'clip.m4a',
    'audio/webm': 'clip.webm',
    'audio/ogg': 'clip.ogg',
    'audio/wav': 'clip.wav',
    'audio/mpeg': 'clip.mp3',
    'audio/aac': 'clip.aac',
}


def _log_failure(provider: str, exc: Exception):
    # Only an HTTP status or exception class is logged, not provider response bodies,
    # request URLs, spoken words, or keys.
    if isinstance(exc, httpx.HTTPStatusError):
        print(f'Jarvis audio transcription: {provider} HTTP {exc.response.status_code}', flush=True)
    else:
        print(f'Jarvis audio transcription: {provider} {type(exc).__name__}', flush=True)


async def transcribe_audio(audio: bytes, mime: str) -> str | None:
    if mime not in SUPPORTED_MIME:
        raise ValueError('Formato audio non supportato')
    if not audio or len(audio) > MAX_AUDIO_BYTES:
        raise ValueError('Audio vuoto o troppo grande')
    async with httpx.AsyncClient(timeout=httpx.Timeout(55.0)) as client:
        # Gemini is already the functional fallback for this installation.
        # Gemini's inline audio support depends on the configured model.
        key = os.getenv('JARVIS_GEMINI_KEY')
        if key:
            try:
                model = os.getenv('JARVIS_GEMINI_MODEL') or 'gemini-3.5-flash-lite'
                response = await client.post(
                    'https://generativelanguage.googleapis.com/v1beta/models/' + model + ':generateContent',
                    headers={'x-goog-api-key': key},
                    json={'contents': [{'parts': [
                        {'text': 'Trascrivi fedelmente il parlato in italiano. Rispondi SOLO con le parole pronunciate, senza commenti.'},
                        {'inline_data': {'mime_type': mime, 'data': base64.b64encode(audio).decode('ascii')}}
                    ]}]},
                )
                response.raise_for_status()
                data = response.json()
                result = ' '.join(
                    part['text'] for part in data['candidates'][0]['content']['parts']
                    if isinstance(part, dict) and isinstance(part.get('text'), str)
                ).strip()
                if result:
                    return result[:4000]
            except (httpx.HTTPError, ValueError, KeyError, IndexError, TypeError) as exc:
                _log_failure('Gemini', exc)
        key = os.getenv('JARVIS_OPENAI_KEY') or os.getenv('OPENAI_API_KEY')
        if key:
            try:
                response = await client.post(
                    'https://api.openai.com/v1/audio/transcriptions',
                    headers={'Authorization': 'Bearer ' + key},
                    data={'model': os.getenv('JARVIS_TRANSCRIBE_MODEL', 'gpt-4o-mini-transcribe'), 'language': 'it'},
                    files={'file': (SUPPORTED_MIME[mime], audio, mime)},
                )
                response.raise_for_status()
                result = str(response.json().get('text') or '').strip()
                if result:
                    return result[:4000]
            except (httpx.HTTPError, ValueError, KeyError, TypeError) as exc:
                _log_failure('OpenAI', exc)
    return None
