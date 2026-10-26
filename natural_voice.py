"""Server-side Gemini speech synthesis: bounded, private, no saved audio.

Returns WAV audio bytes only for an authenticated, user-initiated request.
"""
import base64
import binascii
import logging
import os
import re

import httpx

LOG = logging.getLogger("jarvis.voice")
DEFAULT_TTS_MODEL = "gemini-3.8-flash-lite-tts"
MAX_TEXT = 1100
MAX_AUDIO = 6 * 1024 * 1024
ALLOWED_VOICES = {"Orus", "Kore", "Charon", "Puck", "Zephyr"}
MODEL_NAME_PATTERN = re.compile(r"^gemini-[a-z0-9.-]{1,60}$")


class VoiceUnavailable(Exception):
    """Provider unavailable. This must never block the text response."""


def _model():
    model = os.getenv("JARVIS_GEMINI_TTS_MODEL", DEFAULT_TTS_MODEL)
    if not MODEL_NAME_PATTERN.fullmatch(model):
        raise VoiceUnavailable("Modello vocale non valido.")
    return model


async def create_voice(text: str, voice: str = "Orus") -> bytes:
    key = os.getenv("JARVIS_GEMINI_KEY")
    if not key:
        raise VoiceUnavailable("Chiave Gemini non configurata.")
    if voice not in ALLOWED_VOICES:
        raise ValueError("Voce non disponibile.")
    cleaned = text.strip()
    if not cleaned or len(cleaned) > MAX_TEXT:
        raise ValueError("Testo fuori dai limiti vocali.")

    # Gemini 3.8 unary REST returns a WAV container (not raw PCM).
    url = "https://generativelanguage.googleapis.com/v1beta/models/" + _model() + ":generateContent"
    data = {
        "contents": [{
            "role": "user",
            "parts": [{
                "text": cleaned,
                "speech_metadata": {"style": "Speak Italian naturally, conversationally and warmly. Calm, expressive, varied intonation. Do not add any words."},
            }],
        }],
        "generationConfig": {
            "responseModalities": ["AUDIO"],
            "speechConfig": {
                "voiceConfig": {"voice": voice},
            },
        },
    }
    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(55.0)) as client:
            response = await client.post(url, headers={"x-goog-api-key": key}, json=data)
            response.raise_for_status()
            content = response.json()["candidates"][0]["content"]["parts"]
            audio = next(part["inlineData"]["data"] for part in content
                         if part.get("inlineData", {}).get("data"))
            decoded = base64.b64decode(audio, validate=True)
            # Avoid passing raw PCM or provider error pages as WAV to Safari.
            if not decoded.startswith(b"RIFF") or decoded[8:12] != b"WAVE":
                raise VoiceUnavailable("Il provider ha restituito un formato audio non supportato.")
            if len(decoded) > MAX_AUDIO:
                raise VoiceUnavailable("Risposta vocale troppo lunga.")
            return decoded
    except httpx.HTTPStatusError as exc:
        LOG.warning("Gemini TTS request refused with HTTP %d", exc.response.status_code)
        raise VoiceUnavailable("Voce AI temporaneamente non disponibile.") from None
    except (httpx.HTTPError, ValueError, KeyError, IndexError, StopIteration,
            TypeError, binascii.Error) as exc:
        LOG.warning("Gemini TTS failed: %s", type(exc).__name__)
        raise VoiceUnavailable("Voce AI temporaneamente non disponibile.") from None
