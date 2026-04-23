"""Application settings and configuration."""
import os
from pathlib import Path
from typing import Optional
from pydantic_settings import BaseSettings
from functools import lru_cache


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    # Application
    APP_NAME: str = "HR Automation - AI Onboarding"
    APP_VERSION: str = "1.0.0"
    DEBUG: bool = False
    ENVIRONMENT: str = "development"

    # Database
    DATABASE_URL: str = "postgresql+asyncpg://postgres:postgres@localhost:5432/hr_onboarding"
    DATABASE_POOL_SIZE: int = 5
    DATABASE_MAX_OVERFLOW: int = 10

    # Email - IMAP
    IMAP_HOST: str = "outlook.office365.com"
    IMAP_PORT: int = 993
    IMAP_USERNAME: Optional[str] = None
    IMAP_PASSWORD: Optional[str] = None
    IMAP_USE_SSL: bool = True

    # Email - SMTP
    SMTP_HOST: str = "smtp-mail.outlook.com"
    SMTP_PORT: int = 587
    SMTP_USERNAME: Optional[str] = None
    SMTP_PASSWORD: Optional[str] = None
    SMTP_USE_TLS: bool = True
    SMTP_FROM_EMAIL: Optional[str] = None

    # Outlook OAuth2 (for personal accounts without app password)
    USE_OAUTH2: bool = False
    OUTLOOK_CLIENT_ID: Optional[str] = None
    OUTLOOK_CLIENT_SECRET: Optional[str] = None

    # LLM Configuration (Ollama)
    LLM_BASE_URL: str = "https://ollama.com"
    LLM_MODEL: str = "gpt-oss:120b"
    LLM_TIMEOUT: int = 120
    OLLAMA_API_KEY: Optional[str] = None

    # Vision LLM Configuration
    VISION_BACKEND: str = "ocr_fallback"  # Options: local_ollama, ollama_cloud, openai, ocr_fallback
    VISION_MODEL: str = "llava:13b"
    VISION_BASE_URL: Optional[str] = None  # Defaults to local Ollama

    # File Storage
    DOCUMENT_STORAGE_PATH: str = "/data/documents"
    TEMP_STORAGE_PATH: str = "/data/temp"

    # Excel Tracker
    EXCEL_TRACKER_PATH: str = "/media/bhupendra/Bhupendra/WorkSpace/Projects/HR_Automation/ai_onboarding_brain/data/input/offer_tracker.xlsx"

    # Airflow
    AIRFLOW_DAG_ID: str = "hr_onboarding_etl"
    AIRFLOW_SCHEDULE: str = "0 22 * * *"  # Daily at 10 PM IST

    # Security
    SECRET_KEY: str = "your-secret-key-change-in-production"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30

    class Config:
        env_file = ".env"
        case_sensitive = True


@lru_cache
def get_settings() -> Settings:
    """Get cached settings instance."""
    return Settings()


# Path constants
BASE_DIR = Path(__file__).resolve().parent.parent
PROJECT_ROOT = BASE_DIR.parent