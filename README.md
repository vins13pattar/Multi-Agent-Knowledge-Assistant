# Multi-Agent Knowledge Assistant

A secure, enterprise-grade AI platform that helps employees retrieve organizational knowledge, analyze documents, execute approved business operations, and complete multi-step tasks using natural-language conversations.

## Architecture

This project is built using a modern, multi-agent architecture with the following components:

- **Orchestration**: LangGraph (Multi-agent workflow with state management, checkpointed HITL breakpoints)
- **Backend**: FastAPI (REST API, authentication, routing, SSE chat streaming)
- **Frontend**: Streamlit (Chat interface + admin dashboard: approval queue, document status, audit log)
- **Vector Database**: ChromaDB (RAG and semantic search)
- **Relational Database**: PostgreSQL (users, conversations, messages, approvals, audit logs, tool executions, prompt versions)
- **Caching/State**: Redis (reserved for rate limiting / intermediate state)
- **Observability**: LangSmith (tracing, auto-enabled via the `LANGCHAIN_TRACING_V2` env var)

**Deployment**: the whole stack (Postgres, Redis, ChromaDB, API, UI) ships as a **single Docker image**, managed by `supervisord`, so it can be deployed on one EC2 instance with one `docker run`. See [Deployment](#deployment-single-container-on-a-single-ec2-instance) below.

## Features

- **Multi-Agent Orchestration**: LLM-powered Supervisor (intent classification + tool-call extraction), Retrieval (query rewriting), Analysis (multi-source synthesis), Verification (citation/hallucination checking), Safety (risk classification), and Response agents, all backed by versioned YAML prompts in `src/prompts/`.
- **Retrieval-Augmented Generation (RAG)**: Ingests PDF, Markdown, and TXT files, chunks them using `RecursiveCharacterTextSplitter`, and stores embeddings in ChromaDB.
- **Human-in-the-Loop (HITL)**: The safety agent classifies tool-call risk. Anything above "low" risk pauses the LangGraph run at a real checkpoint (`interrupt_before=["tool_execution"]`); an admin's approve/reject decision in `/api/v1/approvals` re-invokes the graph from that exact checkpoint to resume or short-circuit execution.
- **Native Tools + Registry**: `src/tools/registry.py` exposes a schema/risk-aware tool registry with two native tools (`create_support_ticket`, `search_knowledge_base`), executed through a resilient `ToolExecutor` (circuit breaker + exponential backoff w/ jitter).
- **Streaming Chat**: `/api/v1/chat/stream` is real Server-Sent Events — emits per-node progress, then a final `done` (or `approval_pending`) event.
- **Provider Failover**: `FailoverLLMProvider` tries OpenAI first, automatically falling back to Anthropic on error/timeout (configurable via `PRIMARY_LLM_PROVIDER` / `FALLBACK_LLM_PROVIDER`).
- **Role-Based Access Control (RBAC)**: JWT-based auth distinguishing `admin` and `employee` roles, backed by real Postgres-stored users (bcrypt password hashes).
- **Conversation Persistence**: Conversations and messages are persisted per user in Postgres; the graph's LangGraph thread id is stored on the conversation for HITL resume.
- **Audit Logging**: Every login, approval decision, etc. is recorded to the `audit_logs` table, viewable in the admin dashboard.

## Prerequisites

- Docker
- OpenAI API key (and optionally an Anthropic API key for failover)

## Deployment: single container on a single EC2 instance

The production image (`docker/Dockerfile`) bundles everything — Postgres, Redis, ChromaDB, the FastAPI app, and Streamlit — into one container, started and supervised by `supervisord` (`docker/supervisord.conf`). Data lives in two named volumes so it survives container restarts/upgrades.

**On the EC2 instance** (Amazon Linux / Ubuntu with Docker installed):

```bash
git clone <this-repo> && cd "Multi Agent Knowledge Assistant - Enterprise"
cp .env.example .env
# edit .env: set OPENAI_API_KEY (and ANTHROPIC_API_KEY for failover), JWT_SECRET, etc.

docker compose up --build -d
# or, without compose:
docker build -t knowledge-assistant -f docker/Dockerfile .
docker run -d --name knowledge_assistant \
  -p 8000:8000 -p 8501:8501 \
  --env-file .env \
  -v knowledge_assistant_postgres:/var/lib/postgresql \
  -v knowledge_assistant_chroma:/data/chroma \
  --restart unless-stopped \
  knowledge-assistant
```

Open the EC2 instance's security group to inbound TCP `8000` (API) and `8501` (Streamlit UI) from wherever your users are (put a reverse proxy / ALB with TLS in front of these in front of a real deployment). Postgres, Redis, and ChromaDB are only reachable inside the container (`localhost`) — never exposed.

- **Streamlit UI**: `http://<ec2-host>:8501`
- **FastAPI Swagger Docs**: `http://<ec2-host>:8000/docs`

On first boot the container initializes the Postgres cluster, creates the `knowledge_db` database, runs `alembic upgrade head`, and seeds the default admin/employee users — no manual DB setup needed.

To upgrade: `git pull`, then `docker compose up --build -d` (volumes are preserved, migrations run automatically on the next boot).

## Local development (multi-container, hot-reload)

For day-to-day development, a separate multi-container compose file keeps each service isolated with live code-mounting and `--reload`:

```bash
cp .env.example .env
docker compose -f docker-compose.dev.yml up --build
```

This starts `api`, `streamlit`, `postgres`, `redis`, and `chromadb` as five containers with `.:/app` mounted for hot-reload — better suited to local iteration than the single-container production image.

## Project Structure

```
├── apps/
│   ├── api/          # FastAPI backend service
│   └── streamlit/    # Streamlit frontend (chat + admin dashboard)
├── docker/           # Single-container Dockerfile, supervisord config, startup scripts
├── src/
│   ├── auth/         # JWT and RBAC handling
│   ├── graph/         # LangGraph nodes, state, and builder (LLM-powered agents)
│   ├── hitl/          # LLM-backed safety/risk classifier
│   ├── prompts/        # Versioned YAML prompt templates, one dir per agent
│   ├── providers/      # LLM provider abstractions + OpenAI/Anthropic + failover
│   ├── rag/            # Document loaders, chunking, embeddings, ChromaDB
│   └── tools/           # Tool registry, native tools, executor, circuit breaker, retry
├── docker-compose.yml      # Single-container production/EC2 deployment
├── docker-compose.dev.yml  # Multi-container local dev with hot-reload
└── requirements.txt
```

## Running Locally Without Docker

1. Create a Python virtual environment: `python3 -m venv venv`
2. Activate it: `source venv/bin/activate`
3. Install dependencies: `pip install -r requirements.txt`
4. Point `DATABASE_URL` / `CHROMA_HOST` / `CHROMA_PORT` / `REDIS_URL` at running Postgres/Chroma/Redis instances (e.g. via `docker compose -f docker-compose.dev.yml up postgres redis chromadb`).
5. Run migrations and seed: `alembic upgrade head && python scripts/seed.py`
6. Run the API: `uvicorn apps.api.main:app --reload`
7. Run the UI: `streamlit run apps/streamlit/app.py`
