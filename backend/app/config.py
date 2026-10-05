import os

try:
    from pydantic_settings import BaseSettings, SettingsConfigDict

    class Settings(BaseSettings):
        DATABASE_URL: str = os.getenv(
            "DATABASE_URL",
            "postgresql://postgres:postgres@localhost:5432/support_automation"
        )
        OPENAI_API_KEY: str = os.getenv("OPENAI_API_KEY", "mock")
        GEMINI_API_KEY: str = os.getenv("GEMINI_API_KEY", "")
        LLM_MODEL: str = os.getenv("LLM_MODEL", "gpt-4o-mini")
        CONFIDENCE_THRESHOLD: float = float(os.getenv("CONFIDENCE_THRESHOLD", "0.80"))
        ENVIRONMENT: str = os.getenv("ENVIRONMENT", "development")
        PORT: int = int(os.getenv("BACKEND_PORT", "8000"))

        model_config = SettingsConfigDict(
            env_file=".env",
            env_file_encoding="utf-8",
            extra="ignore"
        )
except ImportError:
    from pydantic import BaseModel

    class Settings(BaseModel):
        DATABASE_URL: str = os.getenv(
            "DATABASE_URL",
            "postgresql://postgres:postgres@localhost:5432/support_automation"
        )
        OPENAI_API_KEY: str = os.getenv("OPENAI_API_KEY", "mock")
        GEMINI_API_KEY: str = os.getenv("GEMINI_API_KEY", "")
        LLM_MODEL: str = os.getenv("LLM_MODEL", "gpt-4o-mini")
        CONFIDENCE_THRESHOLD: float = float(os.getenv("CONFIDENCE_THRESHOLD", "0.80"))
        ENVIRONMENT: str = os.getenv("ENVIRONMENT", "development")
        PORT: int = int(os.getenv("BACKEND_PORT", "8000"))



settings = Settings()
