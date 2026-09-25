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
    llm_provider: str = "anthropic"  # "anthropic" | "openai" (any OpenAI-compatible API)
    llm_api_key: str = ""
    llm_model: str = "claude-opus-5"
    llm_base_url: str = ""  # only used by the OpenAI-compatible provider
    llm_max_tokens: int = 4096  # thinking-capable models count reasoning tokens here too
    llm_temperature: float = 0.0  # ignored by providers/models that don't accept it
    llm_timeout_seconds: float = 60.0
    max_context_chars: int = 6000

    # Ingestion limits
    max_upload_mb: int = 25
    min_chars_per_page: int = 20  # pages with fewer characters are treated as empty

    # Classification
    classifier_labels: list[str] = field(default_factory=lambda: list(DEFAULT_CATEGORIES))

    # Logging
    log_level: str = "INFO"

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

    def ensure_dirs(self) -> None:
        for directory in (self.raw_dir, self.processed_dir, self.index_dir, self.classifier_model_path.parent):
            directory.mkdir(parents=True, exist_ok=True)


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
        llm_temperature=_env_float("LLM_TEMPERATURE", Settings.llm_temperature),
        llm_timeout_seconds=_env_float("LLM_TIMEOUT_SECONDS", Settings.llm_timeout_seconds),
        max_context_chars=_env_int("MAX_CONTEXT_CHARS", Settings.max_context_chars),
        max_upload_mb=_env_int("MAX_UPLOAD_MB", Settings.max_upload_mb),
        min_chars_per_page=_env_int("MIN_CHARS_PER_PAGE", Settings.min_chars_per_page),
        classifier_labels=_env_list("CLASSIFIER_LABELS", DEFAULT_CATEGORIES),
        log_level=_env_str("LOG_LEVEL", "INFO").upper(),
    )
    settings.validate()
    return settings


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Process-wide settings singleton."""
    return load_settings()
