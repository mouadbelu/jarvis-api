from fastapi import FastAPI, Request
from provider_omnipotent import omnipotent_ask

app = FastAPI()

@app.post("/ask")
async def ask(request: Request):
    try:
        data = await request.json()
        prompt = data.get("prompt") or data.get("text") or ""
        if not prompt:
            return {"reply": "Non ho capito la domanda, Signore."}
        reply = await omnipotent_ask(prompt)
        return {"reply": reply}
    except Exception as e:
        print(f"Main crash: {e}")
        return {"reply": "Errore temporaneo. Riprova."}

@app.get("/")
async def root():
    return {"status": "ok", "message": "Jarvis API online"}

@app.get("/health")
async def health():
    return {"status": "ok"}
