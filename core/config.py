# core/config.py

from pydantic_settings import BaseSettings, SettingsConfigDict
from typing import List, Optional
from pathlib import Path
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent
ENV_PATH = BASE_DIR / ".env"

# 2. Load environment variables into os.environ system-wide
load_dotenv(dotenv_path=ENV_PATH)

class Settings(BaseSettings):

    APP_NAME: str = "AI Customer Support System"
    APP_VERSION: str = "1.0.0"
    DEBUG: bool = False
    BASE_URL: str = "http://localhost:8000"
    FRONTEND_URL: str = "http://localhost:3000"
    
    # Database
    DATABASE_TYPE: str = "postgres"  # "postgres" or "sqlite"
    SQLITE_FILE_PATH: str = "data/app.db"
    POSTGRES_USER: str = ""
    POSTGRES_PASSWORD: str = ""
    POSTGRES_HOST: str = "localhost"
    POSTGRES_PORT: int = 5432
    POSTGRES_DB: str = ""
    
    UPLOAD_DIR: str = "./uploads/chat"

    # Database URL
    @property
    def DATABASE_URL(self) -> str:
        if self.DATABASE_TYPE.lower() == "sqlite":
            return f"sqlite+aiosqlite:///{self.SQLITE_FILE_PATH}"
        return f"postgresql+asyncpg://{self.POSTGRES_USER}:{self.POSTGRES_PASSWORD}@{self.POSTGRES_HOST}:{self.POSTGRES_PORT}/{self.POSTGRES_DB}"

    
    # Encryption
    ENCRYPTION_KEY: Optional[str] = None  # Dedicated app-level encryption key (recommended)

    # External API Keys (referenced in action configs via {{env.XXX}})
    GROQ_API_KEY: Optional[str] = None
    SHOPEASY_API_KEY: Optional[str] = None
    OLLAMA_API_KEY: Optional[str] = None
    ADMIN_RPC_KEY: Optional[str] = None

    # Vector DB (overrides default when set)
    VECTOR_DB_CONNECTION_STRING: Optional[str] = None

    # JWT Settings
    SECRET_KEY: str
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30
    REFRESH_TOKEN_EXPIRE_DAYS: int = 7
    RESET_TOKEN_EXPIRE_MINUTES: int = 30
    
    # SMTP Settings
    SMTP_HOST: str = "smtp.gmail.com"
    SMTP_PORT: int = 587
    SMTP_USER: str
    SMTP_PASSWORD: str
    SMTP_FROM_EMAIL: str
    SMTP_FROM_NAME: str = "IntgraServe-AI Support"
    SMTP_TLS: bool = True
    SMTP_SSL: bool = False
    
    # CORS
    CORS_ORIGINS: List[str] = ["http://localhost:3000", "http://localhost:8000"]

    # AI Gateway
    AI_GATEWAY_ENABLED: bool = True
    CHAT_SESSION_TIMEOUT_MINUTES: int = 30

    model_config = SettingsConfigDict(
        env_file=".env",
        case_sensitive=True,
        extra="forbid"
    )


settings = Settings()