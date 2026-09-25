# One image, two roles: the API (default command) and the Streamlit UI
# (docker-compose overrides the command). CPU-only.
FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    HF_HOME=/app/.cache/huggingface

WORKDIR /app

# Install the CPU build of PyTorch first; the default wheel pulls in ~2 GB of CUDA libraries.
RUN pip install --index-url https://download.pytorch.org/whl/cpu torch

COPY requirements.txt .
RUN pip install -r requirements.txt

# Bake the default embedding model into the image so containers start without a download.
ARG EMBEDDING_MODEL=sentence-transformers/all-MiniLM-L6-v2
RUN python -c "from sentence_transformers import SentenceTransformer; SentenceTransformer('${EMBEDDING_MODEL}')"

COPY app ./app
COPY frontend ./frontend
COPY evaluation ./evaluation
COPY main.py .
COPY .streamlit ./.streamlit
COPY data/classifier/sample_training.csv data/classifier/README.md ./data/classifier/

# Run as an unprivileged user.
RUN useradd --create-home docmind && mkdir -p /app/data && chown -R docmind /app
USER docmind

EXPOSE 8000 8501
CMD ["uvicorn", "app.api:app", "--host", "0.0.0.0", "--port", "8000"]
