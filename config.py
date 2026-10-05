import os

class Settings:
    OPENAI_API_KEY = os.getenv("JARVIS_OPENAI_KEY", "")
    CLAUDE_API_KEY = os.getenv("JARVIS_CLAUDE_KEY", "")
    GEMINI_API_KEY = os.getenv("JARVIS_GEMINI_KEY", "")
    APP_NAME = "JARVIS API"
    DEBUG = False

settings = Settings()
