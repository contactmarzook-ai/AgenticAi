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


def _jwt_secret() -> str:
    # No hard-coded fallback. Outside production an unset secret becomes a random per-process
    # value (sessions end on restart); production refuses to start without JWT_SECRET (validate()).
    value = os.getenv("JWT_SECRET", "")
    if value or os.getenv("APP_ENV", "development").lower() == "production":
        return value
    import secrets

    return secrets.token_urlsafe(48)


DEV_CREDENTIALS_KEY = "dev-only-insecure-credentials-key"


@dataclass(frozen=True)
class Settings:
    app_env: str = field(default_factory=lambda: os.getenv("APP_ENV", "development"))
    database_url: str = field(default_factory=lambda: os.getenv("DATABASE_URL", "sqlite:///./agentos.db"))

    # Auth
    jwt_secret: str = field(default_factory=_jwt_secret)
    # Encrypts saved connection secrets. Changing it makes existing connections unreadable.
    credentials_key: str = field(default_factory=lambda: os.getenv("CREDENTIALS_KEY", DEV_CREDENTIALS_KEY))
    # Access tokens are short-lived; the browser renews them with the refresh cookie until the
    # session's absolute lifetime (REFRESH_EXPIRE_HOURS) ends or the user signs out.
    jwt_expire_minutes: int = field(default_factory=lambda: _int("JWT_EXPIRE_MINUTES", 15))
    refresh_expire_hours: int = field(default_factory=lambda: _int("REFRESH_EXPIRE_HOURS", 12))
    # Secure cookies need HTTPS; defaults to on in production.
    cookie_secure: bool = field(
        default_factory=lambda: _bool("COOKIE_SECURE", os.getenv("APP_ENV", "development").lower() == "production")
    )
    # Set to false to allow only Microsoft sign-in (bootstrap/platform admins can still use passwords).
    local_login_enabled: bool = field(default_factory=lambda: _bool("LOCAL_LOGIN_ENABLED", True))
    auth_requests_per_minute: int = field(default_factory=lambda: _int("AUTH_REQUESTS_PER_MINUTE", 60))
    public_requests_per_minute: int = field(default_factory=lambda: _int("PUBLIC_REQUESTS_PER_MINUTE", 60))
    max_request_bytes: int = field(default_factory=lambda: _int("MAX_REQUEST_BYTES", 2_000_000))

    # Microsoft Entra ID (OIDC). Sign-in is enabled only when tenant, client id, secret and
    # redirect URI are all set.
    oidc_tenant_id: str = field(default_factory=lambda: os.getenv("OIDC_TENANT_ID", ""))
    oidc_client_id: str = field(default_factory=lambda: os.getenv("OIDC_CLIENT_ID", ""))
    oidc_client_secret: str = field(default_factory=lambda: os.getenv("OIDC_CLIENT_SECRET", ""))
    oidc_redirect_uri: str = field(default_factory=lambda: os.getenv("OIDC_REDIRECT_URI", ""))
    oidc_authority: str = field(
        default_factory=lambda: os.getenv("OIDC_AUTHORITY", "https://login.microsoftonline.com").rstrip("/")
    )
    # JSON object: Entra app-role value or group object id -> Star Dust role (never platform_admin).
    oidc_role_map: str = field(default_factory=lambda: os.getenv("OIDC_ROLE_MAP", "{}"))
    # Role for first-time users with no mapped role; empty = refuse them until an admin adds them.
    oidc_default_role: str = field(default_factory=lambda: os.getenv("OIDC_DEFAULT_ROLE", ""))
    oidc_org_slug: str = field(default_factory=lambda: os.getenv("OIDC_ORG_SLUG", "default"))
    oidc_allowed_domains: list[str] = field(default_factory=lambda: _list("OIDC_ALLOWED_DOMAINS"))
    login_max_attempts: int = field(default_factory=lambda: _int("LOGIN_MAX_ATTEMPTS", 5))
    login_ip_failures_per_10min: int = field(default_factory=lambda: _int("LOGIN_IP_FAILURES_PER_10MIN", 30))
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
    user_max_concurrent_runs: int = field(default_factory=lambda: _int("USER_MAX_CONCURRENT_RUNS", 5))
    user_runs_per_minute: int = field(default_factory=lambda: _int("USER_RUNS_PER_MINUTE", 30))

    # Tools
    http_tool_allowed_hosts: list[str] = field(default_factory=lambda: _list("HTTP_TOOL_ALLOWED_HOSTS"))

    # HTTP
    cors_origins: list[str] = field(default_factory=lambda: _list("CORS_ORIGINS", "http://localhost:5173"))
    auto_create_tables: bool = field(default_factory=lambda: _bool("AUTO_CREATE_TABLES", True))
    log_level: str = field(default_factory=lambda: os.getenv("LOG_LEVEL", "INFO"))
    log_json: bool = field(default_factory=lambda: _bool("LOG_JSON", False))

    @property
    def oidc_enabled(self) -> bool:
        return bool(self.oidc_tenant_id and self.oidc_client_id and self.oidc_client_secret and self.oidc_redirect_uri)

    @property
    def is_production(self) -> bool:
        return self.app_env.lower() == "production"

    def validate(self) -> None:
        if not self.is_production:
            return
        problems = []
        if len(self.jwt_secret) < 32 or self.jwt_secret.startswith("change-me"):
            problems.append("JWT_SECRET must be set to a random value of at least 32 characters")
        if (
            self.credentials_key == DEV_CREDENTIALS_KEY
            or len(self.credentials_key) < 32
            or self.credentials_key.startswith("change-me")
        ):
            problems.append("CREDENTIALS_KEY must be set to a random value of at least 32 characters")
        if "change-me" in self.database_url:
            problems.append("DATABASE_URL still contains the placeholder password 'change-me'")
        if self.database_url.startswith("sqlite"):
            problems.append("DATABASE_URL must point to PostgreSQL in production")
        if self.auto_create_tables:
            problems.append("AUTO_CREATE_TABLES must be false in production (use Alembic migrations)")
        if "*" in self.cors_origins:
            problems.append("CORS_ORIGINS must list explicit origins, not '*'")
        if self.jwt_expire_minutes > 60:
            problems.append("JWT_EXPIRE_MINUTES must be at most 60 in production (sessions renew automatically)")
        if self.oidc_enabled and not self.oidc_redirect_uri.startswith("https://"):
            problems.append("OIDC_REDIRECT_URI must use https:// in production")
        if problems:
            raise RuntimeError("Refusing to start: " + "; ".join(problems))


settings = Settings()
