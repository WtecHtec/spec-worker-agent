from pydantic_settings import BaseSettings, SettingsConfigDict
from functools import lru_cache


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # ── PostgreSQL ──────────────────────────────
    pg_host: str = "localhost"
    pg_port: int = 5432
    pg_user: str = "postgres"
    pg_password: str = "postgres"
    pg_db: str = "app"
    pg_pool_size: int = 10
    pg_max_overflow: int = 20
    pg_pool_timeout: int = 30

    @property
    def database_url(self) -> str:
        return (
            f"postgresql+asyncpg://{self.pg_user}:{self.pg_password}"
            f"@{self.pg_host}:{self.pg_port}/{self.pg_db}"
        )

    @property
    def database_url_sync(self) -> str:
        """Alembic 迁移使用同步驱动"""
        return (
            f"postgresql+psycopg2://{self.pg_user}:{self.pg_password}"
            f"@{self.pg_host}:{self.pg_port}/{self.pg_db}"
        )

    # ── Redis ───────────────────────────────────
    redis_host: str = "localhost"
    redis_port: int = 6379
    redis_password: str = ""
    redis_db: int = 0
    redis_max_connections: int = 20

    @property
    def redis_url(self) -> str:
        if self.redis_password:
            return f"redis://:{self.redis_password}@{self.redis_host}:{self.redis_port}/{self.redis_db}"
        return f"redis://{self.redis_host}:{self.redis_port}/{self.redis_db}"

    # ── JWT ─────────────────────────────────────
    jwt_secret: str = "dev-secret-change-in-production-min-32-chars"
    jwt_algorithm: str = "HS256"
    jwt_expire_minutes: int = 10080  # 7 days

    # ── Agent Executor & LLM ────────────────────
    agent_mode: str = "llm"  # mock | llm
    mock_files_dir: str = "./src/infrastructure/executor/mock_data"

    llm_provider: str = "openai_compatible"
    llm_base_url: str = "https://api.siliconflow.cn/v1"
    llm_api_key: str = ""
    llm_model: str = "Qwen/Qwen3-8B"
    llm_temperature: float = 0.2
    llm_timeout: int = 120
    llm_max_retries: int = 3
    llm_max_steps: int = 15
    llm_workspace_dir: str = "./workspace"

    # ── Flow & Agent Circuit Breaker Limits ─────
    agent_flow_max_steps: int = 100  # PlanAndExecuteFlow 全局最大事件防失控熔断步数
    agent_flow_max_replans: int = 3  # 最大动态重规划次数

    # ── Sandbox ─────────────────────────────────
    sandbox_enabled: bool = True
    sandbox_url: str = "http://localhost:5050"
    sandbox_timeout: int = 60


    # ── Worker ──────────────────────────────────
    worker_concurrency: int = 4
    worker_heartbeat_interval: int = 10
    worker_heartbeat_timeout: int = 60
    worker_graceful_shutdown_timeout: int = 30
    redis_stream_max_len: int = 10000
    redis_consumer_group: str = "workers"
    redis_stream_name: str = "task_queue"

    # ── HITL ────────────────────────────────────
    hitl_default_timeout_hours: int = 24
    hitl_default_action: str = "cancel"

    # ── App & Security ──────────────────────────
    app_env: str = "development"
    app_host: str = "0.0.0.0"
    app_port: int = 8000
    log_level: str = "INFO"
    cors_origins: str = "http://localhost:3000"
    rate_limit_enabled: bool = True
    rate_limit_requests_per_minute: int = 120

    @property
    def cors_origins_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",")]


@lru_cache
def get_settings() -> Settings:
    return Settings()
