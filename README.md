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

**Deployment**: a single `docker-compose.yml` runs the API, UI, Postgres, Redis, and ChromaDB as five containers — the same file works for local development and for a real deployment. See [Running with Docker](#running-with-docker) below.

## Features

- **Multi-Agent Orchestration**: LLM-powered Supervisor (intent classification + tool-call extraction), Retrieval (query rewriting), Analysis (multi-source synthesis), Verification (citation/hallucination checking), Safety (risk classification), and Response agents, all backed by versioned YAML prompts in `src/prompts/`.
- **Retrieval-Augmented Generation (RAG)**: Ingests PDF, Markdown, and TXT files, chunks them using `RecursiveCharacterTextSplitter`, and stores embeddings in ChromaDB.
- **Human-in-the-Loop (HITL)**: The safety agent classifies tool-call risk. Anything above "low" risk pauses the LangGraph run at a real checkpoint (`interrupt_before=["tool_execution"]`); an admin's approve/reject decision in `/api/v1/approvals` re-invokes the graph from that exact checkpoint to resume or short-circuit execution.
- **Native Tools + Registry**: `src/tools/registry.py` exposes a schema/risk-aware tool registry with two native tools (`create_support_ticket`, `search_knowledge_base`), executed through `execute_tool()` for resilience (per-tool circuit breaker + exponential backoff w/ jitter).
- **Streaming Chat**: `/api/v1/chat/stream` is real Server-Sent Events — emits per-node progress, then a final `done` (or `approval_pending`) event.
- **Provider Failover**: `FailoverLLMProvider` tries OpenAI first, automatically falling back to Anthropic on error/timeout (configurable via `PRIMARY_LLM_PROVIDER` / `FALLBACK_LLM_PROVIDER`).
- **Role-Based Access Control (RBAC)**: JWT-based auth distinguishing `admin` and `employee` roles, backed by real Postgres-stored users (bcrypt password hashes).
- **Conversation Persistence**: Conversations and messages are persisted per user in Postgres; the graph's LangGraph thread id is stored on the conversation for HITL resume.
- **Audit Logging**: Every login, approval decision, etc. is recorded to the `audit_logs` table, viewable in the admin dashboard.
- **RAG Evaluation**: Two complementary layers, both surfaced in the admin dashboard's "RAG Evals" tab (`src/rag/eval.py`, `apps/api/eval_runner.py`):
  - *Online metrics* — every `knowledge_query` chat turn is scored inline (retrieval count, groundedness/faithfulness status, citation count, per-node latency) and written to `rag_eval_metrics`, at no extra LLM-call cost.
  - *Offline evaluation* — an admin-triggered batch run (`POST /api/v1/evals/run`, or `python scripts/run_rag_eval.py`) scores a golden question set (`src/rag/eval.py`, backed by `sample_docs/`) for retrieval hit-rate/MRR plus LLM-judged faithfulness and answer relevancy, persisted to `rag_eval_runs` / `rag_eval_run_results`.

## Prerequisites

- Docker
- OpenAI API key (and optionally an Anthropic API key for failover)

## Running with Docker

One `docker-compose.yml` starts five containers — `api`, `streamlit`, `postgres`, `redis`, `chromadb` — and works the same way locally or on a server:

```bash
cp .env.example .env
# edit .env: set OPENAI_API_KEY (and ANTHROPIC_API_KEY for failover), JWT_SECRET, etc.

docker compose up --build
```

- **Streamlit UI**: `http://localhost:8501`
- **FastAPI Swagger Docs**: `http://localhost:8000/docs`

On first boot, the `api` container runs `alembic upgrade head` and `python scripts/seed.py` before starting — no manual DB setup needed. Code is mounted live (`.:/app`) and the API runs with `--reload`, so this is convenient for iterating locally. Data persists in the `postgres_data` / `chroma_data` named volumes across restarts.

**Deploying this to a server** (e.g. a single EC2 instance):

Open [`docs/deployment-guide.html`](docs/deployment-guide.html) in a browser for the full field guide (Mermaid architecture diagrams, copy-paste commands). The default path is Docker Compose on one EC2 instance; the same file covers Azure/GCP VMs and a scalable architecture on AWS, Azure, and GCP.

- Only open inbound `8000` (API) and `8501` (Streamlit) in your security group — Postgres, ChromaDB, and Redis aren't published to the host at all (they're reachable only over the internal compose network), and no reverse proxy / TLS is set up, so put one in front of these for anything beyond a demo.
- Set `ENVIRONMENT=production` and a real `POSTGRES_PASSWORD` in `.env` — this makes `scripts/seed.py` refuse to create the demo admin/employee accounts (create your first admin via `POST /api/v1/users` instead) and stops the Postgres container from using its default password.
- For a hardened build, drop the `volumes: .:/app` mounts and the `--reload` flag in `docker-compose.yml`'s `api` service (they exist for local hot-reload only) and bake the code into the image instead.

To upgrade: `git pull`, then `docker compose up --build -d` (volumes are preserved, migrations run automatically on the next boot).

## Trying It Out

`sample_docs/` has six fictional documents (PDF/Markdown/TXT, mixed `shared`/`restricted` access scopes) plus a matching golden question set — see [`sample_docs/README.md`](sample_docs/README.md) for the upload commands and suggested test queries. They're what the offline RAG eval (`src/rag/eval.py`) scores against, and a good way to see ingestion, RBAC-scoped retrieval, and HITL all working without writing your own content first.

## Project Structure

```
├── apps/
│   ├── api/
│   │   ├── main.py         # FastAPI backend service (routes, SSE chat stream)
│   │   └── eval_runner.py  # Background-task runner for offline RAG eval
│   └── streamlit/    # Streamlit frontend (chat + admin dashboard)
├── docker/           # Dockerfile.api, Dockerfile.streamlit
├── src/
│   ├── auth/         # JWT and RBAC handling
│   ├── graph/         # LangGraph nodes, state, and builder (LLM-powered agents)
│   ├── hitl/          # LLM-backed safety/risk classifier
│   ├── prompts/        # Versioned YAML prompt templates, one dir per agent
│   ├── providers/      # LLM provider abstractions + OpenAI/Anthropic + failover
│   ├── rag/            # Document loaders, chunking, embeddings, ChromaDB, eval.py (golden-set scoring)
│   └── tools/           # Tool registry, native tools, executor, circuit breaker, retry
├── scripts/
│   ├── seed.py             # Seeds demo admin/employee accounts
│   └── run_rag_eval.py     # CLI to trigger an offline RAG eval run outside the dashboard
├── sample_docs/       # Fictional documents + golden question set for exercising RAG end-to-end
├── docker-compose.yml      # api, streamlit, postgres, redis, chromadb containers
└── requirements.txt
```

## Running Locally Without Docker

1. Create a Python virtual environment: `python3 -m venv venv`
2. Activate it: `source venv/bin/activate`
3. Install dependencies: `pip install -r requirements.txt`
4. Point `DATABASE_URL` / `CHROMA_HOST` / `CHROMA_PORT` / `REDIS_URL` at running Postgres/Chroma/Redis instances (e.g. via `docker compose up postgres redis chromadb`).
5. Run migrations and seed: `alembic upgrade head && python scripts/seed.py`
6. Run the API: `uvicorn apps.api.main:app --reload`
7. Run the UI: `streamlit run apps/streamlit/app.py`
