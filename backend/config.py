from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    klangio_api_key: str = ""
    output_dir: str = ""
    default_engine: str = "klangio"  # "klangio" or "opensource"
    port: int = 8765


settings = Settings()
