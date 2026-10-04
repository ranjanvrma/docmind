"""Application configuration loaded from environment variables.

All tunable values live here so that the rest of the code never reads
``os.environ`` directly. Values come from the process environment, optionally
populated from a local ``.env`` file (see ``.env.example``).
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path

from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parent.parent

DEFAULT_CATEGORIES = ["Research Paper", "Report", "Assignment", "Notes", "Policy", "Other"]
VALID_EFFORTS = {"low", "medium", "high", "xhigh", "max"}
VALID_LOG_LEVELS = {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}
VALID_APP_ENVS = {"development", "production"}


def _env_str(name: str, default: str) -> str:
    value = os.getenv(name)
    return value.strip() if value and value.strip() else default


def _env_int(name: str, default: int) -> int:
    raw = os.getenv(name)
    if raw is None or not raw.strip():
        return default
    try:
        return int(raw)
    except ValueError as exc:
        raise ValueError(f"Environment variable {name} must be an integer, got {raw!r}") from exc


def _env_float(name: str, default: float) -> float:
    raw = os.getenv(name)
    if raw is None or not raw.strip():
        return default
    try:
        return float(raw)
    except ValueError as exc:
        raise ValueError(f"Environment variable {name} must be a number, got {raw!r}") from exc


def _env_bool(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None or not raw.strip():
        return default
    value = raw.strip().lower()
    if value in {"1", "true", "yes", "on"}:
        return True
    if value in {"0", "false", "no", "off"}:
        return False
    raise ValueError(f"Environment variable {name} must be true or false, got {raw!r}")


def _env_list(name: str, default: list[str]) -> list[str]:
    raw = os.getenv(name)
    if raw is None or not raw.strip():
        return list(default)
    return [item.strip() for item in raw.split(",") if item.strip()]


@dataclass
class Settings:
    # Storage
    data_dir: Path = PROJECT_ROOT / "data"

    # Embeddings
    embedding_model: str = "sentence-transformers/all-MiniLM-L6-v2"
    embedding_batch_size: int = 32

    # Chunking (measured in characters)
    chunk_size: int = 800
    chunk_overlap: int = 150

    # Retrieval
    top_k: int = 5
    max_top_k: int = 20

    # LLM
    llm_provider: str = "anthropic"  # "anthropic" | "openai" (OpenAI-compatible chat-completions API)
    llm_api_key: str = field(default="", repr=False)  # never shown in repr/logs
    llm_model: str = "claude-opus-5"
    llm_base_url: str = ""  # only used by the OpenAI-compatible provider
    llm_max_tokens: int = 8192  # thinking-capable models count reasoning tokens here too
    llm_effort: str = ""  # Anthropic only: low|medium|high|xhigh|max; empty = model default
    llm_temperature: float = 0.0  # sent only by the OpenAI-compatible client; AnthropicClient never passes it
    llm_timeout_seconds: float = 60.0
    max_context_chars: int = 6000

    # Ingestion limits
    max_upload_mb: int = 25  # per file
    max_request_mb: int = 100  # whole upload request, checked before the body is read
    max_pages: int = 500  # per document
    min_chars_per_page: int = 20  # pages with fewer characters are treated as empty

    # API access
    api_token: str = field(default="", repr=False)  # if set, required on every endpoint except /health
    cors_allow_origins: list[str] = field(default_factory=list)  # empty = no CORS headers at all

    # Classification
    classifier_labels: list[str] = field(default_factory=lambda: list(DEFAULT_CATEGORIES))

    # Logging
    log_level: str = "INFO"

    # Deployment profile. "production" refuses to start without DOCMIND_API_TOKEN
    # and hides the interactive API docs unless API_DOCS=true.
    app_env: str = "development"
    api_docs: bool = True  # serve /api/docs and /api/openapi.json

    # Built React UI (web/dist). Served by the API if it exists.
    web_dist_dir: Path = PROJECT_ROOT / "web" / "dist"

    @property
    def raw_dir(self) -> Path:
        return self.data_dir / "raw"

    @property
    def processed_dir(self) -> Path:
        return self.data_dir / "processed"

    @property
    def index_dir(self) -> Path:
        return self.data_dir / "index"

    @property
    def classifier_model_path(self) -> Path:
        return self.data_dir / "classifier" / "classifier.joblib"

    @property
    def max_upload_bytes(self) -> int:
        return self.max_upload_mb * 1024 * 1024

    @property
    def max_request_bytes(self) -> int:
        return self.max_request_mb * 1024 * 1024

    @property
    def llm_configured(self) -> bool:
        return bool(self.llm_api_key and self.llm_model)

    def validate(self) -> None:
        if self.chunk_size <= 0:
            raise ValueError("CHUNK_SIZE must be positive")
        if not 0 <= self.chunk_overlap < self.chunk_size:
            raise ValueError("CHUNK_OVERLAP must be >= 0 and smaller than CHUNK_SIZE")
        if not 1 <= self.top_k <= self.max_top_k:
            raise ValueError(f"TOP_K must be between 1 and {self.max_top_k}")
        if self.llm_provider not in {"anthropic", "openai"}:
            raise ValueError("LLM_PROVIDER must be 'anthropic' or 'openai'")
        if not self.classifier_labels:
            raise ValueError("CLASSIFIER_LABELS must contain at least one label")
        if self.llm_effort and self.llm_effort not in VALID_EFFORTS:
            raise ValueError(f"LLM_EFFORT must be empty or one of {sorted(VALID_EFFORTS)}")
        for name in ("embedding_batch_size", "llm_max_tokens", "max_context_chars", "max_upload_mb", "max_pages"):
            if getattr(self, name) <= 0:
                raise ValueError(f"{name.upper()} must be positive")
        if self.llm_timeout_seconds <= 0:
            raise ValueError("LLM_TIMEOUT_SECONDS must be positive")
        if self.max_request_mb < self.max_upload_mb:
            raise ValueError("MAX_REQUEST_MB must be at least MAX_UPLOAD_MB")
        if self.llm_base_url and not self.llm_base_url.startswith(("http://", "https://")):
            raise ValueError("LLM_BASE_URL must start with http:// or https://")
        if not self.llm_model:
            raise ValueError("LLM_MODEL must not be empty")
        if self.app_env not in VALID_APP_ENVS:
            raise ValueError(f"APP_ENV must be one of {sorted(VALID_APP_ENVS)}")
        if self.app_env == "production" and not self.api_token:
            raise ValueError(
                "APP_ENV=production requires DOCMIND_API_TOKEN; without it anyone who can reach the server "
                "can read and delete every document"
            )
        for origin in self.cors_allow_origins:
            if origin == "*" or not origin.startswith(("http://", "https://")) or origin.endswith("/"):
                raise ValueError(
                    f"CORS_ALLOW_ORIGINS entries must be exact origins like https://app.example.com "
                    f"(no wildcard, no trailing slash); got {origin!r}"
                )
        if self.log_level not in VALID_LOG_LEVELS:
            raise ValueError(f"LOG_LEVEL must be one of {sorted(VALID_LOG_LEVELS)}")

    def ensure_dirs(self) -> None:
        """Create the data directories and check that they are writable.

        Raises OSError (e.g. PermissionError on a volume owned by another user).
        """
        for directory in (self.raw_dir, self.processed_dir, self.index_dir, self.classifier_model_path.parent):
            directory.mkdir(parents=True, exist_ok=True)
        probe = self.data_dir / ".write-test"
        probe.write_bytes(b"")
        probe.unlink()


def load_settings() -> Settings:
    """Build settings from the environment (and a .env file if present)."""
    load_dotenv(PROJECT_ROOT / ".env", override=False)
    settings = Settings(
        data_dir=Path(_env_str("DATA_DIR", str(PROJECT_ROOT / "data"))),
        embedding_model=_env_str("EMBEDDING_MODEL", Settings.embedding_model),
        embedding_batch_size=_env_int("EMBEDDING_BATCH_SIZE", Settings.embedding_batch_size),
        chunk_size=_env_int("CHUNK_SIZE", Settings.chunk_size),
        chunk_overlap=_env_int("CHUNK_OVERLAP", Settings.chunk_overlap),
        top_k=_env_int("TOP_K", Settings.top_k),
        llm_provider=_env_str("LLM_PROVIDER", Settings.llm_provider).lower(),
        llm_api_key=os.getenv("LLM_API_KEY", "").strip(),
        llm_model=_env_str("LLM_MODEL", Settings.llm_model),
        llm_base_url=_env_str("LLM_BASE_URL", ""),
        llm_max_tokens=_env_int("LLM_MAX_TOKENS", Settings.llm_max_tokens),
        llm_effort=_env_str("LLM_EFFORT", "").lower(),
        llm_temperature=_env_float("LLM_TEMPERATURE", Settings.llm_temperature),
        llm_timeout_seconds=_env_float("LLM_TIMEOUT_SECONDS", Settings.llm_timeout_seconds),
        max_context_chars=_env_int("MAX_CONTEXT_CHARS", Settings.max_context_chars),
        max_upload_mb=_env_int("MAX_UPLOAD_MB", Settings.max_upload_mb),
        max_request_mb=_env_int("MAX_REQUEST_MB", Settings.max_request_mb),
        max_pages=_env_int("MAX_PAGES", Settings.max_pages),
        api_token=os.getenv("DOCMIND_API_TOKEN", "").strip(),
        cors_allow_origins=_env_list("CORS_ALLOW_ORIGINS", []),
        min_chars_per_page=_env_int("MIN_CHARS_PER_PAGE", Settings.min_chars_per_page),
        classifier_labels=_env_list("CLASSIFIER_LABELS", DEFAULT_CATEGORIES),
        log_level=_env_str("LOG_LEVEL", "INFO").upper(),
        app_env=_env_str("APP_ENV", "development").lower(),
        api_docs=_env_bool("API_DOCS", os.getenv("APP_ENV", "").strip().lower() != "production"),
        web_dist_dir=Path(_env_str("WEB_DIST_DIR", str(PROJECT_ROOT / "web" / "dist"))),
    )
    settings.validate()
    return settings


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Process-wide settings singleton."""
    return load_settings()
