"""Data models.

Two kinds of models live here:

* Domain objects (plain dataclasses) passed between pipeline stages.
* API schemas (Pydantic) that define the FastAPI request/response contract.

Keeping them side by side makes it easy to see how internal objects map onto
what the API exposes.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

# ---------------------------------------------------------------------------
# Domain objects
# ---------------------------------------------------------------------------


@dataclass
class PageText:
    """Text extracted from a single PDF page (page_number is 1-based)."""

    doc_id: str
    doc_name: str
    page_number: int
    text: str


@dataclass
class Chunk:
    """A retrievable unit of text with the metadata needed for citations."""

    chunk_id: str
    doc_id: str
    doc_name: str
    page_number: int
    chunk_index: int  # position of the chunk within its page
    text: str

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "Chunk":
        return cls(**{k: data[k] for k in cls.__dataclass_fields__})


@dataclass
class SearchResult:
    chunk: Chunk
    score: float  # cosine similarity in [-1, 1]
    rank: int  # 1-based


@dataclass
class ClassificationResult:
    label: str
    method: Literal["supervised", "zero-shot"]
    # supervised -> class probabilities; zero-shot -> raw cosine similarities.
    scores: dict[str, float] = field(default_factory=dict)


# uploaded -> queued -> processing -> processed | failed. queued/processing occur
# only with background processing; a synchronous request returns the result.
DocumentStatus = Literal["uploaded", "queued", "processing", "processed", "failed"]


@dataclass
class DocumentRecord:
    doc_id: str
    filename: str
    size_bytes: int
    uploaded_at: str
    status: DocumentStatus = "uploaded"
    page_count: int = 0
    empty_pages: list[int] = field(default_factory=list)
    chunk_count: int = 0
    warnings: list[str] = field(default_factory=list)
    error: str | None = None
    classification: dict | None = None
    processed_at: str | None = None

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "DocumentRecord":
        return cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})


# ---------------------------------------------------------------------------
# API schemas
# ---------------------------------------------------------------------------


class LimitsOut(BaseModel):
    max_upload_mb: int
    max_request_mb: int
    max_pages: int
    max_files_per_upload: int
    default_top_k: int
    max_top_k: int


class HealthResponse(BaseModel):
    status: Literal["ok"] = "ok"
    version: str
    embedding_model: str
    llm_provider: str
    llm_model: str
    llm_configured: bool
    auth_required: bool
    documents: int
    indexed_chunks: int
    limits: LimitsOut


class DocumentChunkOut(BaseModel):
    chunk_id: str
    page_number: int
    chunk_index: int
    text: str


class ClassificationOut(BaseModel):
    label: str
    method: str
    scores: dict[str, float]


class DocumentOut(BaseModel):
    doc_id: str
    filename: str
    size_bytes: int
    uploaded_at: str
    status: str
    page_count: int
    empty_pages: list[int]
    chunk_count: int
    warnings: list[str]
    error: str | None
    classification: ClassificationOut | None
    processed_at: str | None

    @classmethod
    def from_record(cls, record: DocumentRecord) -> "DocumentOut":
        return cls(**record.to_dict())


class UploadItem(BaseModel):
    filename: str
    status: Literal["uploaded", "duplicate", "rejected"]
    doc_id: str | None = None
    detail: str | None = None


class UploadResponse(BaseModel):
    items: list[UploadItem]


class ProcessRequest(BaseModel):
    doc_ids: list[str] | None = Field(
        default=None, description="Documents to process. Omit to process every unprocessed document."
    )
    force: bool = Field(default=False, description="Re-process documents that are already indexed.")
    background: bool = Field(
        default=False,
        description="Return 202 immediately and process on the server's worker; poll GET /api/documents for status.",
    )


class ProcessItem(BaseModel):
    doc_id: str
    filename: str
    status: str
    chunk_count: int
    skipped: bool = False
    detail: str | None = None


class ProcessResponse(BaseModel):
    items: list[ProcessItem]
    indexed_chunks: int


class _QueryBase(BaseModel):
    top_k: int | None = Field(default=None, ge=1, le=20)
    doc_ids: list[str] | None = Field(default=None, description="Restrict retrieval to these documents.")


class SearchRequest(_QueryBase):
    query: str = Field(..., min_length=1, max_length=2000)

    @field_validator("query")
    @classmethod
    def _not_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("query must not be blank")
        return value.strip()


class SearchHit(BaseModel):
    rank: int
    score: float
    chunk_id: str
    doc_id: str
    doc_name: str
    page_number: int
    text: str

    @classmethod
    def from_result(cls, result: SearchResult) -> "SearchHit":
        c = result.chunk
        return cls(
            rank=result.rank,
            score=round(result.score, 4),
            chunk_id=c.chunk_id,
            doc_id=c.doc_id,
            doc_name=c.doc_name,
            page_number=c.page_number,
            text=c.text,
        )


class SearchResponse(BaseModel):
    query: str
    top_k: int
    results: list[SearchHit]


class AskRequest(_QueryBase):
    question: str = Field(..., min_length=1, max_length=2000)

    @field_validator("question")
    @classmethod
    def _not_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("question must not be blank")
        return value.strip()


class SourceOut(SearchHit):
    source_number: int
    cited: bool


class AskResponse(BaseModel):
    question: str
    answer: str
    answered_from_documents: bool  # True only when grounding == "grounded"
    grounding: Literal["grounded", "not_found", "ungrounded"]
    sources: list[SourceOut]
    invalid_citations: list[int]
    # The model's raw reply when it could not be grounded in the sources even
    # after a retry. Not an answer: shown to users only as unverified output.
    unverified_answer: str | None = None
    model: str | None


class SettingsUpdate(BaseModel):
    """Fields present in the request are changed; everything else is left alone."""

    model_config = ConfigDict(extra="forbid")

    llm_provider: Literal["anthropic", "openai"] | None = None
    llm_model: str | None = Field(default=None, max_length=200)
    llm_base_url: str | None = Field(default=None, max_length=500)
    llm_effort: str | None = Field(default=None, max_length=10)
    llm_max_tokens: int | None = None
    llm_temperature: float | None = None
    llm_timeout_seconds: float | None = None
    llm_api_key: str | None = Field(default=None, max_length=500)  # write-only
    max_context_chars: int | None = None
    top_k: int | None = None
    min_relevance: float | None = None
    chunk_size: int | None = None
    chunk_overlap: int | None = None
    min_chars_per_page: int | None = None
    max_upload_mb: int | None = None
    max_request_mb: int | None = None
    max_pages: int | None = None
    classifier_labels: list[str] | None = None


class SettingsOut(BaseModel):
    values: dict[str, Any]
    overridden: list[str]
    llm_api_key: dict[str, Any]
    read_only: dict[str, Any]


class LlmTestOut(BaseModel):
    ok: bool
    message: str
    latency_ms: int | None
    model: str


class EvaluationRequest(BaseModel):
    ks: list[int] = Field(default=[1, 3, 5], min_length=1, max_length=5)

    @field_validator("ks")
    @classmethod
    def _range(cls, value: list[int]) -> list[int]:
        if any(k < 1 or k > 20 for k in value):
            raise ValueError("each k must be between 1 and 20")
        return value
