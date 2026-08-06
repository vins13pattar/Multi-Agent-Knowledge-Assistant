# Single-container image for the Multi-Agent Knowledge Assistant.
# Bundles PostgreSQL, Redis, ChromaDB, the FastAPI backend, and the Streamlit
# UI into one image, orchestrated by supervisord — intended for deployment on
# a single EC2 instance via `docker run`.
FROM python:3.12-slim

ENV DEBIAN_FRONTEND=noninteractive \
    PYTHONUNBUFFERED=1 \
    DATABASE_URL=postgresql://postgres:postgres@localhost:5432/knowledge_db \
    CHROMA_HOST=localhost \
    CHROMA_PORT=8001 \
    REDIS_URL=redis://localhost:6379/0 \
    API_URL=http://localhost:8000

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
        build-essential python3-dev curl \
        postgresql postgresql-contrib redis-server supervisor \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

RUN mkdir -p /var/log/supervisor /data/chroma /var/lib/postgresql \
    && chown -R postgres:postgres /var/lib/postgresql /data/chroma \
    && chmod +x docker/start-postgres.sh docker/start-api.sh docker/start-streamlit.sh

COPY docker/supervisord.conf /etc/supervisor/conf.d/supervisord.conf

VOLUME ["/var/lib/postgresql", "/data/chroma"]
EXPOSE 8000 8501

CMD ["/usr/bin/supervisord", "-n", "-c", "/etc/supervisor/conf.d/supervisord.conf"]
