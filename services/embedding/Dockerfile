# syntax=docker/dockerfile:1
FROM python:3.12-slim

WORKDIR /app

# Install dependencies before copying source so service edits keep the
# dependency layer cacheable. sentence-transformers pulls torch, so this layer
# is large; keeping it ahead of the source copy avoids re-downloading on edits.
COPY services/embedding/requirements.txt ./services/embedding/requirements.txt
RUN pip install --no-cache-dir -r services/embedding/requirements.txt

# Embedding source and shared package namespace.
COPY services/ ./services/

EXPOSE 8002

# The real model (dragonkue/BGE-m3-ko) is downloaded/loaded at startup; mount a
# HuggingFace cache volume in compose so it is not refetched every restart.
CMD ["uvicorn", "services.embedding.app.main:app", "--host", "0.0.0.0", "--port", "8002"]
