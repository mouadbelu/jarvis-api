from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from config import settings
from provider_omnipotent import omnipotent_ask
from pydantic import BaseModel
from typing import Optional

app = FastAPI(title=settings.APP_NAME, version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

class ChatRequest(BaseModel):
    message: str
    prompt: Optional[str] = None
    system: Optional[str] = None

class ChatResponse(BaseModel):
    response: str
    reply: str
    model_used: str = "omnipotent"
    status: str = "ok"

@app.get("/")
async def root():
    return {"status": "ok", "message": "JARVIS API è online", "app": settings.APP_NAME}

@app.get("/health")
async def health():
    return {"status": "ok", "healthy": True}

@app.post("/chat", response_model=ChatResponse)
async def chat(req: ChatRequest):
    prompt = req.message or req.prompt or ""
    if not prompt.strip():
        return ChatResponse(response="Dimmi cosa vuoi chiedermi.", reply="Dimmi cosa vuoi chiedermi.")
    answer = await omnipotent_ask(prompt, system=req.system)
    return ChatResponse(response=answer, reply=answer)

@app.post("/ask")
async def ask(req: ChatRequest):
    return await chat(req)

@app.get("/config")
async def get_config():
    return {
        "openai": bool(settings.OPENAI_API_KEY),
        "claude": bool(settings.CLAUDE_API_KEY),
        "gemini": bool(settings.GEMINI_API_KEY)
    }

@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    return JSONResponse(status_code=500, content={"error": str(exc), "status": "error"})
