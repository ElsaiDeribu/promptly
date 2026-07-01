# Promptly

Promptly is a full-stack application for experimenting with LLMs. It features a Django REST API backend and a React SPA frontend, supporting JWT authentication, local LLM chat via Ollama, per-user semantic memory, async S3/MinIO document ingestion via Celery, and a multimodal RAG pipeline over PDFs using Qdrant, MinIO, and OpenAI.

The RAG stack combines:

- **Docling** PDF parsing with hierarchical chunking, table extraction, and inline image capture
- **LangGraph** ingestion (preprocess → index) and a **ReAct agent** for grounded Q&A
- **Hybrid vector retrieval** in Qdrant (OpenAI dense embeddings + local BM25 sparse vectors); optional cross-encoder reranking
- **Per-user long-term memory** in PostgreSQL, retrieved semantically and writable by the agent
- **Async document ingestion** — presigned MinIO/S3 uploads, Celery workers on a Redis broker queue
- **LLM-driven eval system** — dynamically generates per-document test cases after ingestion and scores RAG answers, with **LangSmith** tracing and offline LLM-as-judge evals

Goal: Build a self-improving multi-agent system that continuously enhances retrieval, reasoning, and response quality through evaluation-driven feedback loops.

---

## Tech stack

| Layer                  | Stack                                                                                                                                                                                                                                                                         |
| ---------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **Backend**            | Python 3.12, Django 5, Django REST Framework, Celery, PostgreSQL, Redis, Uvicorn (ASGI)                                                                                                                                                                                       |
| **LLM / AI**           | Ollama (local chat), OpenAI (RAG ingestion + agent + embeddings), LangChain, LangGraph, LangSmith                                                                                                                                                                             |
| **Retrieval**          | Qdrant (hybrid dense + sparse), fastembed (BM25), sentence-transformers (cross-encoder reranking)                                                                                                                                                                             |
| **Document parsing**   | Docling (`DocumentConverter`, `HybridChunker`, OpenAI token-aware splits)                                                                                                                                                                                                     |
| **Storage**            | Qdrant (vector DB), MinIO (S3-compatible object storage for PDFs and extracted images)                                                                                                                                                                                        |
| **Frontend**           | React 19, TypeScript, Vite 6, Tailwind CSS 4, react-markdown                                                                                                                                                                                                                  |
| **UI components**      | shadcn/ui (Radix UI primitives), Lucide icons, Framer Motion                                                                                                                                                                                                                  |
| **Forms / validation** | React Hook Form, Zod                                                                                                                                                                                                                                                          |
| **HTTP / routing**     | Axios, React Router v7, Server-Sent Events (RAG streaming)                                                                                                                                                                                                                    |
| **Containerisation**   | Docker, Docker Compose — local dev stack (`docker-compose.local.yml`), production stack with Traefik (`docker-compose.production.yml`), docs stack (`docker-compose.docs.yml`); custom Dockerfiles under `backend/compose/`                                                   |
| **DevOps / infra**     | Traefik (reverse proxy, TLS/ACME in production), Flower (Celery monitoring), Mailpit (dev email capture), Redis (Celery broker + result backend), `just` task runner, AWS CLI sidecar (Postgres backups in production), env-file layout (`.envs/.local`, `.envs/.production`) |
| **Quality / tooling**  | pre-commit, Ruff, mypy, pytest (backend); ESLint, Prettier (frontend); drf-spectacular (OpenAPI / Swagger)                                                                                                                                                                    |

---

## Features & architecture

### End-to-end flow

```text
Upload PDF ──► presigned PUT to MinIO ──► complete-upload ──► Redis queue ──► Celery worker
                                                                                      │
                                                                                      ▼
                                                                            LangGraph ingestion graph
                                                                            (preprocess → index)
                                                                                      │
                         ┌────────────────────────────────────────────────────────────┼────────────────────┐
                         ▼                                                            ▼                    ▼
                    Qdrant index                                                 text/table chunks   images in MinIO
                    (raw + image summaries)                                      (with provenance)   (linked by image_key)

User query ──► memory search (Postgres) ──► LangGraph ReAct agent (gpt-4o-mini)
                                                    │
                                                    ▼ vector_rag_tool
                              Qdrant hybrid search (k×4 candidates)
                                                    │
                                                    ▼ cross-encoder rerank
                              top-k chunks + presigned image URLs ──► SSE answer
```

### Multimodal RAG pipeline

PDF ingestion runs asynchronously in Celery (`process_document`) after the client confirms upload. A LangGraph `StateGraph` in `backend/app/llm/services/multimodal_rag/rag_pipeline.py` executes two nodes:

| Node           | What it does                                                                                      |
| -------------- | ------------------------------------------------------------------------------------------------- |
| **preprocess** | Parses the PDF with Docling (`process_pdf`) and produces typed chunks (text, table, image)        |
| **index**      | Vision-describes images, stores JPEGs in MinIO, embeds all chunks into Qdrant                     |

**Vision summarisation** (images only)

| Content | Model    | Concurrency |
| ------- | -------- | ----------- |
| Images  | `gpt-4o` | 2           |

Text and table chunks are indexed **as-is** from Docling — no LLM summarisation step. Only figure images get a vision description before embedding.

**Indexing pattern**

- Each chunk gets a UUID `source_id` and provenance metadata (`page_no`, `headings`, `bbox`, etc.).
- **Text and tables** — raw chunk text is embedded directly in Qdrant.
- **Images** — `gpt-4o` produces a concise description; the summary is embedded with `image_key` metadata pointing to a JPEG in MinIO at `images/{uuid}.jpg`. At query time, presigned URLs are generated so the agent can reference images.

**Document lifecycle** (`Document` model): `pending` → `uploaded` → `processing` → `processed` / `failed`. After processing, optional eval generation runs independently (`eval_generation_status`: `none` → `processing` → `completed` / `failed`). See [Document storage & background processing](#document-storage--background-processing) for how uploads reach MinIO and how Celery picks up the work.

### Document storage & background processing

PDFs land in **MinIO** (S3-compatible object storage) via **presigned URLs**, and RAG ingestion runs **asynchronously on a Celery worker** backed by a **Redis message queue**. Django orchestrates both steps but never handles the raw file bytes.

**Presigned URL upload**

Uploads bypass the API entirely. `S3Wrapper` generates short-lived presigned PUT URLs signed against `S3_PUBLIC_ENDPOINT_URL` so the browser can reach MinIO directly. Django only creates the `Document` record, issues the URL, and later confirms the object landed in the bucket — the PDF never passes through a request body.

| Step | Who               | What happens                                                                                                                   |
| ---- | ----------------- | ------------------------------------------------------------------------------------------------------------------------------ |
| 1    | Frontend → Django | `POST /api/llm/documents/create-upload-url` — creates a `Document` (`pending`), ensures the S3 bucket exists, returns a presigned PUT URL + `document_id` |
| 2    | Browser → MinIO   | `PUT` the PDF to the presigned URL (no JWT; just `Content-Type`)                                                               |
| 3    | Frontend → Django | `POST /api/llm/documents/{id}/complete-upload` — verifies the object exists, sets status to `uploaded`, enqueues ingestion     |
| 4    | Frontend → Django | Polls `GET /api/llm/documents/{id}` with backoff (30s → 60s → 120s, up to ~1 hour) until `processed` or `failed`               |

Container-to-container traffic uses `S3_ENDPOINT_URL` (`http://minio:9000`). Presigned links use the public endpoint (`http://localhost:9200` locally) because the browser cannot resolve Docker-internal hostnames.

**What lives in MinIO**

| Object prefix                       | When it's written              | Purpose                                                                 |
| ----------------------------------- | ------------------------------ | ----------------------------------------------------------------------- |
| `uploads/{upload_token}/{filename}` | Client PUT via presigned URL   | Original PDF, keyed by a collision-free token on the `Document` record  |
| `images/{uuid}.jpg`                 | Celery worker during ingestion | Extracted figure JPEGs, referenced from Qdrant via `image_key` metadata |

Metadata (filename, status, S3 key, errors) lives in **PostgreSQL** on the `Document` model. MinIO holds the blobs; Postgres tracks processing state.

**Celery + Redis ingestion queue**

When `complete-upload` succeeds, Django calls `process_document.delay(document_id)` and returns **`202 Accepted`** immediately. The task is pushed onto a **Redis broker** (`REDIS_URL`, default `redis://redis:6379/0`) and picked up by the `celeryworker` container. Redis also serves as the Celery result backend.

```text
complete-upload ──► process_document.delay() ──► Redis queue ──► celeryworker
                                                                      │
                                                                      ▼
                                                            download PDF from MinIO
                                                            LangGraph RAG ingestion
                                                            update Document status

generate-eval-examples ──► generate_eval_examples.delay() ──► Redis queue ──► celeryworker
                                                                                    │
                                                                                    ▼
                                                                          sample passages from Qdrant
                                                                          generate Q/A pairs (gpt-4o-mini)
                                                                          store EvalExample rows in Postgres
```

The worker (`backend/app/llm/tasks.py`) runs the full ingestion pipeline:

1. Sets the document to `processing`.
2. Downloads the PDF from MinIO into a temporary file.
3. Invokes the LangGraph graph (preprocess → index into Qdrant + MinIO).
4. Marks the document `processed`, or `failed` with an error message.

PDF parsing and vision summarisation are slow, so this task overrides Celery's default timeouts with **25 min soft / 30 min hard** limits and allows up to **3 retries**. The temp file is always removed in a `finally` block. Monitor the queue via **Flower** at http://localhost:5555.

A second Celery task, **`generate_eval_examples`**, runs the eval system's test-case generation step for a processed document — see [Evaluation system](#evaluation-system) for the full two-stage flow.

This split — presigned upload to storage, ingestion on a Redis-backed worker — keeps the API responsive and lets users queue multiple PDFs without blocking the chat UI.

### PDF chunking strategy

Chunking is handled by [Docling](https://github.com/docling-project/docling) in `backend/app/llm/utils/pdf_processor.py`:

| Component     | Value                                         | Purpose                                            |
| ------------- | --------------------------------------------- | -------------------------------------------------- |
| **Parser**    | `DocumentConverter` + `PdfPipelineOptions`    | Structure-aware PDF conversion                     |
| **Chunker**   | `HybridChunker`                               | Hierarchical chunking with token-aware split/merge |
| **Tokenizer** | `OpenAITokenizer` (`cl100k_base`, 512 tokens) | Aligns chunk sizes with OpenAI embedding models    |
| **Pictures**  | `generate_picture_images=True`                | Extract figure images for multimodal summarisation |

Each chunk is a `ProcessedChunk` with provenance metadata stored in Qdrant:

| Metadata field            | Purpose                                                    |
| ------------------------- | ---------------------------------------------------------- |
| `page_no`                 | Page citation                                              |
| `headings`                | Section breadcrumb                                         |
| `captions`                | Table/figure captions                                      |
| `element_label`           | Element type (`paragraph`, `table`, `picture`, …)          |
| `doc_item_ref`            | Stable reference back to the Docling document node         |
| `bbox`                    | Bounding box JSON for future PDF highlighting              |
| `image_key` / `image_url` | MinIO object key at index time; presigned URL at retrieval |

### Hybrid vector retrieval & reranking

Retrieval lives in `backend/app/llm/utils/vector_db.py` and is exposed to the agent via `vector_rag_tool` (`backend/app/llm/tools/vector_rag.py`).

| Component             | Technology                             | Details                                                                |
| --------------------- | -------------------------------------- | ---------------------------------------------------------------------- |
| **Vector DB**         | Qdrant                                 | Collection `multi_modal_rag`; dense (1536-dim cosine) + sparse vectors |
| **Dense embeddings**  | `OpenAIEmbeddings`                     | Default OpenAI embedding model                                         |
| **Sparse embeddings** | `FastEmbedSparse` (`Qdrant/bm25`)      | Local BM25 via [fastembed](https://github.com/qdrant/fastembed)        |
| **Retrieval mode**    | `RetrievalMode.HYBRID`                 | Combines dense semantic search with sparse keyword matching            |
| **Reranker**          | `cross-encoder/ms-marco-MiniLM-L-6-v2` | sentence-transformers cross-encoder; cached per model                  |
| **Rerank default**    | `enable_reranking=False`               | Hybrid search always on; reranking is opt-in via constructor           |
| **Fetch strategy**    | `rerank_fetch_multiplier=4`            | When reranking is enabled: fetches `k × 4` candidates, reranks to top `k` |

Pass `VectorDBWrapper(enable_reranking=True)` to enable cross-encoder reranking. Retrieved image chunks get presigned MinIO URLs inlined before the agent sees them.

### LangGraph ReAct agent

Query-time orchestration is in `backend/app/llm/agents/rag_agent.py`:

- **Framework:** LangGraph `create_react_agent`
- **Model:** `ChatOpenAI(model="gpt-4o-mini", temperature=0)`
- **Tools:** `vector_rag_tool` (document retrieval), `upsert_memory` (user-scoped, bound per request)
- **Behaviour:** Retrieve from documents first for factual questions; save personal preferences and user facts via the memory tool (not RAG). Reformulate follow-up questions into standalone search queries when needed.

Answers stream back over **Server-Sent Events** (`POST /api/llm/rag/query/stream`) via LangGraph `astream_events(version="v2")`. The frontend sends the last **10** conversation turns per request.

### User memory

Long-term, per-user memory is stored in **PostgreSQL** (`UserMemory` model), not Qdrant. Embeddings are stored as JSON arrays and ranked in Python via cosine similarity (no pgvector extension).

Promptly uses **two memory layers**:

| Layer        | Storage              | Scope                          | How it is written                          |
| ------------ | -------------------- | ------------------------------ | ------------------------------------------ |
| **Short-term** | Client-side chat history | Last **10** conversation turns | Sent with each RAG request from the frontend |
| **Long-term**  | Postgres `UserMemory`    | Persists across sessions       | Agent `upsert_memory` tool only (no REST create/update) |

| Capability              | Implementation                                                                          |
| ----------------------- | --------------------------------------------------------------------------------------- |
| **Storage**             | `content`, optional `context`, OpenAI embedding (JSON) per memory                       |
| **Upsert**              | Agent tool `upsert_memory` — create new or update by `memory_id` (for corrections)      |
| **Pre-query retrieval** | Cosine similarity over all user memories; query built from the last **3** message turns; top **10** injected into the system prompt |
| **REST API**            | `GET /api/llm/memories`, `DELETE /api/llm/memories/{uuid}` — list and delete only     |
| **UI**                  | Memory panel in the multimodal RAG dashboard; refreshes after each chat                 |
| **Admin**               | Inspect memories at http://localhost:8000/admin/ (`UserMemory`)                         |

The agent is instructed to use `vector_rag_tool` for document facts and `upsert_memory` for personal preferences and user-specific information. Relevant long-term memories are injected into the agent system prompt before streaming begins.

### Evaluation system

Promptly closes the loop from ingestion to quality measurement with a **two-stage, LLM-driven eval system** — no hand-authored test fixtures required.

```text
PDF ingested ──► passages sampled from Qdrant ──► LLM generates Q/A test cases
                                                          │
                                                          ▼
                              run_rag_eval: RAG agent answers each question ──► LLM judges score the answer
```

**Stage 1 — generate test cases** (`generate_eval_examples` Celery task, `backend/app/llm/evals/generate_examples.py`)

After a document reaches `processed`, trigger generation from the UI or API. The system:

1. Samples up to **15** deduplicated passages from Qdrant for that document (falls back to re-parsing the PDF from S3 if vectors are missing).
2. For each passage, **`gpt-4o-mini`** writes up to **2** question–answer pairs that are answerable strictly from that passage.
3. Deduplicates questions and stores rows in Postgres as `EvalExample` (`inputs.question`, `inputs.document_id`, `outputs.answer` as reference).
4. Optionally pushes the new examples to LangSmith (`sync_langsmith: true`).

Each regeneration **replaces** prior test cases for that document — eval examples always reflect the current index.

**Stage 2 — score answers (LLM-as-judge)** (`manage.py run_rag_eval`, `backend/app/llm/evals/rag_eval.py`)

For each test case, the eval harness:

1. Invokes the same **`build_rag_agent`** used in production (scoped to `document_id`, no user memory).
2. Collects the agent's answer and the retrieved `vector_rag_tool` context from the message trace.
3. Scores the run with **LLM-as-judge** evaluators (`gpt-4o-mini`, structured 0.0–1.0 grades):

| Evaluator          | What the judge checks                                                                 |
| ------------------ | ------------------------------------------------------------------------------------- |
| `faithfulness`     | Is every factual claim in the answer supported by retrieved context?                  |
| `answer_relevancy` | Does the answer directly address the question? (grounding judged separately)          |

Results upload to LangSmith by default, or print locally with `--local`. See [LangSmith tracing and evals](#langsmith-tracing-and-evals) for CLI flags and the step-by-step workflow.

### Model assignments

| Use case                      | Provider | Model(s)                          |
| ----------------------------- | -------- | --------------------------------- |
| Local chat playground         | Ollama   | Default `llama3` (`OLLAMA_MODEL`) |
| RAG ingestion (images only)   | OpenAI   | `gpt-4o` (vision descriptions)    |
| RAG Q&A agent                 | OpenAI   | `gpt-4o-mini`                     |
| Eval judges + example generation | OpenAI | `gpt-4o-mini`                     |
| Embeddings (vectors + memory) | OpenAI   | Default `OpenAIEmbeddings`        |

Chat-only features work without `OPENAI_API_KEY`; RAG endpoints require it.

---

## Repository layout

```text
promptly/
├── backend/                              # Django API + Docker Compose stack
│   ├── app/                              # Django project root
│   │   ├── authentication/               # JWT auth app (register, login, me)
│   │   │   ├── serializers.py
│   │   │   ├── views.py
│   │   │   └── urls.py
│   │   ├── users/                        # Custom user model + Celery tasks
│   │   │   ├── models.py
│   │   │   ├── manager.py
│   │   │   ├── tasks.py
│   │   │   └── tests/
│   │   └── llm/                          # LLM features (chat + RAG + memory)
│   │       ├── views.py                  # API views: models, chat, RAG SSE, memories, documents
│   │       ├── serializers.py
│   │       ├── urls.py
│   │       ├── models.py                 # Document, UserMemory, EvalExample models
│   │       ├── tasks.py                  # Celery: async PDF processing
│   │       ├── agents/
│   │       │   └── rag_agent.py          # LangGraph ReAct agent (retrieval + memory tools)
│   │       ├── tools/
│   │       │   ├── vector_rag.py         # vector_rag_tool: hybrid search → context JSON
│   │       │   └── memory.py             # upsert_memory tool (user-scoped)
│   │       ├── services/
│   │       │   ├── memory.py             # Memory CRUD + semantic search (Postgres)
│   │       │   └── multimodal_rag/
│   │       │       └── rag_pipeline.py   # LangGraph ingestion (pre-process, summarise, index)
│   │       ├── utils/
│   │       │   ├── pdf_processor.py      # Docling PDF parsing and hybrid chunking
│   │       │   ├── s3.py                 # MinIO/S3 upload + presigned URL helpers
│   │       │   └── vector_db.py          # Qdrant hybrid search + cross-encoder reranking
│   │       ├── evals/
│   │       │   ├── rag_eval.py           # LangSmith evaluators (faithfulness, answer_relevancy)
│   │       │   ├── generate_examples.py  # Eval test-case generation from indexed passages
│   │       │   ├── dataset.py            # Load/replace eval examples; LangSmith sync
│   │       │   └── sample_dataset.json   # Starter static eval examples
│   │       └── management/commands/
│   │           └── run_rag_eval.py       # `manage.py run_rag_eval` entry point
│   ├── config/                           # Django settings (base, local, production)
│   ├── requirements/                     # Pinned deps: base.txt, local.txt, production.txt
│   ├── compose/                          # Dockerfile and entrypoint scripts
│   ├── docker-compose.local.yml          # Full local dev stack
│   ├── docker-compose.production.yml
│   ├── justfile                          # `just` shortcuts for common tasks
│   ├── pyproject.toml                    # Ruff, mypy, pytest config
│   └── .envs/.local/                     # Local secrets (gitignored)
│       ├── .django
│       ├── .postgres
│       └── .rag
│
└── frontend/                             # React SPA (Vite dev server on port 8081)
    ├── src/
    │   ├── auth/                         # JWT auth layer
    │   │   ├── context/auth/             # AuthContext + AuthProvider (token storage)
    │   │   ├── guard/                    # AuthGuard, GuestGuard, RoleBasedGuard
    │   │   └── hooks/                    # useAuthContext hook
    │   ├── pages/                        # Route-level page components
    │   │   ├── auth/                     # login.tsx, register.tsx
    │   │   ├── dashboard/                # dashboard.tsx, llm-chat.tsx, multimodal-rag.tsx
    │   │   ├── playground/               # LLM playground (model/preset/temperature selectors)
    │   │   └── 403.tsx / 404.tsx / 500.tsx
    │   ├── sections/                     # Feature UI sections (compose pages)
    │   │   ├── auth/                     # LoginView, RegisterView
    │   │   ├── dashboard/                # Dashboard overview section
    │   │   └── multimodal-rag/           # RAG chat, document upload, memory panel
    │   ├── components/                   # Shared, reusable components
    │   │   ├── ui/                       # shadcn/ui primitives (button, dialog, tabs …)
    │   │   ├── hook-form/                # FormProvider wrapper
    │   │   ├── form/                     # Custom TextField component
    │   │   └── loading-screen/           # Full-page and splash loading states
    │   ├── routes/                       # React Router v7 route definitions
    │   │   ├── sections/                 # auth.tsx, dashboard.tsx, main.tsx (lazy imports)
    │   │   ├── hooks/                    # useRouter, usePathname, useParams …
    │   │   └── paths.ts                  # Centralised route path constants
    │   ├── hooks/                        # Generic utility hooks
    │   │   └── use-boolean, use-debounce, use-local-storage …
    │   ├── theme/                        # Tailwind/shadcn theme provider + dark-mode toggle
    │   ├── utils/                        # axios instance, formatters, storage helpers
    │   ├── types/                        # Shared TypeScript types
    │   ├── config-global.ts              # App-wide config (API base URL, etc.)
    │   └── main.tsx                      # React entry point
    ├── package.json
    ├── vite.config.ts
    ├── tsconfig.json
    └── components.json                   # shadcn/ui component registry config
```

---

## Prerequisites

| Tool                                                              | Version / notes                                      |
| ----------------------------------------------------------------- | ---------------------------------------------------- |
| [Docker Desktop](https://www.docker.com/products/docker-desktop/) | Required for the backend and all supporting services |
| [Node.js](https://nodejs.org/)                                    | **20+** recommended                                  |
| npm or yarn                                                       | Comes with Node                                      |

Optional:

- [Git](https://git-scm.com/) — clone the repo
- OpenAI API key — required for the **multimodal RAG** pipeline (embeddings, summarisation, and the Q&A agent)
- Enough disk/RAM for Docker images, Ollama models, and the cross-encoder reranker (models are large)

---

## Quick start (local development)

1. Create backend environment files (see [Backend setup](#backend-setup)).
2. Start the backend stack with Docker Compose.
3. Pull at least one Ollama model and create the MinIO bucket.
4. Create `frontend/.env` and start the dev server.
5. Open http://localhost:8081, register or log in, and explore the dashboard.

---

## Backend setup

All backend services run via Docker Compose from the `backend/` directory.

### 1. Create environment files

The backend loads env vars from `backend/.envs/.local/`. These files are **gitignored** — create them locally and do not commit secrets.

#### `backend/.envs/.local/.django`

```env
USE_DOCKER=yes
IPYTHONDIR=/app/.ipython

REDIS_URL=redis://redis:6379/0

CELERY_FLOWER_USER=debug
CELERY_FLOWER_PASSWORD=debug
```

#### `backend/.envs/.local/.postgres`

```env
POSTGRES_HOST=postgres
POSTGRES_PORT=5432
POSTGRES_DB=app
POSTGRES_USER=debug
POSTGRES_PASSWORD=debug
```

`DATABASE_URL` is constructed automatically from these variables inside the container entrypoint.

#### `backend/.envs/.local/.rag`

Required for the multimodal RAG endpoints. Use Docker service hostnames (not `localhost`) so containers can reach each other.

```env
# OpenAI (embeddings + summarisation + RAG agent)
OPENAI_API_KEY=your-openai-api-key

# Optional: LangSmith tracing and evals
LANGSMITH_TRACING=true
LANGSMITH_ENDPOINT=https://api.smith.langchain.com
LANGSMITH_API_KEY=your-langsmith-api-key
LANGSMITH_PROJECT=promptly-rag

# Qdrant (vector store)
QDRANT_HOST=qdrant
QDRANT_PORT=6333

# MinIO / S3 (object storage for PDF uploads and extracted images)
S3_BUCKET_NAME=pdf-images
S3_ENDPOINT_URL=http://minio:9000
# Browser-reachable MinIO URL for presigned upload/download links (required in Docker)
S3_PUBLIC_ENDPOINT_URL=http://localhost:9200
AWS_ACCESS_KEY_ID=minioadmin
AWS_SECRET_ACCESS_KEY=minioadmin
AWS_DEFAULT_REGION=us-east-1

# Ollama (local LLM for chat playground)
OLLAMA_BASE_URL=http://ollama:13000
OLLAMA_MODEL=llama3
```

Chat-only features work without `OPENAI_API_KEY`; RAG endpoints will fail without it.

> **Note:** `S3_PUBLIC_ENDPOINT_URL` must be reachable from the browser. Inside Docker, use `http://localhost:9200` (mapped MinIO API port), not the internal hostname `minio:9000`.

### 2. Start the stack

```bash
cd backend
docker compose -f docker-compose.local.yml up --build
```

First run can take several minutes (image builds, Python wheels, NLTK data, cross-encoder model download). To run detached: add `-d`. To stop: `docker compose -f docker-compose.local.yml down`.

> **Production compose:** `docker-compose.production.yml` includes Django, Postgres, Redis, Celery, Flower, and Traefik. It does **not** include Ollama, MinIO, or Qdrant — the full RAG stack is currently oriented toward local development via `docker-compose.local.yml`.

### 3. Services

| Service          | Container                | Host port                  | Purpose                                               |
| ---------------- | ------------------------ | -------------------------- | ----------------------------------------------------- |
| **django**       | `app_local_django`       | 8000                       | REST API (Uvicorn, auto-migrate on start)             |
| **postgres**     | `app_local_postgres`     | 5432                       | Application database                                  |
| **redis**        | `app_local_redis`        | —                          | Celery broker + result backend (ingestion task queue) |
| **mailpit**      | `app_local_mailpit`      | 8025                       | Dev email UI (SMTP on 1025 inside network)            |
| **ollama**       | `app_local_ollama`       | 13000                      | Local LLM runtime                                     |
| **minio**        | `app_local_minio`        | 9200 (API), 9201 (console) | Object storage                                        |
| **qdrant**       | `app_local_qdrant`       | 6333, 6334                 | Vector database                                       |
| **celeryworker** | `app_local_celeryworker` | —                          | `process_document` + `generate_eval_examples` tasks |
| **celerybeat**   | `app_local_celerybeat`   | —                          | Scheduled tasks                                       |
| **flower**       | `app_local_flower`       | 5555                       | Celery monitoring UI                                  |

### 4. Pull an Ollama model

```bash
docker exec -it app_local_ollama ollama pull llama3
```

The API defaults to `llama3`. Override with `OLLAMA_MODEL` in `.rag`.

### 5. Create the MinIO bucket

RAG stores PDF uploads and extracted images in the bucket defined by `S3_BUCKET_NAME` (default: `pdf-images`). `CreateUploadURLView` calls `ensure_bucket()` on first upload, but creating the bucket manually in the MinIO console is a good safety net for local dev.

1. Open **MinIO Console**: http://localhost:9201
2. Log in: `minioadmin` / `minioadmin`
3. Create a bucket named **`pdf-images`** if it does not already exist.

### 6. Create a Django superuser (optional)

```bash
docker exec -it app_local_django python manage.py createsuperuser
```

Django admin: http://localhost:8000/admin/

Inspect LLM models there: `Document`, `UserMemory`, `EvalExample`.

### 7. API endpoints

| URL                               | Description          |
| --------------------------------- | -------------------- |
| http://localhost:8000/api/docs/   | Swagger UI           |
| http://localhost:8000/api/schema/ | OpenAPI schema       |
| http://localhost:8025             | Mailpit dev email UI |

**Auth**

| Method | Path                 | Description                   |
| ------ | -------------------- | ----------------------------- |
| `POST` | `/api/auth/register` | Create account                |
| `POST` | `/api/auth/login`    | Get JWT tokens                |
| `GET`  | `/api/auth/me`       | Current user (requires token) |

**LLM / RAG**

| Method   | Path                                      | Description                               |
| -------- | ----------------------------------------- | ----------------------------------------- |
| `GET`    | `/api/llm/models`                         | List available Ollama models              |
| `POST`   | `/api/llm/chat`                           | Chat with an Ollama model (non-streaming) |
| `POST`   | `/api/llm/rag/query/stream`               | Multimodal RAG query (SSE token stream)   |
| `GET`    | `/api/llm/memories`                       | List saved user memories                  |
| `DELETE` | `/api/llm/memories/{uuid}`                | Delete a saved memory                     |
| `POST`   | `/api/llm/documents/create-upload-url`              | Get a presigned URL to upload a PDF to S3 |
| `POST`   | `/api/llm/documents/{id}/complete-upload`           | Confirm upload and queue async processing |
| `GET`    | `/api/llm/documents/{id}`                           | Poll processing status (`status`, `eval_generation_status`, `eval_example_count`, …) |
| `POST`   | `/api/llm/documents/{id}/generate-eval-examples`    | Queue eval test-case generation (`202`; body: `{ "sync_langsmith": false }`) |
| `GET`    | `/api/llm/documents/{id}/eval-examples`             | Poll eval generation status; `?include_examples=true` returns Q/A payloads |

CORS is configured for `http://localhost:8081` by default.

### 8. Useful backend commands

```bash
# Run migrations (also runs on container start)
docker exec -it app_local_django python manage.py migrate

# Django shell
docker exec -it app_local_django python manage.py shell

# Run tests
docker exec -it app_local_django pytest

# View logs for one service
docker compose -f docker-compose.local.yml logs -f django

# LangSmith RAG evals (requires indexed PDFs + OPENAI_API_KEY; uses Postgres eval examples by default)
docker exec -it app_local_django python manage.py run_rag_eval

# Restrict evals to one document's test cases
docker exec -it app_local_django python manage.py run_rag_eval --document-id 1 --local

# Run evals locally without uploading to LangSmith
docker exec -it app_local_django python manage.py run_rag_eval --local

# Shorthand via just
just rag-eval
just rag-eval --local
```

---

## Frontend setup

The frontend is a Vite + React SPA. The dev server runs on port **8081** and proxies API requests to the Django backend on port **8000**.

### 1. Install dependencies

```bash
cd frontend
npm install
```

### 2. Environment variables

Create `frontend/.env` (gitignored):

```env
VITE_HOST_API=http://localhost:8000
VITE_ASSETS_API=http://localhost:8000
```

| Variable          | Description                      |
| ----------------- | -------------------------------- |
| `VITE_HOST_API`   | Base URL for all Axios API calls |
| `VITE_ASSETS_API` | Base URL for static/media assets |

Restart the dev server after changing `.env`.

### 3. Start the dev server

```bash
npm run dev
```

Open: **http://localhost:8081**

### 4. Available routes

| Path                        | Description                                                   |
| --------------------------- | ------------------------------------------------------------- |
| `/login`                    | Sign in with email + password                                 |
| `/register`                 | Create a new account                                          |
| `/dashboard`                | Overview landing page (requires auth)                         |
| `/dashboard/llm-chat`       | Chat with a local Ollama model                                |
| `/dashboard/multimodal-rag` | Upload PDFs (async S3 + Celery), query with RAG (SSE chat), manage memories, generate eval examples |
| `/playground`               | LLM playground with model/preset/temperature controls         |

JWT tokens are stored client-side; all authenticated requests include `Authorization: Bearer <token>`.

### 5. Frontend scripts

| Command             | Description                         |
| ------------------- | ----------------------------------- |
| `npm run dev`       | Dev server with HMR (port 8081)     |
| `npm run build`     | Production build to `dist/`         |
| `npm run preview`   | Preview the production build        |
| `npm run lint`      | Run ESLint                          |
| `npm run lint:fix`  | ESLint with auto-fix                |
| `npm run fm:fix`    | Prettier formatting                 |
| `npm run fix:all`   | Lint + format in one step           |
| `npm run tsc:watch` | TypeScript type-check in watch mode |

### 6. Key frontend dependencies

| Package                         | Role                                             |
| ------------------------------- | ------------------------------------------------ |
| `react` 19, `react-dom`         | UI framework                                     |
| `react-router-dom` v7           | Client-side routing with lazy loading            |
| `axios`                         | HTTP client (configured in `src/utils/axios.ts`) |
| `react-hook-form` + `zod`       | Form state and schema validation                 |
| `@radix-ui/*` + `shadcn/ui`     | Accessible, unstyled UI primitives               |
| `tailwindcss` 4                 | Utility-first styling                            |
| `framer-motion`                 | Animations                                       |
| `react-markdown` + `remark-gfm` | Markdown rendering for RAG chat replies          |
| `@excalidraw/excalidraw`        | Embedded whiteboard / diagram tool               |
| `lucide-react`                  | Icon library                                     |

---

## LangSmith tracing and evals

LangSmith covers **live tracing** during RAG chat and **experiment tracking** for offline eval runs. The eval system is LLM-native end to end: one LLM generates test cases, the RAG agent answers them, and separate LLM judges score each answer — see [Evaluation system](#evaluation-system).

### Setup and tracing

1. Create an API key at [smith.langchain.com](https://smith.langchain.com) and set `LANGSMITH_API_KEY` in `backend/.envs/.local/.rag`.
2. Restart Django: `docker compose -f docker-compose.local.yml restart django`.
3. Upload and process a PDF (`create-upload-url` → S3 PUT → `complete-upload`), then query via `POST /api/llm/rag/query/stream` — the ReAct agent's tool calls (retrieval + memory), hybrid search, and LLM steps appear as nested traces under `LANGSMITH_PROJECT`.

### Step 1 — generate test cases

Test cases are **generated on demand** from indexed document content — no checked-in fixtures for normal use.

| Step | UI | API |
| ---- | -- | --- |
| 1. Process PDF | Upload on `/dashboard/multimodal-rag` | `create-upload-url` → S3 PUT → `complete-upload` |
| 2. Generate examples | **Generate eval examples** on the document card | `POST /api/llm/documents/{id}/generate-eval-examples` |
| 3. Poll status | Status chip on the document card | `GET /api/llm/documents/{id}/eval-examples` |
| 4. Run evals | — | `python manage.py run_rag_eval` |

`Document.eval_generation_status`: `none` → `processing` → `completed` / `failed`

Optional body on step 2: `{ "sync_langsmith": true }` also pushes examples to the LangSmith dataset `promptly-multimodal-rag`.

Generation runs as Celery task `generate_eval_examples` (20 min soft / 25 min hard). Passages come from Qdrant (or S3 PDF re-parse as fallback); **`gpt-4o-mini`** writes grounded Q/A pairs into `EvalExample` rows in Postgres.

### Step 2 — run evals (LLM-as-judge)

```bash
docker exec -it app_local_django python manage.py run_rag_eval
```

For each example, the harness runs the production RAG agent, then **`gpt-4o-mini` judges** score **faithfulness** (grounded in retrieved context) and **answer_relevancy** (addresses the question). Judges return a 0.0–1.0 score plus a short reason; `faithfulness` is skipped when no context was retrieved.

**Eval scoping** — runs use `build_rag_agent(user_id="eval", document_id=…)` so retrieval is limited to one document. Production chat searches across all of the user's indexed documents.

**Eval flags**

| Flag                        | Description                                                             |
| --------------------------- | ----------------------------------------------------------------------- |
| `--local`                   | Run evaluators without uploading to LangSmith                           |
| `--sync-dataset`            | Push examples to a LangSmith dataset first                              |
| `--dataset-file <path>`     | Use a static JSON file instead of Postgres `EvalExample` rows           |
| `--document-id <n>`         | When loading from Postgres, restrict evals to one document                |
| `--dataset-name <name>`     | LangSmith dataset name (default: `promptly-multimodal-rag`)             |
| `--experiment-prefix <str>` | Prefix for the experiment name (default: `promptly-rag`)                |
| `--max-concurrency <n>`     | Parallel eval runs (default: 1)                                         |

By default, examples load from dynamically generated `EvalExample` rows in Postgres. Pass `--dataset-file` only for ad-hoc runs (e.g. `backend/app/llm/evals/sample_dataset.json`).

---

## End-to-end checklist

- [ ] `backend/.envs/.local/.django`, `.postgres`, and `.rag` files exist (including `S3_PUBLIC_ENDPOINT_URL`)
- [ ] `docker compose -f docker-compose.local.yml up --build` completes without errors
- [ ] Ollama model pulled (`ollama list` shows e.g. `llama3`)
- [ ] MinIO bucket `pdf-images` created at http://localhost:9201
- [ ] http://localhost:8000/api/docs/ loads
- [ ] `frontend/.env` points to `http://localhost:8000`
- [ ] `npm run dev` starts and http://localhost:8081 loads
- [ ] Register / login succeeds
- [ ] LLM chat returns a response
- [ ] (Optional) RAG: upload a PDF, wait for `processed` status, then query it (requires valid `OPENAI_API_KEY`)
- [ ] (Optional) Memory: tell the RAG chat a preference, confirm it appears in the memory panel
- [ ] (Optional) Evals: generate eval examples for a processed PDF, then run `python manage.py run_rag_eval --local`

---

## Troubleshooting

### Docker / backend

| Issue                                      | What to try                                                                                             |
| ------------------------------------------ | ------------------------------------------------------------------------------------------------------- |
| Port already in use                        | Stop other services on 8000, 5432, 13000, 6333, 9200, 9201, or change Compose port mappings             |
| `PostgreSQL is available` never appears    | Check `app_local_postgres` logs; verify `.postgres` env file                                            |
| Ollama chat 502 / "Failed to reach Ollama" | Ensure `app_local_ollama` is running and a model has been pulled                                        |
| RAG fails on S3/MinIO                      | Create the `pdf-images` bucket in the MinIO console; set `S3_PUBLIC_ENDPOINT_URL=http://localhost:9200` |
| Presigned upload URL unreachable           | `S3_PUBLIC_ENDPOINT_URL` must use a browser-accessible host, not `minio:9000`                           |
| RAG OpenAI errors                          | Set a valid `OPENAI_API_KEY` in `.rag` and restart Django                                               |
| CORS errors from frontend                  | `CORS_ALLOWED_ORIGINS` must include `http://localhost:8081` (default in local settings)                 |

### Frontend

| Issue                          | What to try                                               |
| ------------------------------ | --------------------------------------------------------- |
| API calls go to wrong host     | Check `VITE_HOST_API` in `.env` and restart `npm run dev` |
| 401 on dashboard routes        | Log in again; JWT may have expired                        |
| Blank page after `.env` change | Restart Vite and clear browser storage for the site       |

### Windows notes

- Run Compose from the `backend/` directory using `.\docker-compose.local.yml` in PowerShell.
- Ensure Docker Desktop is running with WSL2 or Linux containers enabled.
- If line-ending issues appear in shell scripts, the Dockerfiles already strip `\r` in entrypoint scripts.

---

## License

MIT — see [LICENSE](LICENSE).
