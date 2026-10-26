"""Private low-latency Gemini Live WebSocket relay.

The browser never sees Google's API key. Only authenticated same-origin browsers
can open the session; audio is in memory and never stored.
"""
import asyncio
import base64
import json
import os
import re
from urllib.parse import quote

import websockets
from fastapi import WebSocket, WebSocketDisconnect

import auth_firewall
import emergency

LIVE_MODEL = "gemini-3.1-flash-live-preview"
MODEL_REGEX = re.compile(r"^gemini-[a-z0-9.-]{2,70}$")
MAX_SESSION_SECONDS = 20 * 60
MAX_PCM_FRAME = 16_384
MAX_AUDIO_RESPONSE = 500_000
MAX_BYTES_PER_SECOND = 65_536


def authorized(store, ws: WebSocket) -> bool:
    """Strict Origin + HttpOnly cookie session; no bearer or secrets in URLs."""
    origin = ws.headers.get("origin", "").rstrip("/")
    expected = os.getenv("JARVIS_PUBLIC_URL", "").rstrip("/")
    if not expected:
        host = ws.headers.get("host", "")
        expected = "https://" + host if host and "/" not in host else ""
    if not origin or origin != expected:
        return False
    key = os.getenv("JARVIS_ACCESS_TOKEN", "")
    if len(key) < 24:
        return False
    try:
        emergency.assert_unlocked(store)
        return auth_firewall.session_exists(store, ws.cookies.get(auth_firewall.COOKIE_NAME))
    except Exception:
        return False


def setup_message():
    model = os.getenv("JARVIS_GEMINI_LIVE_MODEL", LIVE_MODEL).strip()
    if not MODEL_REGEX.fullmatch(model):
        raise ValueError("Invalid model")
    return {
        "setup": {
            "model": "models/" + model,
            "responseModalities": ["AUDIO"],
            "inputAudioTranscription": {},
            "outputAudioTranscription": {},
            "systemInstruction": {
                "parts": [{"text": (
                    "Sei Jarvis, assistente vocale personale in italiano. "
                    "Conversa in modo naturale, scorrevole e conciso. "
                    "NON salutare e NON dire buongiorno a ogni risposta. "
                    "Puoi salutare brevemente una sola volta all'inizio della sessione, "
                    "ma poi rispondi direttamente alla domanda. "
                    "Non affermare di aver letto email, eseguito azioni o usato app "
                    "se non ti sono state fornite tali capacità. "
                    "Nessuna azione esterna senza esplicita autorizzazione."
                )}]
            },
        }
    }


def safe_live_message(message: str):
    """Forward only audio, transcripts and turn signals, never tool calls."""
    if len(message) > 2_500_000:
        return []
    try:
        payload = json.loads(message)
    except (ValueError, TypeError):
        return []
    if "setupComplete" in payload:
        return [{"ready": True}]
    content = payload.get("serverContent") or {}
    result = []
    if content.get("interrupted"):
        result.append({"interrupted": True})
    if content.get("inputTranscription", {}).get("text"):
        result.append({"input": str(content["inputTranscription"]["text"])[:3000]})
    if content.get("outputTranscription", {}).get("text"):
        result.append({"output": str(content["outputTranscription"]["text"])[:3000]})
    for part in (content.get("modelTurn", {}).get("parts") or []):
        blob = part.get("inlineData") if isinstance(part, dict) else None
        if blob and isinstance(blob.get("data"), str) and len(blob["data"]) <= MAX_AUDIO_RESPONSE:
            result.append({"audio": blob["data"]})
    if content.get("turnComplete"):
        result.append({"turnComplete": True})
    return result


async def websocket_session(ws: WebSocket, store):
    if not authorized(store, ws):
        await ws.close(code=4403)
        return
    api_key = os.getenv("JARVIS_GEMINI_KEY")
    if not api_key:
        await ws.close(code=4403)
        return
    await ws.accept()
    model = os.getenv("JARVIS_GEMINI_LIVE_MODEL", LIVE_MODEL)
    if not MODEL_REGEX.fullmatch(model):
        await ws.send_json({"error": "Modello Live non valido."})
        await ws.close(code=1011)
        return

    # Query key never reaches user's browser, logs, or the UI.
    url = (
        "wss://generativelanguage.googleapis.com/ws/"
        "google.ai.generativelanguage.v1beta.GenerativeService.BidiGenerateContent?key="
        + quote(api_key, safe="")
    )
    try:
        async with websockets.connect(url, open_timeout=12, close_timeout=3,
                                      max_size=2_500_000, ping_interval=20) as upstream:
            await upstream.send(json.dumps(setup_message()))

            async def browser_to_provider():
                sent_this_second = 0
                window_start = asyncio.get_running_loop().time()
                while True:
                    frame = await ws.receive()
                    if frame["type"] == "websocket.disconnect":
                        return
                    pcm = frame.get("bytes")
                    if pcm is None:
                        # No untrusted commands are accepted from the browser.
                        continue
                    if not 2 <= len(pcm) <= MAX_PCM_FRAME or len(pcm) % 2:
                        continue
                    now = asyncio.get_running_loop().time()
                    if now - window_start >= 1:
                        sent_this_second, window_start = 0, now
                    sent_this_second += len(pcm)
                    if sent_this_second > MAX_BYTES_PER_SECOND:
                        # Client is producing data too fast. Stop rather than incur
                        # unbounded audio usage.
                        return
                    await upstream.send(json.dumps({
                        "realtimeInput": {"audio": {
                            "data": base64.b64encode(pcm).decode("ascii"),
                            "mimeType": "audio/pcm;rate=16000"
                        }}
                    }))

            async def provider_to_browser():
                async for message in upstream:
                    if not isinstance(message, str):
                        continue
                    for event in safe_live_message(message):
                        await ws.send_json(event)

            tasks = [asyncio.create_task(browser_to_provider()),
                     asyncio.create_task(provider_to_browser())]
            try:
                done, pending = await asyncio.wait(tasks, timeout=MAX_SESSION_SECONDS,
                                                   return_when=asyncio.FIRST_COMPLETED)
                for task in pending:
                    task.cancel()
                await asyncio.gather(*tasks, return_exceptions=True)
                for task in done:
                    try:
                        task.result()
                    except (WebSocketDisconnect, RuntimeError, websockets.exceptions.ConnectionClosed):
                        pass
            finally:
                for task in tasks:
                    task.cancel()
                await asyncio.gather(*tasks, return_exceptions=True)
    except (OSError, TimeoutError, websockets.exceptions.WebSocketException, ValueError):
        try:
            await ws.send_json({"error": "Conversazione Live non disponibile con il tuo piano Gemini. Usa la modalità Voce classica."})
        except (WebSocketDisconnect, RuntimeError):
            pass
    finally:
        try:
            await ws.close()
        except (RuntimeError, WebSocketDisconnect):
            pass
