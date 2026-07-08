# zread MCP server — self-hosted, company-wide deployment image
#
# All data comes straight from GitHub; no external SaaS, no account, no token.
#
# Build:
#   docker build -t zread-mcp .
#
# Run the shared MCP server (HTTP mode, endpoint: http://<host>:8708/mcp):
#   docker run -d --name zread-mcp -p 8708:8708 zread-mcp
#   # optional: -e GITHUB_TOKEN=... for higher API limits / private repos
#
# The full CLI is available in the same image:
#   docker exec zread-mcp zread ls golang/go -p
#   docker run --rm zread-mcp top -p

FROM python:3.12-slim

# The image is built from a source checkout without .git, so tell
# setuptools-scm which version to stamp (override via --build-arg).
ARG ZREAD_VERSION=0.0.0
ENV SETUPTOOLS_SCM_PRETEND_VERSION=${ZREAD_VERSION}

# Corporate networks with TLS-inspecting proxies: pass the proxy's CA
# bundle so pip (build) and zread (runtime) trust it:
#   docker build --build-arg EXTRA_CA_CERT="$(cat /path/to/ca.pem)" ...
ARG EXTRA_CA_CERT=""
RUN if [ -n "$EXTRA_CA_CERT" ]; then \
        printf '%s\n' "$EXTRA_CA_CERT" \
            > /usr/local/share/ca-certificates/corporate-ca.crt \
        && update-ca-certificates; \
    fi
# Point Python HTTP stacks (pip, httpx, requests) at the system CA store
# so an injected corporate CA is honored everywhere.
ENV SSL_CERT_FILE=/etc/ssl/certs/ca-certificates.crt \
    REQUESTS_CA_BUNDLE=/etc/ssl/certs/ca-certificates.crt \
    PIP_CERT=/etc/ssl/certs/ca-certificates.crt

WORKDIR /app

COPY pyproject.toml README.md LICENSE ./
COPY zread ./zread

RUN pip install --no-cache-dir . && rm -rf /root/.cache

# Run as a non-root user
RUN useradd --create-home --uid 1000 zread
USER zread

# Configuration (set at run time):
#   GITHUB_TOKEN     optional, raises GitHub API limits / enables private repos
#   ZREAD_LANG       zh / en (default: en for a shared server)
ENV ZREAD_LANG=en

EXPOSE 8708

# Health: prefer the /healthz endpoint (a real HTTP response from the MCP
# app, including version and runtime metrics); fall back to a TCP connect
# if the route is unavailable.
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 CMD \
    python -c "exec(\"import urllib.request, socket\ntry:\n    urllib.request.urlopen('http://127.0.0.1:8708/healthz', timeout=4)\nexcept Exception:\n    socket.create_connection(('127.0.0.1', 8708), timeout=4)\")"

ENTRYPOINT ["zread"]
CMD ["mcp", "http", "0.0.0.0:8708"]
