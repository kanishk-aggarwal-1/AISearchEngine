from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    openai_api_key: str = ""
    gemini_api_key: str = ""
    newsapi_key: str = ""
    app_base_url: str = "http://localhost:3000"
    database_url: str = ""
    sqlite_database_path: str = "data/retriever.db"

    max_fetch_per_source: int = 10
    http_timeout_seconds: int = 10

    scheduler_interval_minutes: int = 60
    frontend_origin: str = "http://localhost:3000"
    extra_frontend_origins: str = "http://127.0.0.1:3000"
    query_cache_minutes: int = 20

    cache_backend: str = "redis"
    redis_url: str = "redis://localhost:6379/0"
    redis_prefix: str = "signalscope"

    embedding_model: str = "text-embedding-3-small"
    explanation_model: str = "gpt-4.1-mini"
    strict_real_embeddings: bool = True
    email_preview_tokens: bool = False
    smtp_host: str = ""
    smtp_port: int = 587
    smtp_username: str = ""
    smtp_password: str = ""
    smtp_from_email: str = ""
    smtp_from_name: str = "SignalScope AI"
    smtp_use_tls: bool = True
    smtp_use_ssl: bool = False

    semantic_weight: float = 1.8
    lexical_weight: float = 1.6
    recency_weight: float = 0.9
    credibility_weight: float = 0.8
    personalization_weight: float = 0.9
    chunk_weight: float = 1.2
    exact_phrase_weight: float = 0.9
    coverage_weight: float = 0.8
    title_match_weight: float = 0.5
    source_diversity_penalty: float = 0.35
    chunk_max_chars: int = 320
    chunk_top_k: int = 40

    vector_backend: str = "qdrant"
    qdrant_url: str = ""
    qdrant_api_key: str = ""
    qdrant_collection: str = "signalscope_docs"
    vector_top_k: int = 120

    enable_metrics: bool = True
    log_level: str = "INFO"
    rate_limit_per_minute: int = 90

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    @property
    def db_path(self) -> str:
        return self.sqlite_database_path

    @property
    def using_postgres(self) -> bool:
        normalized = self.database_url.strip().lower()
        return normalized.startswith(("postgres://", "postgresql://", "postgresql+psycopg://"))


settings = Settings()
