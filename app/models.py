"""Data models.

Two kinds of models live here:

* Domain objects (plain dataclasses) passed between pipeline stages.
* API schemas (Pydantic) that define the FastAPI request/response contract.

Keeping them side by side makes it easy to see how internal objects map onto
what the API exposes.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Literal

from pydantic import BaseModel, Field, field_validator

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

    @property
    def is_empty(self) -> bool:
        return not self.text.strip()


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


DocumentStatus = Literal["uploaded", "processed", "failed"]


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


class HealthResponse(BaseModel):
    status: Literal["ok"] = "ok"
    version: str
    embedding_model: str
    llm_provider: str
    llm_model: str
    llm_configured: bool
    documents: int
    indexed_chunks: int


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
    answered_from_documents: bool
    sources: list[SourceOut]
    invalid_citations: list[int]
    model: str | None


class ErrorResponse(BaseModel):
    detail: str
