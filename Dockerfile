# DocMind: one image that serves the API and the built React UI on one port.
# Stage 1 builds the UI with Node; stage 2 is the Python runtime (CPU-only, no PyTorch).

# ---------------------------------------------------------------- web build
FROM node:22-slim AS web
WORKDIR /web
COPY web/package.json web/package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY web/ ./
RUN npm run build

# ---------------------------------------------------------------- runtime
FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    HF_HOME=/app/.cache/huggingface

WORKDIR /app

# No PyTorch: the embedding model runs on ONNX Runtime (CPU).
COPY requirements.txt .
RUN pip install -r requirements.txt

# Bake the embedding model's ONNX export and tokenizer (~90 MB) into the image,
# then run offline so containers never download at startup. To use another
# sentence-transformers model that ships onnx/model.onnx, rebuild with
# --build-arg EMBEDDING_MODEL=<name> (the runtime EMBEDDING_MODEL defaults to it).
ARG EMBEDDING_MODEL=sentence-transformers/all-MiniLM-L6-v2
ENV EMBEDDING_MODEL=${EMBEDDING_MODEL} \
    HF_HUB_DISABLE_TELEMETRY=1
RUN python -c "import sys; from huggingface_hub import hf_hub_download; [hf_hub_download(sys.argv[1], f) for f in ('onnx/model.onnx', 'tokenizer.json', 'sentence_bert_config.json', '1_Pooling/config.json')]" "${EMBEDDING_MODEL}"
ENV HF_HUB_OFFLINE=1

COPY app ./app
COPY evaluation ./evaluation
COPY main.py .
COPY data/classifier/sample_training.csv data/classifier/README.md ./data/classifier/
COPY --from=web /web/dist ./web/dist

# Run as an unprivileged user.
RUN useradd --create-home --uid 1000 docmind && mkdir -p /app/data && chown -R docmind /app
USER docmind

# Production profile: refuses to start without DOCMIND_API_TOKEN and hides
# /api/docs (set API_DOCS=true to show them). All persistent state lives in
# DATA_DIR; mount a volume there or it is lost when the container is replaced.
ENV APP_ENV=production \
    DATA_DIR=/app/data \
    HOST=0.0.0.0 \
    PORT=8000

EXPOSE 8000
HEALTHCHECK --interval=15s --timeout=5s --start-period=90s --retries=5 \
    CMD python -c "import os, urllib.request; urllib.request.urlopen('http://127.0.0.1:%s/api/health' % os.environ.get('PORT', '8000'), timeout=4)" || exit 1

# Listens on $PORT (most cloud platforms set it). Python is PID 1 (exec form),
# so SIGTERM reaches uvicorn and it shuts down gracefully. Exactly one worker:
# the FAISS index and write locks live in process memory.
CMD ["python", "main.py", "api"]
