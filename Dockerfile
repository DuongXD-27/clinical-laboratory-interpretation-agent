# ---- Stage 1: Build ----
FROM python:3.11-slim AS builder

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir --user -r requirements.txt

# ---- Stage 2: Production ----
FROM python:3.11-slim

WORKDIR /app

# Security: run as non-root user — tạo TRƯỚC khi copy để chown đúng luôn,
# copy vào /home/appuser/.local thay vì /root/.local (mặc định 700, user
# khác không đọc được -> từng gây "uvicorn: Permission denied" lúc deploy).
RUN useradd -m appuser
COPY --from=builder --chown=appuser:appuser /root/.local /home/appuser/.local
ENV PATH=/home/appuser/.local/bin:$PATH

# Copy application code (chown ngay lúc copy, không cần chown -R riêng)
COPY --chown=appuser:appuser . .

RUN mkdir -p /app/data && chown -R appuser:appuser /app/data

USER appuser

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=10s --retries=3 \
    CMD python -c "import os, urllib.request; urllib.request.urlopen(f'http://localhost:{os.environ.get(\"PORT\", 8000)}/health')" || exit 1

# JSON exec form invokes the shell explicitly so runtime PORT expansion remains
# available while Uvicorn still receives signals as PID 1 through `exec`.
# Railway containers are ephemeral and data/chroma is intentionally not in Git.
# Build the small approved corpus on boot when production RAG is enabled, then
# start serving only after the collection exists.
CMD ["sh", "-c", "if [ \"${RAG_ENABLED:-false}\" = \"true\" ]; then python -m src.scripts.ingest_kb; fi && exec uvicorn src.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
