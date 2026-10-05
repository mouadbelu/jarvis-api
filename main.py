from uuid import uuid4
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from .config import settings
from .provider import DemoProvider
from .schemas import ChatRequest, ChatResponse, HealthResponse, Message, ToolRequest
from .security import is_allowed, requires_confirmation

app = FastAPI(title="JARVIS API", version="0.1.0")

origins = [x.strip() for x in settings.allowed_origins.split(",") if x.strip()]
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)

provider = DemoProvider()

@app.get("/health", response_model=HealthResponse)
async def health():
    return HealthResponse(
        status="ok",
        version=app.version,
        provider=provider.__class__.__name__,
    )

@app.post("/v1/chat", response_model=ChatResponse)
async def chat(req: ChatRequest):
    answer = await provider.complete(req.messages)
    return ChatResponse(
        message=Message(role="assistant", content=answer),
        conversation_id=req.conversation_id or str(uuid4()),
    )

@app.post("/v1/tools/authorize")
async def authorize(req: ToolRequest):
    if not is_allowed(req.name):
        raise HTTPException(404, "Tool not registered")
    if requires_confirmation(req.name) and not req.confirmed:
        return {"allowed": False, "confirmation_required": True}
    return {"allowed": True, "confirmation_required": False}
