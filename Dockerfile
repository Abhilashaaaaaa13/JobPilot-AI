# ── Stage 1: build the React frontend ──────────────────────────────────────
FROM node:20-slim AS client-build
WORKDIR /client
COPY client/package*.json ./
RUN npm ci
COPY client/ ./
RUN npm run build

# ── Stage 2: Python backend, serving the built frontend ────────────────────
FROM python:3.11-slim AS runtime
WORKDIR /app

# System deps for Playwright's Chromium (used by the Betalist scraper) and PDF/OCR libs.
RUN apt-get update && apt-get install -y --no-install-recommends \
    wget gnupg ca-certificates \
    libnss3 libnspr4 libatk1.0-0 libatk-bridge2.0-0 libcups2 libdrm2 \
    libxkbcommon0 libxcomposite1 libxdamage1 libxfixes3 libxrandr2 \
    libgbm1 libpango-1.0-0 libcairo2 libasound2 \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt
# Best-effort — the Betalist scraper degrades gracefully if this ever fails.
RUN python -m playwright install chromium || true

COPY backend/ ./backend/
COPY run_scheduler.py ./
COPY --from=client-build /client/dist ./client/dist

RUN mkdir -p data uploads

EXPOSE 8000
CMD ["sh", "-c", "uvicorn backend.api.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
