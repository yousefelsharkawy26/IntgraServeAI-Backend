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
    
    # Actions Configuration
    ACTIONS_FILE_PATH: str = "data/actions.json"
    ACTIONS_BACKUP_ENABLED: bool = True
    ACTIONS_BACKUP_COUNT: int = 5

    # AI Gateway
    AI_GATEWAY_ENABLED: bool = True
    CHAT_SESSION_TIMEOUT_MINUTES: int = 30
    
    @property
    def ACTIONS_FILE_FULL_PATH(self) -> Path:
        """Get full path to actions file, anchored to project root if relative"""
        path = Path(self.ACTIONS_FILE_PATH)
        if not path.is_absolute():
            path = BASE_DIR / path
        return path
    
    @property
    def ACTIONS_BACKUP_DIR(self) -> Path:
        """Get backup directory path, anchored to project root if relative"""
        path = Path(self.ACTIONS_FILE_PATH)
        if not path.is_absolute():
            path = BASE_DIR / path
        return path.parent / "backups"

    AGENT_CONFIG_FILE_PATH: str = "data/agent_config.json"
    AGENT_CONFIG_BACKUP_ENABLED: bool = True
    AGENT_CONFIG_BACKUP_COUNT: int = 5

    @property
    def AGENT_CONFIG_FILE_FULL_PATH(self) -> Path:
        """Get full path to agent config file, anchored to project root if relative"""
        path = Path(self.AGENT_CONFIG_FILE_PATH)
        if not path.is_absolute():
            path = BASE_DIR / path
        return path
    
    @property
    def AGENT_CONFIG_BACKUP_DIR(self) -> Path:
        """Get agent config backup directory path, anchored to project root if relative"""
        path = Path(self.AGENT_CONFIG_FILE_PATH)
        if not path.is_absolute():
            path = BASE_DIR / path
        return path.parent / "backups"

    model_config = SettingsConfigDict(
        env_file=".env",
        case_sensitive=True,
        extra="allow"
    )


settings = Settings()