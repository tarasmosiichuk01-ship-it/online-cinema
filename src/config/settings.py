from pathlib import Path
from pydantic_settings import BaseSettings, SettingsConfigDict

BASE_DIR = Path(__file__).resolve().parent.parent.parent

class BaseAppSettings(BaseSettings):
    PATH_TO_EMAIL_TEMPLATES_DIR: str = str(
        Path(__file__).parent.parent / "notifications" / "templates"
    )
    ACTIVATION_EMAIL_TEMPLATE_NAME: str = "activation_request.html"
    ACTIVATION_COMPLETE_EMAIL_TEMPLATE_NAME: str = "activation_complete.html"
    PASSWORD_RESET_TEMPLATE_NAME: str = "password_reset_request.html"

    LOGIN_TIME_DAYS: int = 7

    EMAIL_HOST: str
    EMAIL_PORT: int
    EMAIL_HOST_USER: str
    EMAIL_HOST_PASSWORD: str
    EMAIL_USE_TLS: bool
    MAILHOG_API_PORT: int

    JWT_SIGNING_ALGORITHM: str

    model_config = SettingsConfigDict(
        env_file=str(BASE_DIR / ".env"),
        extra="ignore"
    )


class Settings(BaseAppSettings):
    POSTGRES_USER: str
    POSTGRES_PASSWORD: str
    POSTGRES_HOST: str
    POSTGRES_DB_PORT: int = 5432
    POSTGRES_DB: str

    SECRET_KEY_ACCESS: str
    SECRET_KEY_REFRESH: str

    MINIO_ROOT_USER: str
    MINIO_ROOT_PASSWORD: str
    MINIO_HOST: str
    MINIO_PORT: int
    MINIO_STORAGE: str

    CELERY_BROKER_URL: str
    CELERY_RESULT_BACKEND: str

    @property
    def postgres_database_url(self) -> str:
        return (
            f"postgresql+asyncpg://{self.POSTGRES_USER}:{self.POSTGRES_PASSWORD}@"
            f"{self.POSTGRES_HOST}:{self.POSTGRES_DB_PORT}/{self.POSTGRES_DB}"
        )

settings = Settings()
