FROM node:22-alpine AS frontend
WORKDIR /build/frontend
COPY frontend/package*.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build

FROM python:3.12-slim AS application
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 LOOP_DATABASE_PATH=/app/data/loop.sqlite3
WORKDIR /app
COPY requirements*.txt ./
RUN pip install --no-cache-dir -r requirements-api.txt
COPY backend/ backend/
COPY core/ core/
COPY nodes/ nodes/
COPY profiles/ profiles/
COPY prompts/ prompts/
COPY utils/ utils/
COPY state.py ./
COPY --from=frontend /build/frontend/dist frontend/dist/
RUN useradd --create-home --uid 10001 loop && mkdir -p /app/data && chown -R loop:loop /app
USER loop
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/api/health',timeout=3)"
# SQLite and the in-process worker intentionally run in a single API process.
CMD ["uvicorn", "backend.main:app", "--host", "0.0.0.0", "--port", "8000"]
