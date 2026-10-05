import os

class Settings:
    APP_NAME = "JARVIS API"
    APP_VERSION = "1.0.0"
    PROJECT_NAME = "JARVIS API"
    DEBUG = True

    JARVIS_GEMINI_KEY = os.getenv("JARVIS_GEMINI_KEY", "")
    JARVIS_OPENAI_KEY = os.getenv("JARVIS_OPENAI_KEY", "")
    JARVIS_CLAUDE_KEY = os.getenv("JARVIS_CLAUDE_KEY", "")
    GEMINI_API_KEY = os.getenv("JARVIS_GEMINI_KEY", "")
    OPENAI_API_KEY = os.getenv("JARVIS_OPENAI_KEY", "")
    CLAUDE_API_KEY = os.getenv("JARVIS_CLAUDE_KEY", "")
    gemini_key = os.getenv("JARVIS_GEMINI_KEY", "")
    openai_key = os.getenv("JARVIS_OPENAI_KEY", "")
    claude_key = os.getenv("JARVIS_CLAUDE_KEY", "")

    def __getattr__(self, name):
        return os.getenv(name, "")

settings = Settings()
