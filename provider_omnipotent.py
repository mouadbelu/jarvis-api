import httpx
import os

SYSTEM_PROMPT = "Sei Jarvis, assistente personale di Mouad. Parli solo italiano. Rispondi in modo formale e chiamalo Signore. Non tradurre mai in inglese. Non aggiungere mai testo tra parentesi. Non dire mai 'Good morning' o frasi in inglese. Rispondi sempre e solo in italiano."

# -------------------------------------------------
# GEMINI
# -------------------------------------------------
async def _gemini_list_models(key: str):
    async with httpx.AsyncClient(timeout=20) as client:
        r = await client.get(
            f"https://generativelanguage.googleapis.com/v1beta/models?key={key}",
            headers={"Content-Type": "application/json"}
        )
        if r.status_code!= 200:
            return []
        models = r.json().get("models", [])
        return [m["name"].replace("models/", "") for m in models if "generateContent" in str(m.get("supportedGenerationMethods", []))]

async def ask_gemini(prompt: str, key: str) -> str | None:
    if not key:
        return None
    try:
        async with httpx.AsyncClient(timeout=60) as client:
            models = await _gemini_list_models(key)
            for model in models:
                if "gemini" not in model:
                    continue
                r = await client.post(
                    f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent",
                    headers={"Content-Type": "application/json"},
                    json={
                        "systemInstruction": {"parts": [{"text": SYSTEM_PROMPT}]},
                        "contents": [{"parts": [{"text": prompt}]}],
                        "generationConfig": {"temperature": 0.7}
                    },
                    params={"key": key}
                )
                if r.status_code!= 200:
                    continue
                parts = r.json().get("candidates", [{}])[0].get("content", {}).get("parts", [])
                if parts and parts[0].get("text"):
                    return parts[0]["text"]
        return None
    except Exception as e:
        print(f"gemini error: {e}")
        return None

# -------------------------------------------------
# OPENAI
# -------------------------------------------------
async def ask_openai(prompt: str, key: str) -> str | None:
    if not key:
        return None
    try:
        async with httpx.AsyncClient(timeout=60) as client:
            r = await client.post(
                "https://api.openai.com/v1/chat/completions",
                headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
                json={
                    "model": "gpt-4o-mini",
                    "messages": [
                        {"role": "system", "content": SYSTEM_PROMPT},
                        {"role": "user", "content": prompt}
                    ]
                }
            )
            if r.status_code!= 200:
                return None
            return r.json()["choices"][0]["message"]["content"]
    except Exception as e:
        print(f"openai error: {e}")
        return None

# -------------------------------------------------
# CLAUDE
# -------------------------------------------------
async def ask_claude(prompt: str, key: str) -> str | None:
    if not key:
        return None
    try:
        async with httpx.AsyncClient(timeout=60) as client:
            r = await client.post(
                "https://api.anthropic.com/v1/messages",
                headers={
                    "x-api-key": key,
                    "anthropic-version": "2023-06-01",
                    "Content-Type": "application/json"
                },
                json={
                    "model": "claude-3-5-sonnet-20241022",
                    "max_tokens": 1024,
                    "system": SYSTEM_PROMPT,
                    "messages": [{"role": "user", "content": prompt}]
                }
            )
            if r.status_code!= 200:
                return None
            return r.json()["content"][0]["text"]
    except Exception as e:
        print(f"claude error: {
