# Backend for "Ask the Eagle" — FastAPI, deployable on Render (or any Docker host).
FROM python:3.11-slim

# ffmpeg covers any server-side audio handling on the voice path.
RUN apt-get update && apt-get install -y --no-install-recommends \
        ffmpeg \
    && rm -rf /var/lib/apt/lists/*

# Run as a non-root user.
RUN useradd -m -u 1000 user
USER user
ENV HOME=/home/user \
    PATH=/home/user/.local/bin:$PATH \
    PYTHONUNBUFFERED=1

WORKDIR /home/user/app

# Install deps first so this layer caches between code changes.
# No torch needed now — embeddings run on Pinecone's hosted model.
COPY --chown=user requirements.txt .
RUN pip install --no-cache-dir --upgrade pip \
 && pip install --no-cache-dir -r requirements.txt

# Copy the rest of the backend (main.py, keywords.py, pinecone_embedding.py, ...).
COPY --chown=user . .

# Render provides $PORT; default to 7860 for local/other hosts.
# Shell form so ${PORT} expands at runtime.
CMD uvicorn main:app --host 0.0.0.0 --port ${PORT:-7860}
