"""FastAPI application.

Routes are thin: they validate input (via Pydantic models), call
``DocMindService`` and translate domain exceptions into HTTP status codes.
"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, File, HTTPException, Request, UploadFile, status
from fastapi.responses import JSONResponse

from app import __version__
from app.config import get_settings
from app.ingestion import IngestionError
from app.llm import LLMError, LLMNotConfiguredError
from app.models import (
    AskRequest,
    AskResponse,
    DocumentOut,
    HealthResponse,
    ProcessItem,
    ProcessRequest,
    ProcessResponse,
    SearchHit,
    SearchRequest,
    SearchResponse,
    SourceOut,
    UploadItem,
    UploadResponse,
)
from app.service import DocMindService, DocumentNotFoundError
from app.utils import sanitize_filename, setup_logging
from app.vector_store import VectorStoreError

logger = logging.getLogger(__name__)

MAX_FILES_PER_UPLOAD = 20


def create_app(service: DocMindService | None = None) -> FastAPI:
    """Build the app. Tests pass a pre-built service; normally it is created at startup."""

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        if service is not None:
            app.state.service = service
        else:
            settings = get_settings()
            setup_logging(settings.log_level)
            # Loads the embedding model and the FAISS index once for the process.
            app.state.service = DocMindService(settings)
        yield

    app = FastAPI(
        title="DocMind API",
        version=__version__,
        description="Upload PDFs, search them semantically and ask grounded questions.",
        lifespan=lifespan,
    )

    def get_service(request: Request) -> DocMindService:
        return request.app.state.service

    @app.exception_handler(VectorStoreError)
    async def _vector_store_error(_: Request, exc: VectorStoreError):
        logger.error("Vector store error: %s", exc)
        return JSONResponse(status_code=500, content={"detail": str(exc)})

    @app.exception_handler(Exception)
    async def _unhandled(_: Request, exc: Exception):
        logger.exception("Unhandled API error")
        return JSONResponse(status_code=500, content={"detail": "Internal server error"})

    # ---------------------------------------------------------------- health
    @app.get("/health", response_model=HealthResponse)
    def health(svc: DocMindService = Depends(get_service)) -> HealthResponse:
        s = svc.settings
        return HealthResponse(
            version=__version__,
            embedding_model=svc.embedder.model_name,
            llm_provider=s.llm_provider,
            llm_model=s.llm_model,
            llm_configured=svc.llm_available,
            documents=len(svc.registry),
            indexed_chunks=svc.store.size,
        )

    # ------------------------------------------------------------- documents
    @app.post("/documents/upload", response_model=UploadResponse, status_code=status.HTTP_201_CREATED)
    async def upload_documents(
        files: list[UploadFile] = File(...), svc: DocMindService = Depends(get_service)
    ) -> UploadResponse:
        if len(files) > MAX_FILES_PER_UPLOAD:
            raise HTTPException(status_code=400, detail=f"At most {MAX_FILES_PER_UPLOAD} files per request")

        items: list[UploadItem] = []
        limit = svc.settings.max_upload_bytes
        for upload in files:
            name = sanitize_filename(upload.filename or "")
            # Read at most limit+1 bytes so an oversized file is rejected without
            # loading all of it into memory.
            data = await upload.read(limit + 1)
            try:
                record, duplicate = svc.upload(name, data)
            except IngestionError as exc:
                items.append(UploadItem(filename=name, status="rejected", detail=str(exc)))
                continue
            items.append(
                UploadItem(
                    filename=name,
                    status="duplicate" if duplicate else "uploaded",
                    doc_id=record.doc_id,
                    detail=f"Already uploaded as '{record.filename}'" if duplicate else None,
                )
            )

        if items and all(item.status == "rejected" for item in items):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="; ".join(item.detail or item.filename for item in items),
            )
        return UploadResponse(items=items)

    @app.post("/documents/process", response_model=ProcessResponse)
    def process_documents(
        body: ProcessRequest | None = None, svc: DocMindService = Depends(get_service)
    ) -> ProcessResponse:
        body = body or ProcessRequest()
        try:
            results = svc.process(body.doc_ids, force=body.force)
        except DocumentNotFoundError as exc:
            raise HTTPException(status_code=404, detail=f"Unknown document id: {exc}") from exc
        items = [
            ProcessItem(
                doc_id=r.doc_id,
                filename=r.filename,
                status=r.status,
                chunk_count=r.chunk_count,
                skipped=skipped,
                detail=r.error or ("; ".join(r.warnings) if r.warnings else None),
            )
            for r, skipped in results
        ]
        return ProcessResponse(items=items, indexed_chunks=svc.store.size)

    @app.get("/documents", response_model=list[DocumentOut])
    def list_documents(svc: DocMindService = Depends(get_service)) -> list[DocumentOut]:
        return [DocumentOut.from_record(r) for r in svc.list_documents()]

    @app.get("/documents/{doc_id}", response_model=DocumentOut)
    def get_document(doc_id: str, svc: DocMindService = Depends(get_service)) -> DocumentOut:
        try:
            return DocumentOut.from_record(svc.get_document(doc_id))
        except DocumentNotFoundError as exc:
            raise HTTPException(status_code=404, detail="Document not found") from exc

    @app.delete("/documents/{doc_id}", status_code=status.HTTP_204_NO_CONTENT)
    def delete_document(doc_id: str, svc: DocMindService = Depends(get_service)) -> None:
        try:
            svc.delete_document(doc_id)
        except DocumentNotFoundError as exc:
            raise HTTPException(status_code=404, detail="Document not found") from exc

    # ---------------------------------------------------------------- search
    @app.post("/search", response_model=SearchResponse)
    def search(body: SearchRequest, svc: DocMindService = Depends(get_service)) -> SearchResponse:
        top_k = body.top_k or svc.settings.top_k
        results = svc.search(body.query, top_k, body.doc_ids)
        return SearchResponse(query=body.query, top_k=top_k, results=[SearchHit.from_result(r) for r in results])

    @app.post("/ask", response_model=AskResponse)
    def ask(body: AskRequest, svc: DocMindService = Depends(get_service)) -> AskResponse:
        try:
            result = svc.ask(body.question, body.top_k, body.doc_ids)
        except LLMNotConfiguredError as exc:
            raise HTTPException(status_code=503, detail=str(exc)) from exc
        except LLMError as exc:
            logger.error("LLM call failed: %s", exc)
            raise HTTPException(status_code=502, detail=f"LLM request failed: {exc}") from exc

        sources = [
            SourceOut(**SearchHit.from_result(r).model_dump(), source_number=i + 1, cited=(i + 1) in result.cited_numbers)
            for i, r in enumerate(result.sources)
        ]
        return AskResponse(
            question=result.question,
            answer=result.answer,
            answered_from_documents=result.answered_from_documents,
            sources=sources,
            invalid_citations=result.invalid_citations,
            model=result.model,
        )

    return app


app = create_app()
