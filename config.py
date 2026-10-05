import os

class Settings:
    JARVIS_GEMINI_KEY = os.getenv("JARVIS_GEMINI_KEY", "")
    JARVIS_OPENAI_KEY = os.getenv("JARVIS_OPENAI_KEY", "")
    JARVIS_CLAUDE_KEY = os.getenv("JARVIS_CLAUDE_KEY", "")
    gemini_key = os.getenv("JARVIS_GEMINI_KEY", "")
    openai_key = os.getenv("JARVIS_OPENAI_KEY", "")
    claude_key = os.getenv("JARVIS_CLAUDE_KEY", "")

settings = Settings()
