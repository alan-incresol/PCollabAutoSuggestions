from pathlib import Path

from pydantic_settings import BaseSettings, PydanticBaseSettingsSource, SettingsConfigDict

ENV_FILE = Path(__file__).resolve().parent / ".env"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=ENV_FILE, extra="ignore")

    mongodb_uri: str
    mongodb_db: str = "vendor_portal_demos"
    cors_origins: str = "http://localhost:4000"

    typesafe_api_key: str = ""
    jev_model: str = "jev-1.13.0"
    jev_candidate_limit: int = 10
    jev_confidence_threshold: float = 0.5
    jev_timeout_seconds: float = 30

    lexical_limit: int = 20
    vector_limit: int = 20
    vector_num_candidates: int = 200
    hybrid_result_limit: int = 15

    vendor_collection: str = "OmOrgVendorDetails"
    material_collection: str = "MaterialMaster"
    vendor_lucene_index: str = "vendor-master"
    material_lucene_index: str = "material-master"
    vendor_vector_index: str = "vendor-master-vector"
    material_vector_index: str = "material-master-vector"

    @classmethod
    def settings_customise_sources(
        cls,
        settings_cls: type[BaseSettings],
        init_settings: PydanticBaseSettingsSource,
        env_settings: PydanticBaseSettingsSource,
        dotenv_settings: PydanticBaseSettingsSource,
        file_secret_settings: PydanticBaseSettingsSource,
    ) -> tuple[PydanticBaseSettingsSource, ...]:
        return init_settings, dotenv_settings, env_settings, file_secret_settings

    @property
    def cors_origin_list(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]

    @property
    def typesafe_key(self) -> str:
        return self.typesafe_api_key.strip()


_settings: Settings | None = None
_env_mtime_ns: int | None = None


def get_settings() -> Settings:
    global _settings, _env_mtime_ns
    try:
        mtime_ns = ENV_FILE.stat().st_mtime_ns
    except FileNotFoundError:
        mtime_ns = None
    if _settings is None or mtime_ns != _env_mtime_ns:
        _settings = Settings()
        _env_mtime_ns = mtime_ns
    return _settings
