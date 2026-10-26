from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

_ENV_FILE = Path(__file__).resolve().parent / ".env"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=_ENV_FILE, extra="ignore")

    mongodb_uri: str
    mongodb_db: str = "vendor_portal_qas"
    search_index_name: str = "pr"
    collection_name: str = "PurRequisitions"
    cors_origins: str = "http://localhost:4000"
    search_result_limit: int = 50

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]


_settings: Settings | None = None
_env_mtime_ns: int | None = None


def get_settings() -> Settings:
    """Re-read backend/.env when the file changes, so a page refresh picks up COLLECTION_NAME."""
    global _settings, _env_mtime_ns
    try:
        mtime_ns = _ENV_FILE.stat().st_mtime_ns
    except FileNotFoundError:
        mtime_ns = None
    if _settings is None or mtime_ns != _env_mtime_ns:
        _settings = Settings()
        _env_mtime_ns = mtime_ns
    return _settings


settings = get_settings()
