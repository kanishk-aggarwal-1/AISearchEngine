from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    openai_api_key: str = ""
    gemini_api_key: str = ""
    newsapi_key: str = ""

    max_fetch_per_source: int = 10
    http_timeout_seconds: int = 10
    db_path: str = "data/retriever.db"

    scheduler_interval_minutes: int = 60
    frontend_origin: str = "http://localhost:3000"
    query_cache_minutes: int = 20

    embedding_model: str = "text-embedding-3-small"
    explanation_model: str = "gpt-4.1-mini"
    strict_real_embeddings: bool = False

    semantic_weight: float = 1.8
    lexical_weight: float = 1.6
    recency_weight: float = 0.9
    credibility_weight: float = 0.8
    personalization_weight: float = 0.9

    vector_backend: str = "qdrant"
    qdrant_url: str = ""
    qdrant_api_key: str = ""
    qdrant_collection: str = "signalscope_docs"
    vector_top_k: int = 120

    enable_metrics: bool = True
    log_level: str = "INFO"

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")


settings = Settings()