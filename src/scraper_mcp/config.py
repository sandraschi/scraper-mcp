"""scraper-mcp configuration — Pydantic settings."""

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    host: str = "127.0.0.1"
    port: int = 10998
    webapp_port: int = 10999
    transport: str = "http"
    http_path: str = "/mcp"

    model_config = {
        "env_prefix": "SCRAPER_MCP_",
        "env_file": ".env",
        "extra": "ignore",
    }


settings = Settings()
