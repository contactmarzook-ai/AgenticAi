"""Application settings, read once from environment variables.

Every setting has a safe development default. In production
(APP_ENV=production) `validate()` refuses to start with insecure defaults.
"""

import os
from dataclasses import dataclass, field


def _bool(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _int(name: str, default: int) -> int:
    raw = os.getenv(name)
    return int(raw) if raw not in (None, "") else default


def _list(name: str, default: str = "") -> list[str]:
    return [item.strip() for item in os.getenv(name, default).split(",") if item.strip()]


DEV_JWT_SECRET = "dev-only-insecure-secret-change-me"
DEV_CREDENTIALS_KEY = "dev-only-insecure-credentials-key"


@dataclass(frozen=True)
class Settings:
    app_env: str = field(default_factory=lambda: os.getenv("APP_ENV", "development"))
    database_url: str = field(default_factory=lambda: os.getenv("DATABASE_URL", "sqlite:///./agentos.db"))

    # Auth
    jwt_secret: str = field(default_factory=lambda: os.getenv("JWT_SECRET", DEV_JWT_SECRET))
    # Encrypts saved connection secrets. Changing it makes existing connections unreadable.
    credentials_key: str = field(default_factory=lambda: os.getenv("CREDENTIALS_KEY", DEV_CREDENTIALS_KEY))
    jwt_expire_minutes: int = field(default_factory=lambda: _int("JWT_EXPIRE_MINUTES", 480))
    login_max_attempts: int = field(default_factory=lambda: _int("LOGIN_MAX_ATTEMPTS", 5))
    login_lockout_minutes: int = field(default_factory=lambda: _int("LOGIN_LOCKOUT_MINUTES", 15))
    bcrypt_rounds: int = field(default_factory=lambda: _int("BCRYPT_ROUNDS", 12))
    password_min_length: int = field(default_factory=lambda: _int("PASSWORD_MIN_LENGTH", 12))

    # First-run admin (only used when the users table is empty)
    bootstrap_admin_email: str = field(default_factory=lambda: os.getenv("BOOTSTRAP_ADMIN_EMAIL", ""))
    bootstrap_admin_password: str = field(default_factory=lambda: os.getenv("BOOTSTRAP_ADMIN_PASSWORD", ""))

    # Default LLM provider (seeded only when no providers exist)
    llm_base_url: str = field(default_factory=lambda: os.getenv("LLM_BASE_URL", "http://localhost:11434/v1"))
    llm_api_key_env: str = field(default_factory=lambda: os.getenv("LLM_API_KEY_ENV", ""))
    llm_default_model: str = field(default_factory=lambda: os.getenv("LLM_DEFAULT_MODEL", "qwen2.5:7b-instruct"))
    llm_timeout_seconds: int = field(default_factory=lambda: _int("LLM_TIMEOUT_SECONDS", 120))

    # Execution limits
    agent_max_steps_cap: int = field(default_factory=lambda: _int("AGENT_MAX_STEPS_CAP", 15))
    agent_timeout_seconds: int = field(default_factory=lambda: _int("AGENT_TIMEOUT_SECONDS", 300))
    tool_timeout_seconds: int = field(default_factory=lambda: _int("TOOL_TIMEOUT_SECONDS", 30))
    workflow_max_nodes: int = field(default_factory=lambda: _int("WORKFLOW_MAX_NODES", 50))
    workflow_timeout_seconds: int = field(default_factory=lambda: _int("WORKFLOW_TIMEOUT_SECONDS", 900))
    run_worker_threads: int = field(default_factory=lambda: _int("RUN_WORKER_THREADS", 4))
    chat_history_messages: int = field(default_factory=lambda: _int("CHAT_HISTORY_MESSAGES", 10))
    max_message_chars: int = field(default_factory=lambda: _int("MAX_MESSAGE_CHARS", 8000))

    # Per-user rate limit on chat messages and runs (0 disables)
    user_runs_per_minute: int = field(default_factory=lambda: _int("USER_RUNS_PER_MINUTE", 30))

    # Tools
    http_tool_allowed_hosts: list[str] = field(default_factory=lambda: _list("HTTP_TOOL_ALLOWED_HOSTS"))

    # HTTP
    cors_origins: list[str] = field(default_factory=lambda: _list("CORS_ORIGINS", "http://localhost:5173"))
    auto_create_tables: bool = field(default_factory=lambda: _bool("AUTO_CREATE_TABLES", True))
    log_level: str = field(default_factory=lambda: os.getenv("LOG_LEVEL", "INFO"))
    log_json: bool = field(default_factory=lambda: _bool("LOG_JSON", False))

    @property
    def is_production(self) -> bool:
        return self.app_env.lower() == "production"

    def validate(self) -> None:
        if not self.is_production:
            return
        problems = []
        if self.jwt_secret == DEV_JWT_SECRET or len(self.jwt_secret) < 32:
            problems.append("JWT_SECRET must be set to a random value of at least 32 characters")
        if self.credentials_key == DEV_CREDENTIALS_KEY or len(self.credentials_key) < 32:
            problems.append("CREDENTIALS_KEY must be set to a random value of at least 32 characters")
        if self.database_url.startswith("sqlite"):
            problems.append("DATABASE_URL must point to PostgreSQL in production")
        if self.auto_create_tables:
            problems.append("AUTO_CREATE_TABLES must be false in production (use Alembic migrations)")
        if problems:
            raise RuntimeError("Refusing to start: " + "; ".join(problems))


settings = Settings()
