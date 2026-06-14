import os
from typing import Annotated, Self

from pydantic import field_validator, model_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    supabase_url: str
    supabase_anon_key: str
    supabase_service_role_key: str
    database_url: str
    openai_api_key: str
    openai_embedding_model: str = "text-embedding-3-small"
    openai_embedding_dimensions: int = 1536
    allowed_origins: Annotated[list[str], NoDecode]

    @field_validator("allowed_origins", mode="before")
    @classmethod
    def parse_allowed_origins(cls, value: object) -> list[str]:
        if isinstance(value, str):
            origins = [origin.strip() for origin in value.split(",") if origin.strip()]
            if not origins:
                raise ValueError("ALLOWED_ORIGINS must list at least one origin")
            return origins
        if isinstance(value, list):
            return value
        raise ValueError("ALLOWED_ORIGINS must be a comma-separated string")

    @model_validator(mode="after")
    def mirror_openai_api_key(self) -> Self:
        # OpenAI SDK reads OPENAI_API_KEY from the environment directly.
        os.environ["OPENAI_API_KEY"] = self.openai_api_key
        return self


settings = Settings()
