# zread-ai-backend — self-hosted RAG over GitHub docs
#
# Build:
#   docker build -t zread-ai ./backend
#
# Run (HTTP mode, endpoint: http://<host>:8709):
#   docker run -d --name zread-ai -p 8709:8709 \
#     -e GITHUB_TOKEN=... \
#     -e ZREAD_LLM_API_KEY=... \
#     -v zread-ai-data:/app/data \
#     zread-ai
#
# Health:
#   curl http://<host>:8709/healthz

FROM python:3.12-slim

# Corporate TLS-inspecting proxies: pass the proxy's CA bundle.
ARG EXTRA_CA_CERT=""
RUN if [ -n "$EXTRA_CA_CERT" ]; then \
        printf '%s\n' "$EXTRA_CA_CERT" \
            > /usr/local/share/ca-certificates/corporate-ca.crt \
        && update-ca-certificates; \
    fi
ENV SSL_CERT_FILE=/etc/ssl/certs/ca-certificates.crt \
    REQUESTS_CA_BUNDLE=/etc/ssl/certs/ca-certificates.crt \
    PIP_CERT=/etc/ssl/certs/ca-certificates.crt

WORKDIR /app

COPY pyproject.toml ./
COPY app ./app

RUN pip install --no-cache-dir . && rm -rf /root/.cache

# Run as a non-root user
RUN useradd --create-home --uid 1000 zread

# Persistent storage for the SQLite DB + embeddings.
# Created as root (before USER switch) so the non-root user can't be denied,
# then chowned so the zread user can write the DB at runtime.
RUN mkdir -p /app/data && chown -R zread:zread /app/data
VOLUME ["/app/data"]

USER zread

# Configuration (set at run time):
#   GITHUB_TOKEN         required for private repos / higher API limits
#   ZREAD_LLM_BASE_URL   OpenAI-compatible endpoint (default: OpenAI)
#   ZREAD_LLM_API_KEY    LLM provider API key
#   ZREAD_LLM_MODEL      chat model (default: gpt-4o-mini)
#   ZREAD_EMBED_MODEL    embedding model (default: text-embedding-3-small)
#   ZREAD_EMBED_DIM      embedding dimensions (must match model; default: 1536)
EXPOSE 8709

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 CMD \
    python -c "exec(\"import urllib.request\nurllib.request.urlopen('http://127.0.0.1:8709/healthz', timeout=4)\")"

ENTRYPOINT ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8709"]
