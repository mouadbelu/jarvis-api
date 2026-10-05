from fastapi import FastAPI
from pydantic import BaseModel
from typing import List, Literal
import os

# Importa i tuoi file originali - li lasciamo intatti
from provider_omnipotent import OmnipotentProvider

app = FastAPI(title="JARVIS Omnipotent")
provider = OmnipotentProvider()

class Msg(BaseModel):
    role: Literal["user","assistant","system"]
    content: str

class ChatReq(BaseModel):
    messages: List[Msg]

@app.get("/health")
async def health():
    return {"status":"ok", "provider":"omnipotent"}

@app.post("/v1/chat")
async def chat(req: ChatReq):
    # converto per compatibilità con i tuoi schemas.py
    from types import SimpleNamespace
    internal = [SimpleNamespace(role=m.role, content=m.content) for m in req.messages]
    text = await provider.complete(internal)
    return {"message": {"role":"assistant", "content": text}}
