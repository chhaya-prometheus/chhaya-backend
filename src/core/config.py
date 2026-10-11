from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    PROJECT_NAME: str = "Chhaya Backend"
    API_PORT: int = 8000
    ROOT_PATH: str = ""

    # Logging
    LOG_LEVEL: str = "INFO"
    LOG_TO_FILE: bool = False

    # AWS & S3 Settings
    AWS_REGION: str = "ap-south-1"
    S3_BUCKET: str = ""
    S3_PREFIX: str = "features"
    REFRESH_SECONDS: int = 300

    # Comma-separated list of allowed frontend origins, or "*" for all
    CORS_ORIGINS: str = "*"

    # PostgreSQL Settings
    POSTGRES_USER: str = "postgres"
    POSTGRES_PASSWORD: str = "chhaya"
    POSTGRES_SERVER: str = "localhost"
    POSTGRES_PORT: int = 5432
    POSTGRES_DB: str = "chhaya_db"


settings = Settings()