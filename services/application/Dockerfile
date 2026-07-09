# syntax=docker/dockerfile:1
FROM python:3.12-slim

WORKDIR /app

# Copy the dependency manifest and install first, before any source, so source
# edits do not invalidate the (slow) install layer. Only a requirements change
# busts this cache.
COPY services/application/requirements.txt ./services/application/requirements.txt
RUN pip install --no-cache-dir -r services/application/requirements.txt

# Application source (and shared service packages) after dependencies.
COPY services/ ./services/

# The index-sync worker entrypoint (b-6) lives in scripts/ and shares this image
# with the application; the compose worker service runs it with a different
# command. Copied after services/ so a deps change still caches the install layer.
COPY scripts/ ./scripts/

EXPOSE 8000

CMD ["uvicorn", "services.application.app.main:app", "--host", "0.0.0.0", "--port", "8000"]
