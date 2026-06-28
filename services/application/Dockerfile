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

EXPOSE 8000

CMD ["uvicorn", "services.application.app.main:app", "--host", "0.0.0.0", "--port", "8000"]
