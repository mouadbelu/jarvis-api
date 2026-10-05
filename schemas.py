from typing import Literal
from pydantic import BaseModel, Field

Role = Literal["user", "assistant", "system"]

class Message(BaseModel):
    role: Role
    content: str = Field(min_length=1, max_length=100_000)

class ChatRequest(BaseModel):
    messages: list[Message] = Field(min_length=1, max_length=200)
    conversation_id: str | None = None

class ChatResponse(BaseModel):
    message: Message
    conversation_id: str

class HealthResponse(BaseModel):
    status: str
    version: str
    provider: str

class Memory(BaseModel):
    key: str
    value: str
    importance: int = Field(default=5, ge=1, le=10)

class ToolRequest(BaseModel):
    name: str
    arguments: dict = Field(default_factory=dict)
    confirmed: bool = False
