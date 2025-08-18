# ==========================================================
#  backend/Dockerfile
#  VERSI FINAL: Multi-stage optimized untuk development dan production
# ==========================================================

# ---------- Base (Dasar Python) ----------
FROM python:3.11-slim AS base
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=off \
    PIP_DISABLE_PIP_VERSION_CHECK=on \
    PIP_DEFAULT_TIMEOUT=100 \
    PATH="/opt/venv/bin:$PATH"
WORKDIR /app

# ---------- Builder (Meng-compile dependensi Python) ----------
FROM base AS builder
RUN apt-get update -y && \
    apt-get install -y --no-install-recommends \
        build-essential libpq-dev libffi-dev \
        libglib2.0-dev libcairo2-dev libpango1.0-dev libgdk-pixbuf-xlib-2.0-dev \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN python -m venv /opt/venv && \
    pip install --upgrade pip && \
    pip install -r requirements.txt

# ---------- Runtime Base (Berisi semua paket OS yang dibutuhkan) ----------
FROM base AS runtime-base
RUN apt-get update -y && \
    apt-get install -y --no-install-recommends \
        gosu \
        libpq5 libffi8 \
        libglib2.0-0 libcairo2 libpango-1.0-0 libgdk-pixbuf-2.0-0 \
        libfontconfig1 libfreetype6 libharfbuzz0b libpangoft2-1.0-0 \
        curl iputils-ping net-tools dnsutils iproute2 procps \
    && rm -rf /var/lib/apt/lists/*

# ---------- Development stage ----------
FROM runtime-base AS development
ENV FLASK_ENV=development FLASK_DEBUG=1

COPY --from=builder /opt/venv /opt/venv
COPY . .

# Setup entrypoint and create user
COPY entrypoint.sh /usr/local/bin/entrypoint.sh
RUN chmod +x /usr/local/bin/entrypoint.sh && \
    useradd -m -u 1001 appuser && \
    mkdir -p /app/.cache/fontconfig /app/logs && \
    chown -R appuser:appuser /app

ENTRYPOINT ["entrypoint.sh"]
EXPOSE 5010

# Development health check
HEALTHCHECK --interval=30s --timeout=5s --retries=3 \
    CMD curl -f http://127.0.0.1:5010/api/ping || exit 1

CMD ["flask", "run", "--host=0.0.0.0", "--port=5010"]

# ---------- Production stage ----------
FROM runtime-base AS production
ENV FLASK_ENV=production

COPY --from=builder /opt/venv /opt/venv
COPY . .
# Install additional production dependencies
RUN pip install --no-warn-script-location gunicorn

# Setup entrypoint and create user
COPY entrypoint.sh /usr/local/bin/entrypoint.sh
RUN chmod +x /usr/local/bin/entrypoint.sh && \
    useradd -m -u 1001 appuser && \
    chown -R appuser:appuser /app

ENTRYPOINT ["entrypoint.sh"]
EXPOSE 5010

# Production health check
HEALTHCHECK --interval=30s --timeout=5s --retries=3 \
    CMD curl -f http://127.0.0.1:5010/healthz || exit 1
 
CMD ["gunicorn", "--bind", "0.0.0.0:5010", "--workers=2", "--log-level=info", "run:app"]