import os
import httpx

SYSTEM_PROMPT = "Sei JARVIS, un assistente AI intelligente e diretto."

async def _ask_openai(prompt: str, key: str):
    if not key:
        return None
    try:
        async with httpx.AsyncClient(timeout=60) as client:
            r = await client.post(
                "https://api.openai.com/v1/chat/completions",
                headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
                json={
                    "model": "gpt-4o-mini",
                    "messages": [{"role": "system", "content": SYSTEM_PROMPT}, {"role": "user", "content": prompt}]
                },
            )
            if r.status_code == 200:
                return r.json()["choices"][0]["message"]["content"]
            print("OpenAI error:", r.status_code, r.text[:200])
    except Exception as e:
        print("OpenAI exception:", e)
    return None

async def _ask_claude(prompt: str, key: str):
    if not key:
        return None
    try:
        async with httpx.AsyncClient(timeout=60) as client:
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
            print("Claude error:", r.status_code, r.text[:200])
    except Exception as e:
        print("Claude exception:", e)
    return None

async def _list_gemini_models(client, key):
    # Chiede a Google quali modelli puoi usare con QUESTA chiave
    try:
        r = await client.get(f"https://generativelanguage.googleapis.com/v1beta/models?key={key}")
        if r.status_code == 200:
            models = []
            for m in r.json().get("models", []):
                if "generateContent" in m.get("supportedGenerationMethods", []):
                    # m["name"] è "models/gemini-2.5-flash"
                    models.append(m["name"].replace("models/", ""))
            print("Gemini models disponibili:", models)
            return models
    except Exception as e:
        print("List models exception:", e)
    return []

async def _ask_gemini(prompt: str, key: str):
    if not key or not key.strip():
        print("Gemini key vuota")
        return None
    key = key.strip()
    async with httpx.AsyncClient(timeout=60) as client:
        # 1. Prima prova a scoprire i modelli
        models = await _list_gemini_models(client, key)
        # 2. Se la scoperta fallisce, usa lista di fallback
        if not models:
            models = ["gemini-2.5-flash", "gemini-2.5-pro", "gemini-1.5-flash", "gemini-1.5-pro", "gemini-2.0-flash", "gemini-2.0-flash-001", "gemini-2.0-flash-lite", "gemini-1.0-pro"]

        for model in models:
            try:
                url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={key}"
                r = await client.post(
                    url,
                    headers={"Content-Type": "application/json"},
                    json={"contents": [{"parts": [{"text": f"{SYSTEM_PROMPT}\n\n{prompt}"}]}]},
                )
                if r.status_code == 200:
                    data = r.json()
                    cands = data.get("candidates", [])
                    if cands:
                        parts = cands[0].get("content", {}).get("parts", [])
                        if parts and parts[0].get("text"):
                            print(f"Gemini OK con {model}")
                            return parts[0]["text"]
                else:
                    print(f"Gemini {model} error: {r.status_code} - {r.text[:200]}")
                    continue
            except Exception as e:
                print(f"Gemini {model} exception:", e)
                continue
    return None

async def omnipotent_ask(prompt: str, system: str = None, **kwargs) -> str:
    global SYSTEM_PROMPT
    if system:
        SYSTEM_PROMPT = system

    openai_key = os.getenv("JARVIS_OPENAI_KEY")
    claude_key = os.getenv("JARVIS_CLAUDE_KEY")
    gemini_key = os.getenv("JARVIS_GEMINI_KEY")

    for key, fn in [(openai_key, _ask_openai), (claude_key, _ask_claude), (gemini_key, _ask_gemini)]:
        try:
            result = await fn(prompt, key)
            if result and result.strip():
                return result
        except Exception as e:
            print("Provider crash:", e)
            continue

    return "Nessun provider disponibile. Controlla le chiavi JARVIS_OPENAI_KEY, JARVIS_CLAUDE_KEY, JARVIS_GEMINI_KEY nelle variabili d'ambiente."

def get_response(prompt: str):
    return omnipotent_ask(prompt)

class ProviderOmnipotent:
    async def ask(self, prompt: str) -> str:
        return await omnipotent_ask(prompt)
