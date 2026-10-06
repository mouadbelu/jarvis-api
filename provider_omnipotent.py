import os
import httpx

OPENAI_KEY = os.getenv("JARVIS_OPENAI_KEY")
CLAUDE_KEY = os.getenv("JARVIS_CLAUDE_KEY")
GEMINI_KEY = os.getenv("JARVIS_GEMINI_KEY")

SYSTEM_PROMPT = "Sei JARVIS, un assistente AI intelligente e diretto."

async def _ask_openai(prompt: str):
    if not OPENAI_KEY:
        return None
    try:
        async with httpx.AsyncClient(timeout=60) as client:
            r = await client.post(
                "https://api.openai.com/v1/chat/completions",
                headers={"Authorization": f"Bearer {OPENAI_KEY}", "Content-Type": "application/json"},
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
            print("OpenAI error:", r.status_code, r.text[:300])
            return None
    except Exception as e:
        print("OpenAI exception:", e)
        return None

async def _ask_claude(prompt: str):
    if not CLAUDE_KEY:
        return None
    try:
        async with httpx.AsyncClient(timeout=60) as client:
            r = await client.post(
                "https://api.anthropic.com/v1/messages",
                headers={
                    "x-api-key": CLAUDE_KEY,
                    "anthropic-version": "2023-06-01",
                    "Content-Type": "application/json"
                },
                json={
                    "model": "claude-3-5-sonnet-20241022",
                    "max_tokens": 1000,
                    "system": SYSTEM_PROMPT,
                    "messages": [{"role": "user", "content": prompt}]
                },
            )
            if r.status_code == 200:
                return r.json()["content"][0]["text"]
            print("Claude error:", r.status_code, r.text[:300])
            return None
    except Exception as e:
        print("Claude exception:", e)
        return None

async def _ask_gemini(prompt: str):
    # Accetta qualsiasi formato di chiave, non solo AIza
    if not GEMINI_KEY or len(GEMINI_KEY) < 10:
        return None
    try:
        async with httpx.AsyncClient(timeout=60) as client:
            url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent?key={GEMINI_KEY}"
            r = await client.post(
                url,
                headers={"Content-Type": "application/json"},
                json={"contents": [{"parts": [{"text": f"{SYSTEM_PROMPT}\n\n{prompt}"}]}]},
            )
            if r.status_code == 200:
                data = r.json()
                candidates = data.get("candidates", [])
                if candidates:
                    parts = candidates[0].get("content", {}).get("parts", [])
                    if parts:
                        return parts[0].get("text", "")
            print("Gemini error:", r.status_code, r.text[:300])
            return None
    except Exception as e:
        print("Gemini exception:", e)
        return None

async def omnipotent_ask(prompt: str) -> str:
    global OPENAI_KEY, CLAUDE_KEY, GEMINI_KEY
    # Rileggi le variabili a runtime per sicurezza
    OPENAI_KEY = os.getenv("JARVIS_OPENAI_KEY")
    CLAUDE_KEY = os.getenv("JARVIS_CLAUDE_KEY")
    GEMINI_KEY = os.getenv("JARVIS_GEMINI_KEY")

    for fn in (_ask_openai, _ask_claude, _ask_gemini):
        result = await fn(prompt)
        if result:
            return result
    return "Nessun provider disponibile. Controlla le chiavi JARVIS_OPENAI_KEY, JARVIS_CLAUDE_KEY, JARVIS_GEMINI_KEY nelle variabili d'ambiente."

def get_response(prompt: str):
    return omnipotent_ask(prompt)

class ProviderOmnipotent:
    async def ask(self, prompt: str) -> str:
        return await omnipotent_ask(prompt)
