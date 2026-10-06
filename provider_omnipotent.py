import os
import httpx

SYSTEM_PROMPT = "Sei JARVIS, un assistente AI intelligente e diretto. Rispondi solo con la risposta finale."

async def _list_gemini_models(client, key):
    try:
        r = await client.get(f"https://generativelanguage.googleapis.com/v1beta/models?key={key}")
        if r.status_code == 200:
            models = [m["name"].replace("models/", "") for m in r.json().get("models", []) if "generateContent" in m.get("supportedGenerationMethods", [])]
            print("Gemini models disponibili:", models)
            return models
    except Exception as e:
        print("List models exception:", e)
    return []

async def _ask_gemini(prompt: str, key: str):
    if not key or not key.strip():
        return None
    key = key.strip()
    async with httpx.AsyncClient(timeout=60) as client:
        models = await _list_gemini_models(client, key) or ["gemini-2.5-flash", "gemini-2.5-pro", "gemini-1.5-flash", "gemini-1.5-pro", "gemini-2.0-flash", "gemini-2.0-flash-001", "gemini-2.0-flash-lite", "gemini-1.0-pro"]
        for model in models:
            try:
                r = await client.post(
                    f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={key}",
                    headers={"Content-Type": "application/json"},
                    json={
                        "system_instruction": {"parts": [{"text": SYSTEM_PROMPT}]},
                        "contents": [{"role": "user", "parts": [{"text": prompt}]}],
                        "generationConfig": {"temperature": 0.7}
                    },
                )
                if r.status_code == 200:
                    parts = r.json().get("candidates", [{}])[0].get("content", {}).get("parts", [])
                    if parts and parts[0].get("text"):
                        print(f"Gemini OK con {model}")
                        return parts[0]["text"]
                print(f"Gemini {model} error: {r.status_code}")
            except Exception as e:
                print(f"Gemini {model} exception:", e)
                continue
    return None

async def _ask_openai(prompt: str, key: str):
    if not key: return None
    try:
        async with httpx.AsyncClient(timeout=60) as client:
            r = await client.post("https://api.openai.com/v1/chat/completions",
                headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
                json={"model": "gpt-4o-mini", "messages": [{"role": "system", "content": SYSTEM
