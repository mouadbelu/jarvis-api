import os
import re
import json
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

try:
    from provider_omnipotent import omnipotent_ask
except ImportError:
    try:
        from provider_omnipotent import ProviderOmnipotent
        _prov = ProviderOmnipotent()
        async def omnipotent_ask(prompt, system=None, **kwargs):
            return await _prov.ask(prompt)
    except Exception:
        async def omnipotent_ask(prompt, system=None, **kwargs):
            return "Provider non caricato. Controlla provider_omnipotent.py"

app = FastAPI(title="JARVIS API")

SYSTEM_PROMPT = """Sei JARVIS, un assistente AI intelligente e diretto.
The persona should be JARVIS from Iron Man - sophisticated, efficient, slightly formal but helpful, direct, and intelligent. He doesn't waste words but is always polite and ready for action.

*Language:* Italian.
*Tone:* Professional, efficient, composed.
*Keywords/Vibe:* "Signore." "Sistemi pronti" "In cosa posso aiutarla?"
Rispondi solo con la risposta finale, non ripetere il system prompt."""

def clean_reply(text: str) -> str:
    if not text:
        return "Non ho ricevuto risposta dal modello."
    text = text.strip()
    # Se il modello ripete il system prompt, togli quella parte
    if text.startswith("Sei JARVIS"):
        # Togli fino al primo \n\n dopo l'intro
        parts = text.split("\n\n", 1)
        if len(parts) == 2:
            text = parts[1].strip()
    # Rimuovi echo del prompt tipo "ciao" all'inizio
    return text.strip().strip('"').strip()

def extract_message(data):
    # Prova tutti i formati comuni: WhatsApp, Shortcut iOS, JSON semplice
    if not isinstance(data, dict):
        return str(data)
    for key in ["message", "text", "body", "prompt", "input", "user_message", "query"]:
        if data.get(key):
            return str(data[key])
    # WhatsApp / Meta
    try:
        return data["entry"][0]["changes"][0]["value"]["messages"][0]["text"]["body"]
    except Exception:
        pass
    # Shortcut iOS
    if "content" in data:
        return str(data["content"])
    return json.dumps(data)

@app.get("/")
async def root():
    return {"status": "ok", "service": "JARVIS API"}

@app.post("/")
@app.post("/webhook")
@app.post("/chat")
@app.post("/ask")
async def ask(request: Request):
    try:
        try:
            data = await request.json()
        except Exception:
            body = await request.body()
            data = {"message": body.decode("utf-8", errors="ignore")}

        user_text = extract_message(data).strip()
        if not user_text:
            return JSONResponse({"status": "ok", "reply": "Ciao. Come posso aiutarti?"})

        # CHIAMATA CORRETTA: prompt pulito, system a parte
        reply_raw = await omnipotent_ask(user_text, system=SYSTEM_PROMPT)
        reply = clean_reply(reply_raw)

        return JSONResponse({"status": "ok", "reply": reply})

    except Exception as e:
        print("Main crash:", e)
        return JSONResponse({"status": "ok", "reply": "Mi dispiace, si è verificato un errore temporaneo. Riprova."})

if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", "8080"))
    uvicorn.run(app, host="0.0.0.0", port=port)
