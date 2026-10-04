"""FastAPI application.

Routes are thin: they validate input (via Pydantic models), call
``DocMindService`` and translate domain exceptions into HTTP status codes.

All API routes live under ``/api``. If the React UI has been built
(``web/dist``), the same process serves it at ``/`` so the browser talks to the
API on the same origin (no CORS needed).
"""

from __future__ import annotations

import logging
import secrets
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import APIRouter, Depends, FastAPI, File, HTTPException, Request, Response, UploadFile, status
from fastapi.concurrency import run_in_threadpool
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from app import __version__
from app.config import Settings, get_settings
from app.ingestion import IngestionError
from app.llm import LLMError, LLMNotConfiguredError
from app.models import (
    AskRequest,
    AskResponse,
    DocumentChunkOut,
    DocumentOut,
    EvaluationRequest,
    HealthResponse,
    LimitsOut,
    LlmTestOut,
    ProcessItem,
    ProcessRequest,
    ProcessResponse,
    SearchHit,
    SearchRequest,
    SearchResponse,
    SettingsOut,
    SettingsUpdate,
    SourceOut,
    UploadItem,
    UploadResponse,
)
from app.service import DocMindService, DocumentNotFoundError
from app.utils import StorageError, sanitize_filename, setup_logging

logger = logging.getLogger(__name__)

API_PREFIX = "/api"
MAX_FILES_PER_UPLOAD = 20
UPLOAD_PATH = f"{API_PREFIX}/documents/upload"

# Applied to the UI's index.html. Scripts only from our own origin; inline
# styles are allowed because the animation library sets style attributes.
CONTENT_SECURITY_POLICY = (
    "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; "
    "img-src 'self' data: blob:; font-src 'self' data:; connect-src 'self'; worker-src 'self' blob:; "
    "object-src 'none'; base-uri 'self'; form-action 'self'; frame-ancestors 'none'"
)
SECURITY_HEADERS = [
    (b"x-content-type-options", b"nosniff"),
    (b"referrer-policy", b"no-referrer"),
    (b"x-frame-options", b"DENY"),
    (b"cross-origin-opener-policy", b"same-origin"),
    (b"permissions-policy", b"camera=(), microphone=(), geolocation=(), payment=()"),
    # Browsers ignore HSTS on plain-HTTP responses, so this is harmless locally
    # and takes effect once the app is served over HTTPS.
    (b"strict-transport-security", b"max-age=31536000"),
]


class UploadSizeLimitMiddleware:
    """Reject oversized upload requests before their body is read.

    Without this, Starlette would receive and spool the whole multipart body
    to a temporary file before the route could check any size. The server's
    HTTP parser enforces Content-Length framing, so a request cannot send more
    bytes than it declares; uploads without a Content-Length are refused.
    """

    def __init__(self, app, max_bytes):
        self.app = app
        self.max_bytes = max_bytes  # int, or a callable returning the current limit

    async def __call__(self, scope, receive, send):
        if scope["type"] == "http" and scope["method"] == "POST" and scope["path"] == UPLOAD_PATH:
            headers = dict(scope["headers"])
            length = headers.get(b"content-length")
            if length is None or not length.isdigit():
                return await _send_json(send, 411, "Uploads must include a Content-Length header")
            max_bytes = self.max_bytes() if callable(self.max_bytes) else self.max_bytes
            if int(length) > max_bytes:
                limit_mb = max_bytes // (1024 * 1024)
                return await _send_json(send, 413, f"Upload request exceeds {limit_mb} MB (MAX_REQUEST_MB)")
        await self.app(scope, receive, send)


class SecurityHeadersMiddleware:
    """Add conservative security headers to every HTTP response."""

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)

        async def send_with_headers(message):
            if message["type"] == "http.response.start":
                existing = {name.lower() for name, _ in message.get("headers", [])}
                message.setdefault("headers", [])
                message["headers"] = list(message["headers"]) + [h for h in SECURITY_HEADERS if h[0] not in existing]
            await send(message)

        await self.app(scope, receive, send_with_headers)


async def _send_json(send, status_code: int, detail: str) -> None:
    response = JSONResponse(status_code=status_code, content={"detail": detail})
    await response({"type": "http"}, None, send)


def mount_web_ui(app: FastAPI, dist: Path) -> bool:
    """Serve the built single-page app from ``dist`` if it exists.

    Unknown non-API paths return index.html so client-side routes such as
    /documents/abc work on refresh. API paths never fall through to the UI.
    """
    index = dist / "index.html"
    if not index.is_file():
        logger.info("Web UI not built (%s missing); serving the API only", index)
        return False
    root = dist.resolve()
    if (dist / "assets").is_dir():
        app.mount("/assets", StaticFiles(directory=dist / "assets"), name="assets")

    @app.get("/{path:path}", include_in_schema=False)
    def spa(path: str):
        if path == "api" or path.startswith("api/"):
            raise HTTPException(status_code=404, detail="Not found")
        candidate = (root / path).resolve()
        # Static files from dist (favicon etc.), but never anything outside it.
        if path and candidate.is_file() and root in candidate.parents:
            return FileResponse(candidate)
        return FileResponse(
            index,
            headers={"Cache-Control": "no-cache", "Content-Security-Policy": CONTENT_SECURITY_POLICY},
        )

    logger.info("Serving web UI from %s", dist)
    return True


def create_app(service: DocMindService | None = None, settings: Settings | None = None) -> FastAPI:
    """Build the app. Tests pass a pre-built service; normally it is created at startup."""
    settings = settings or (service.settings if service is not None else get_settings())

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        app.state.startup_error = None
        if service is not None:
            app.state.service = service
        else:
            setup_logging(settings.log_level)
            try:
                # Loads the embedding model and the FAISS index once for the process.
                app.state.service = DocMindService(settings)
            except StorageError as exc:
                # Start anyway so every request can explain the problem (503)
                # instead of the server dying with a traceback.
                logger.error("DocMind could not load its stored data: %s", exc)
                app.state.service, app.state.startup_error = None, str(exc)
        if not settings.api_token:
            logger.warning("DOCMIND_API_TOKEN is not set: anyone who can reach this API can use it.")
        logger.info(
            "DocMind API ready: env=%s llm_provider=%s llm_configured=%s cors_origins=%d auth=%s",
            settings.app_env,
            settings.llm_provider,
            settings.llm_configured,
            len(settings.cors_allow_origins),
            "token" if settings.api_token else "none",
        )
        yield
        if service is None and app.state.service is not None:
            app.state.service.shutdown()

    app = FastAPI(
        title="DocMind API",
        version=__version__,
        description="Upload PDFs, search them semantically and ask grounded questions.",
        lifespan=lifespan,
        docs_url=f"{API_PREFIX}/docs" if settings.api_docs else None,
        redoc_url=None,
        openapi_url=f"{API_PREFIX}/openapi.json" if settings.api_docs else None,
    )
    def current_settings() -> Settings:
        svc = getattr(app.state, "service", None)
        return svc.settings if svc is not None else settings

    app.add_middleware(UploadSizeLimitMiddleware, max_bytes=lambda: current_settings().max_request_bytes)
    app.add_middleware(SecurityHeadersMiddleware)
    if settings.cors_allow_origins:
        # Only needed when a browser app on another origin calls the API directly.
        # The bundled UI is served from the same origin and needs no CORS.
        app.add_middleware(
            CORSMiddleware,
            allow_origins=settings.cors_allow_origins,
            allow_methods=["GET", "POST", "PATCH", "DELETE"],
            allow_headers=["Content-Type", "X-API-Key", "Authorization"],
            allow_credentials=False,
        )

    def require_token(request: Request) -> None:
        if not settings.api_token:
            return
        supplied = request.headers.get("x-api-key", "")
        auth = request.headers.get("authorization", "")
        if not supplied and auth.lower().startswith("bearer "):
            supplied = auth[7:].strip()
        if not (supplied and secrets.compare_digest(supplied.encode(), settings.api_token.encode())):
            raise HTTPException(
                status_code=401, detail="Missing or invalid API token", headers={"WWW-Authenticate": "Bearer"}
            )

    def get_service(request: Request) -> DocMindService:
        if request.app.state.service is None:
            raise HTTPException(status_code=503, detail=f"Search index unavailable: {request.app.state.startup_error}")
        return request.app.state.service

    @app.exception_handler(StorageError)
    async def _storage_error(_: Request, exc: StorageError):
        logger.error("Storage error: %s", exc)
        return JSONResponse(status_code=500, content={"detail": str(exc)})

    @app.exception_handler(Exception)
    async def _unhandled(_: Request, exc: Exception):
        logger.exception("Unhandled API error")
        return JSONResponse(status_code=500, content={"detail": "Internal server error"})

    public = APIRouter(prefix=API_PREFIX)
    api = APIRouter(prefix=API_PREFIX, dependencies=[Depends(require_token)])

    # ---------------------------------------------------------------- health
    @public.get("/health", response_model=HealthResponse)
    def health(svc: DocMindService = Depends(get_service)) -> HealthResponse:
        # Deliberately unauthenticated so load balancers / Docker can probe it,
        # and so the UI can tell whether it needs to ask for a token.
        # Returns 503 (via get_service) if stored data could not be loaded.
        s = svc.settings
        return HealthResponse(
            version=__version__,
            embedding_model=svc.embedder.model_name,
            llm_provider=s.llm_provider,
            llm_model=s.llm_model,
            llm_configured=svc.llm_available,
            auth_required=bool(s.api_token),
            documents=len(svc.registry),
            indexed_chunks=svc.store.size,
            limits=LimitsOut(
                max_upload_mb=s.max_upload_mb,
                max_request_mb=s.max_request_mb,
                max_pages=s.max_pages,
                max_files_per_upload=MAX_FILES_PER_UPLOAD,
                default_top_k=s.top_k,
                max_top_k=s.max_top_k,
            ),
        )

    # ------------------------------------------------------------- documents
    @api.post("/documents/upload", response_model=UploadResponse, status_code=status.HTTP_201_CREATED)
    async def upload_documents(
        files: list[UploadFile] = File(...), svc: DocMindService = Depends(get_service)
    ) -> UploadResponse:
        if len(files) > MAX_FILES_PER_UPLOAD:
            raise HTTPException(status_code=400, detail=f"At most {MAX_FILES_PER_UPLOAD} files per request")

        items: list[UploadItem] = []
        limit = svc.settings.max_upload_bytes
        for upload in files:
            name = sanitize_filename(upload.filename or "")
            # Read at most limit+1 bytes into memory; anything larger is rejected.
            data = await upload.read(limit + 1)
            try:
                # Hashing and the disk write are blocking work; keep them off the event loop.
                record, duplicate = await run_in_threadpool(svc.upload, name, data)
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

    @api.post("/documents/process", response_model=ProcessResponse)
    def process_documents(
        response: Response, body: ProcessRequest | None = None, svc: DocMindService = Depends(get_service)
    ) -> ProcessResponse:
        body = body or ProcessRequest()
        try:
            if body.background:
                results = svc.enqueue(body.doc_ids, force=body.force)
                response.status_code = 202
            else:
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

    @api.get("/documents", response_model=list[DocumentOut])
    def list_documents(svc: DocMindService = Depends(get_service)) -> list[DocumentOut]:
        return [DocumentOut.from_record(r) for r in svc.list_documents()]

    @api.get("/documents/{doc_id}", response_model=DocumentOut)
    def get_document(doc_id: str, svc: DocMindService = Depends(get_service)) -> DocumentOut:
        try:
            return DocumentOut.from_record(svc.get_document(doc_id))
        except DocumentNotFoundError as exc:
            raise HTTPException(status_code=404, detail="Document not found") from exc

    @api.get("/documents/{doc_id}/chunks", response_model=list[DocumentChunkOut])
    def get_document_chunks(doc_id: str, svc: DocMindService = Depends(get_service)) -> list[DocumentChunkOut]:
        try:
            chunks = svc.get_document_chunks(doc_id)
        except DocumentNotFoundError as exc:
            raise HTTPException(status_code=404, detail="Document not found") from exc
        return [
            DocumentChunkOut(chunk_id=c.chunk_id, page_number=c.page_number, chunk_index=c.chunk_index, text=c.text)
            for c in chunks
        ]

    @api.delete("/documents/{doc_id}", status_code=status.HTTP_204_NO_CONTENT)
    def delete_document(doc_id: str, svc: DocMindService = Depends(get_service)) -> None:
        try:
            svc.delete_document(doc_id)
        except DocumentNotFoundError as exc:
            raise HTTPException(status_code=404, detail="Document not found") from exc

    # ---------------------------------------------------------------- search
    @api.post("/search", response_model=SearchResponse)
    def search(body: SearchRequest, svc: DocMindService = Depends(get_service)) -> SearchResponse:
        top_k = body.top_k or svc.settings.top_k
        results = svc.search(body.query, top_k, body.doc_ids)
        return SearchResponse(query=body.query, top_k=top_k, results=[SearchHit.from_result(r) for r in results])

    @api.post("/ask", response_model=AskResponse)
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
            grounding=result.grounding,
            sources=sources,
            invalid_citations=result.invalid_citations,
            unverified_answer=result.unverified_answer,
            model=result.model,
        )

    # -------------------------------------------------------------- settings
    @api.get("/settings", response_model=SettingsOut)
    def get_settings_view(svc: DocMindService = Depends(get_service)) -> SettingsOut:
        return SettingsOut(**svc.settings_view())

    @api.patch("/settings", response_model=SettingsOut)
    def update_settings(body: SettingsUpdate, svc: DocMindService = Depends(get_service)) -> SettingsOut:
        changes = body.model_dump(exclude_unset=True)
        if not changes:
            raise HTTPException(status_code=422, detail="No settings to change")
        try:
            return SettingsOut(**svc.update_settings(changes))
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc

    @api.delete("/settings/llm-api-key", response_model=SettingsOut)
    def remove_saved_llm_key(svc: DocMindService = Depends(get_service)) -> SettingsOut:
        """Forget a key saved from the UI; the environment's LLM_API_KEY (if any) applies again."""
        return SettingsOut(**svc.remove_overrides({"llm_api_key"}))

    @api.post("/settings/reset", response_model=SettingsOut)
    def reset_settings(svc: DocMindService = Depends(get_service)) -> SettingsOut:
        return SettingsOut(**svc.reset_settings())

    @api.post("/settings/test-llm", response_model=LlmTestOut)
    def test_llm(svc: DocMindService = Depends(get_service)) -> LlmTestOut:
        return LlmTestOut(**svc.test_llm())

    # ------------------------------------------------------------ evaluation
    @api.post("/evaluation/retrieval")
    def evaluate_retrieval(body: EvaluationRequest | None = None, svc: DocMindService = Depends(get_service)) -> dict:
        """Measure retrieval on the bundled demo dataset with the current settings (temporary index)."""
        from evaluation.evaluate import EvaluationError, run_retrieval_evaluation

        try:
            return run_retrieval_evaluation(svc.settings, (body or EvaluationRequest()).ks, embedder=svc.embedder)
        except (EvaluationError, OSError) as exc:
            logger.error("Evaluation failed: %s", exc)
            raise HTTPException(status_code=503, detail="The evaluation dataset is not available on this server.") from exc

    app.include_router(public)
    app.include_router(api)
    # Registered last: the UI's catch-all route must not shadow API routes.
    mount_web_ui(app, settings.web_dist_dir)
    return app


app = create_app()
