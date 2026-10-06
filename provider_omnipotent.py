import os
import httpx

SYSTEM_PROMPT = "Sei JARVIS, un assistente AI intelligente e diretto."

# Tutti i modelli Gemini validi, provati in ordine. Se uno non esiste, salta al prossimo.
GEMINI_MODELS = [
    "gemini-2.5-flash",
    "gemini-2.5-pro",
    "gemini-1.5-flash",
    "gemini-1.5-pro",
    "gemini-2.0-flash-001",
    "gemini-2.0-flash-lite",
]

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

async def _ask_gemini(prompt: str, key: str):
    if not key or len(key) < 10:
        return None
    # Prova ogni modello finché uno funziona
    async with httpx.AsyncClient(timeout=60) as client:
        for model in GEMINI_MODELS:
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
                    print(f"Gemini {model} error: {r.status_code}")
                    continue # prova modello successivo
            except Exception as e:
                print(f"Gemini {model} exception:", e)
                continue
    return None

async def omnipotent_ask(prompt: str, system: str = None, **kwargs) -> str:
    global SYSTEM_PROMPT
    if system:
        SYSTEM_PROMPT = system

    # Rileggi le chiavi ogni volta, così non serve riavviare per nulla
    openai_key = os.getenv("JARVIS_OPENAI_KEY")
    claude_key = os.getenv("JARVIS_CLAUDE_KEY")
    gemini_key = os.getenv("JARVIS_GEMINI_KEY")

    # Prova i provider in ordine
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
