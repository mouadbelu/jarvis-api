import os
import httpx

SYSTEM_PROMPT = "Sei JARVIS, un assistente AI intelligente e diretto. Rispondi solo con la risposta finale, in italiano, senza ripetere il system prompt."

async def _list_gemini_models(client, key):
    try:
        r = await client.get(f"https://generativelanguage.googleapis.com/v1beta/models?key={key}")
        if r.status_code == 200:
            models = []
            for m in r.json().get("models", []):
                if "generateContent" in m.get("supportedGenerationMethods", []):
                    models.append(m["name"].replace("models/", ""))
            return models
    except Exception as e:
        print("List models exception:", e)
    return []

async def _ask_gemini(prompt: str, key: str):
    if not key or not key.strip():
        return None
    key = key.strip()
    async with httpx.AsyncClient(timeout=30) as client:
        models = await _list_gemini_models(client, key)
        if not models:
            models = ["gemini-2.5-flash", "gemini-1.5-flash", "gemini-2.0-flash"]
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
                        return parts[0]["text"]
            except Exception as e:
                print(f"Gemini {model} exception:", e)
                continue
    return None

async def _ask_openai(prompt: str, key: str):
    if not key:
        return None
    try:
        async with httpx.AsyncClient(timeout=30) as client:
            r = await client.post(
                "https://api.openai.com/v1/chat/completions",
                headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
                json={
                    "model": "gpt-4o-mini",
                    "messages": [
                        {"role": "system", "content": SYSTEM_PROMPT},
                        {"role": "user", "content": prompt}
                    ]
                },
            )
            if r.status_code == 200:
                return r.json()["choices"][0]["message"]["content"]
    except Exception as e:
        print("OpenAI exception:", e)
    return None

async def _ask_claude(prompt: str, key: str):
    if not key:
        return None
    try:
        async with httpx.AsyncClient(timeout=30) as client:
            r = await client.post(
                "https://api.anthropic.com/v1/messages",
                headers={"x-api-key": key, "anthropic-version": "2023-06-01", "Content-Type": "application/json"},
                json={
                    "model": "claude-3-5-sonnet-20241022",
                    "max_tokens": 1000,
                    "system": SYSTEM_PROMPT,
                    "messages": [{"role": "user", "content": prompt}]
                },
            )
            if r.status_code == 200:
                return r.json()["content"][0]["text"]
    except Exception as e:
        print("Claude exception:", e)
    return None

async def omnipotent_ask(prompt: str, system: str = None, **kwargs) -> str:
    global SYSTEM_PROMPT
    if system:
        SYSTEM_PROMPT = system
    for key, fn in [
        (os.getenv("JARVIS_OPENAI_KEY"), _ask_openai),
        (os.getenv("JARVIS_CLAUDE_KEY"), _ask_claude),
        (os.getenv("JARVIS_GEMINI_KEY"), _ask_gemini),
    ]:
        try:
            result = await fn(prompt, key)
            if result and result.strip():
                return result
        except Exception as e:
            print("Provider crash:", e)
    return "Nessun provider disponibile. Controlla le chiavi JARVIS_OPENAI_KEY, JARVIS_CLAUDE_KEY, JARVIS_GEMINI_KEY."

class ProviderOmnipotent:
    async def ask(self, prompt: str) -> str:
        return await omnipotent_ask(prompt)
