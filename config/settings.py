import os
from dotenv import load_dotenv
load_dotenv()

class Settings:
    TELEGRAM_BOT_TOKEN: str       = os.getenv("TELEGRAM_BOT_TOKEN", "")
    TELEGRAM_WEBHOOK_SECRET: str  = os.getenv("TELEGRAM_WEBHOOK_SECRET", "")
    GEMINI_API_KEY: str           = os.getenv("GEMINI_API_KEY", "")
    SERPAPI_KEY: str              = os.getenv("SERPAPI_KEY", "")
    DATABASE_URL: str             = os.getenv("DATABASE_URL", "sqlite:///./agent.db")
    SECRET_KEY: str               = os.getenv("SECRET_KEY", "dev-secret-change-me")
    DEBUG: bool                   = os.getenv("DEBUG", "False").lower() == "true"
    PORT: int                     = int(os.getenv("PORT", "8000"))
    MAX_REQUESTS_PER_USER_PER_HOUR: int = int(os.getenv("MAX_REQUESTS_PER_USER_PER_HOUR", "20"))
    AGENT_TIMEOUT_SECONDS: int    = int(os.getenv("AGENT_TIMEOUT_SECONDS", "45"))

settings = Settings()
