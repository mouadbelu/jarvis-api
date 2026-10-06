import os
import httpx

OPENAI_KEY = os.getenv("JARVIS_OPENAI_KEY")
CLAUDE_KEY = os.getenv("JARVIS_CLAUDE_KEY")
GEMINI_KEY = os.getenv("JARVIS_GEMINI_KEY")

SYSTEM_PROMPT = "Sei JARVIS, un assistente AI intelligente, diretto e utile. Rispondi in italiano in modo chiaro e conciso."

async def _ask_openai(prompt: str):
    if not OPENAI_KEY:
        return None
    async with httpx.AsyncClient(timeout=30) as client:
        r = await client.post(
            "https://api.openai.com/v1/chat/completions",
            headers={"Authorization": f"Bearer {OPENAI_KEY}"},
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

async def _ask_claude(prompt: str):
    if not CLAUDE_KEY:
        return None
    async with httpx.AsyncClient(timeout=30) as client:
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
            }
        )
        if r.status_code!= 200:
            return None
        return r.json()["content"][0]["text"]

async def _ask_gemini(prompt: str):
    if not GEMINI_KEY:
        return None
    async with httpx.AsyncClient(timeout=30) as client:
        r = await client.post(
            f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent?key={GEMINI_KEY}",
            headers={"Content-Type": "application/json"},
            json={"contents": [{"parts": [{"text": f"{SYSTEM_PROMPT}\n\nUtente: {prompt}"}]}]}
        )
        if r.status_code!= 200:
            print(f"Gemini error {r.status_code}: {r.text}")
            return None
        return r.json()["candidates"][0]["content"]["parts"][0]["text"]

async def omnipotent_ask(prompt: str, system: str = None):
    """Prova OpenAI -> Claude -> Gemini e restituisce la prima risposta valida."""
    global SYSTEM_PROMPT
    if system:
        SYSTEM_PROMPT = system

    for fn in (_ask_openai, _ask_claude, _ask_gemini):
        try:
            result = await fn(prompt)
            if result:
                return result
        except Exception:
            continue
    return "Nessun provider disponibile. Controlla le chiavi JARVIS_OPENAI_KEY, JARVIS_CLAUDE_KEY, JARVIS_GEMINI_KEY nelle variabili d'ambiente."

# Alias usati da main.py
ask = omnipotent_ask
ask_omnipotent = omnipotent_ask
get_response = omnipotent_ask
omnipotent = omnipotent_ask

class ProviderOmnipotent:
    async def ask(self, prompt: str):
        return await omnipotent_ask(prompt)
