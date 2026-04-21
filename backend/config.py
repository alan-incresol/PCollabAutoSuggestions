from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    mongodb_uri: str
    mongodb_db: str = "pcollab-quality"
    search_index_name: str = "vendorDetails-lucene"
    collection_name: str = "omOrgVendorDetails"
    cors_origins: str = "http://localhost:4000"
    search_result_limit: int = 50

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]


settings = Settings()
