# Escuta+ — backend (FastAPI) + PWA servida em /app. Contexto de build: raiz do repositório.
FROM python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1 \
    ESCUTA_DIR_FRONTEND=/srv/frontend
# Sem --proxy-headers: o uvicorn reescreveria request.client a partir de X-Forwarded-For,
# que o cliente pode forjar. O IP real é resolvido em escuta.api.app.ip_cliente.
WORKDIR /srv/backend

COPY backend/pyproject.toml ./
COPY backend/escuta ./escuta
RUN pip install . && useradd --system --uid 10001 escuta && mkdir -p /data && chown escuta /data

COPY backend/alembic.ini ./
COPY frontend /srv/frontend

USER escuta
EXPOSE 8080
# Migrações antes de servir: o schema em produção só muda por Alembic.
CMD ["sh", "-c", "alembic upgrade head && exec uvicorn escuta.api.app:app --host 0.0.0.0 --port 8080"]
