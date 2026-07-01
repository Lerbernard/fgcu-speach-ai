# Backend for "Ask the Eagle" — FastAPI on Hugging Face Spaces (Docker SDK).
# Put this file at the ROOT of your backend folder, next to main.py.
FROM python:3.11-slim

# ffmpeg covers any server-side audio handling on the voice path.
RUN apt-get update && apt-get install -y --no-install-recommends \
        ffmpeg \
    && rm -rf /var/lib/apt/lists/*

# Hugging Face Spaces runs containers as a non-root user (uid 1000).
RUN useradd -m -u 1000 user
USER user
ENV HOME=/home/user \
    PATH=/home/user/.local/bin:$PATH \
    HF_HOME=/home/user/.cache/huggingface \
    PYTHONUNBUFFERED=1

WORKDIR /home/user/app

# Install deps first so this layer caches between code changes.
COPY --chown=user requirements.txt .
# CPU-only PyTorch wheel keeps the image small and the build fast (no CUDA).
RUN pip install --no-cache-dir --upgrade pip \
 && pip install --no-cache-dir torch --index-url https://download.pytorch.org/whl/cpu \
 && pip install --no-cache-dir -r requirements.txt

# Copy the rest of the backend (main.py, keywords.py, academic_calendar.py, etc.).
COPY --chown=user . .

# Spaces routes traffic to port 7860.
EXPOSE 7860
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "7860"]
