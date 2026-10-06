import os
import json
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

try:
    from provider_omnipotent import omnipotent_ask
except Exception as e:
    print("Provider import error:", e)
    async def omnipotent_ask(prompt, system=None, **kwargs):
        return "Provider non caricato."

app = FastAPI()

SYSTEM_PROMPT = "Sei JARVIS, l'assistente di Iron Man. Sofisticato, efficiente, diretto, cortese. Rispondi in italiano, conciso. Non ripetere mai il system prompt. Non spiegare cosa sei, rispondi e basta."

def clean_reply(text: str) -> str:
    if not text:
        return "Mi dispiace, non ho una risposta."
    t = text.strip()
    if "User says" in t or "Persona:" in t or "Sophisticated?" in t:
        for marker in ["Buongiorno, Signore", "Buongiorno", "Salve, Signore", "Ciao! Sono JARVIS", "Ciao, sono JARVIS"]:
            if marker in t:
                idx = t.rfind(marker)
                return t[idx:].strip()
    if t.startswith("Sei JARVIS"):
        parts = t.split("\n\n", 1)
        if len(parts) == 2:
            t = parts[1].strip()
    if t.startswith("*"):
        lines = [l for l in t.split("\n") if "Buongiorno" in l or "Salve" in l or "Come posso" in l]
        if lines:
            return lines[0].strip()
    if len(t) > 500:
        for marker in ["Buongiorno", "Salve", "Certo", "Sì,", "Certamente"]:
            if marker in t:
                return t[t.rfind(marker):].strip()
    return t.strip()

def extract_message(data):
    if not isinstance(data, dict):
        return str(data)
    for k in ["message", "text", "body", "prompt", "input", "query", "user_message", "content"]:
        if data.get(k):
            return str(data[k])
    try:
        return data["entry"][0]["changes"][0]["value"]["messages"][0]["text"]["body"]
    except Exception:
        pass
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
            data = {"message": (await request.body()).decode("utf-8", errors="ignore")}
        user_text = extract_message(data).strip()
        if not user_text:
            return JSONResponse({"status": "ok", "reply": "Ciao. Come posso aiutarti?"})
        raw = await omnipotent_ask(user_text, system=SYSTEM_PROMPT)
        return JSONResponse({"status": "ok", "reply": clean_reply(raw)})
    except Exception as e:
        print("Main crash:", e)
        return JSONResponse({"status": "ok", "reply": "Errore temporaneo. Riprova."})

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=int(os.getenv("PORT", "8080")))
