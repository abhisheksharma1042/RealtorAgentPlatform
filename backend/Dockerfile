# syntax=docker/dockerfile:1
# Build context must be the REPO ROOT so the image keeps the repo-root package
# layout: /app/backend/... — that way `uvicorn backend.main:app` and
# `python -m backend.ingestion.cli` both work exactly as they do in dev.
#   docker build -f backend/Dockerfile .

FROM python:3.11-slim
WORKDIR /app

# Install from the pinned lockfile (uv pip compile output) so a cold rebuild
# weeks later resolves the exact same dependency versions as today.
COPY backend/requirements.lock backend/requirements.lock
RUN pip install --no-cache-dir -r backend/requirements.lock

COPY backend/ backend/

RUN useradd --create-home appuser
USER appuser

EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health', timeout=4)" || exit 1

CMD ["uvicorn", "backend.main:app", "--host", "0.0.0.0", "--port", "8000"]
