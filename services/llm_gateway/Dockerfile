# syntax=docker/dockerfile:1
FROM python:3.12-slim

WORKDIR /app

# Install dependencies before copying source so application edits keep the
# dependency layer cacheable.
COPY services/llm_gateway/requirements.txt ./services/llm_gateway/requirements.txt
RUN pip install --no-cache-dir -r services/llm_gateway/requirements.txt

# Gateway source and shared package namespace.
COPY services/ ./services/

EXPOSE 8001

CMD ["uvicorn", "services.llm_gateway.app.main:app", "--host", "0.0.0.0", "--port", "8001"]
