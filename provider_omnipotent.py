import httpx
import os

SYSTEM_PROMPT = "Sei Jarvis, assistente personale di Mouad. Parli solo italiano. Rispondi in modo formale e chiamalo Signore. Non tradurre mai in inglese. Non aggiungere mai testo tra parentesi. Rispondi sempre e solo in italiano."

async def ask_gemini(prompt, key):
    if not key:
        return None
    try:
        async with httpx.AsyncClient(timeout=60) as client:
            r = await client.post(
                f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent?key={key}",
                headers={"Content-Type": "application/json"},
                json={
                    "systemInstruction": {"parts": [{"text": SYSTEM_PROMPT}]},
                    "contents": [{"parts": [{"text": prompt}]}]
                }
            )
            if r.status_code!= 200:
                print(f"gemini http {r.status_code}: {r.text[:300]}")
                return None
            parts = r.json().get("candidates", [{}])[0].get("content", {}).get("parts", [])
            return parts[0]["text"] if parts else None
    except Exception as e:
        print(f"gemini error: {e}")
        return None

async def ask_openai(prompt, key):
    if not key:
        return None
    try:
        async with httpx.AsyncClient(timeout=60) as client:
            r = await client.post(
                "https://api.openai.com/v1/chat/completions",
                headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
                json={"model": "gpt-4o-mini", "messages": [{"role": "system", "content": SYSTEM_PROMPT}, {"role": "user", "content": prompt}]}
            )
            return r.json()["choices"][0]["message"]["content"] if r.status_code == 200 else None
    except Exception as e:
        print(f"openai error: {e}")
        return None

async def ask_claude(prompt, key):
    if not key:
        return None
    try:
        async with httpx.AsyncClient(timeout=60) as client:
            r = await client.post(
                "https://api.anthropic.com/v1/messages",
                headers={"x-api-key": key, "anthropic-version": "2023-06-01", "Content-Type": "application/json"},
                json={"model": "claude-3-5-sonnet-20241022", "max_tokens": 1024, "system": SYSTEM_PROMPT, "messages": [{"role": "user", "content": prompt}]}
            )
            return r.json()["content"][0]["text"] if r.status_code == 200 else None
    except Exception as e:
        print(f"claude error: {e}")
        return None

async def omnipotent_ask(prompt, sys=None):
    gemini_key = os.getenv("JARVIS_GEMINI_KEY", "")
    openai_key = os.getenv("JARVIS_OPENAI_KEY", "")
    claude_key = os.getenv("JARVIS_CLAUDE_KEY", "")
    result = await ask_gemini(prompt, gemini_key)
    if result:
        return result
    result = await ask_openai(prompt, openai_key)
    if result:
        return result
    result = await ask_claude(prompt, claude_key)
    if result:
        return result
    return "Errore provider disponibile."

# alias per compatibilità
ask_omnipotent = omnipotent_ask
