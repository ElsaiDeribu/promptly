# Promptly

Promptly is a full-stack application for experimenting with LLMs. It features a Django REST API backend and a React SPA frontend, supporting JWT authentication, local LLM chat via Ollama, and a multimodal RAG pipeline over PDFs using Qdrant, MinIO, and OpenAI. The RAG pipeline is powered by a LangGraph ReAct agent that uses a dedicated retrieval tool to fetch context before generating grounded answers. It includes integrated evaluation (evals) for retrieval quality, and leverages LangChain, LangGraph, and LangSmith for advanced orchestration, retrieval, and evaluation workflows.

Goal: Build a self-improving multi-agent system that continuously enhances retrieval, reasoning, and response quality through evaluation-driven feedback loops.
---

## Tech stack

| Layer | Stack |
|-------|--------|
| **Backend** | Python 3.12, Django 5, Django REST Framework, Celery, PostgreSQL, Redis |
| **LLM / AI** | Ollama (local models), OpenAI (embeddings + summaries),LangChain, LangGraph, LangSmith |
| **Storage** | Qdrant (vector DB), MinIO (S3-compatible object storage) |
| **Frontend** | React 19, TypeScript, Vite 6, Tailwind CSS 4 |
| **UI components** | shadcn/ui (Radix UI primitives), Lucide icons, Framer Motion |
| **Forms / validation** | React Hook Form, Zod |
| **HTTP / routing** | Axios, React Router v7 |

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
│   │   └── llm/                          # LLM features (chat + RAG)
│   │       ├── views.py                  # API views: models, chat, RAG endpoints
│   │       ├── serializers.py
│   │       ├── urls.py
│   │       ├── agents/
│   │       │   └── rag_agent.py          # LangGraph ReAct agent (orchestrates retrieval + generation)
│   │       ├── tools/
│   │       │   └── vector_rag.py         # vector_rag_tool: similarity search → raw context string
│   │       ├── services/
│   │       │   └── multimodal_rag/
│   │       │       └── rag_pipeline.py   # PDF ingestion pipeline (pre-process, summarise, index)
│   │       ├── utils/
│   │       │   ├── pdf_processor.py      # PDF parsing and image extraction
│   │       │   ├── s3.py                 # MinIO/S3 upload helpers
│   │       │   └── vector_db.py          # Qdrant upsert/search helpers
│   │       ├── evals/
│   │       │   ├── rag_eval.py           # LangSmith evaluators
│   │       │   └── sample_dataset.json   # Starter eval examples
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
    │   │   └── map/                      # Map section
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

| Tool | Version / notes |
|------|------------------|
| [Docker Desktop](https://www.docker.com/products/docker-desktop/) | Required for the backend and all supporting services |
| [Node.js](https://nodejs.org/) | **20+** recommended |
| npm or yarn | Comes with Node |

Optional:

- [Git](https://git-scm.com/) — clone the repo
- OpenAI API key — required for the **multimodal RAG** pipeline (embeddings + summarisation)
- Enough disk/RAM for Docker images and Ollama models (models are large)

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
# OpenAI (embeddings + summarisation)
OPENAI_API_KEY=your-openai-api-key

# Optional: LangSmith tracing and evals
LANGSMITH_TRACING=true
LANGSMITH_ENDPOINT=https://api.smith.langchain.com
LANGSMITH_API_KEY=your-langsmith-api-key
LANGSMITH_PROJECT=promptly-rag

# Qdrant (vector store)
QDRANT_HOST=qdrant
QDRANT_PORT=6333

# MinIO (object storage for extracted PDF images)
MINIO_HOST=minio
MINIO_PORT=9000
MINIO_ACCESS_KEY=minioadmin
MINIO_SECRET_KEY=minioadmin

S3_BUCKET_NAME=pdf-images
S3_ENDPOINT_URL=http://minio:9000
AWS_ACCESS_KEY_ID=minioadmin
AWS_SECRET_ACCESS_KEY=minioadmin
AWS_DEFAULT_REGION=us-east-1

# Ollama (local LLM)
OLLAMA_BASE_URL=http://ollama:11434
OLLAMA_MODEL=llama3
```

Chat-only features work without `OPENAI_API_KEY`; RAG endpoints will fail without it.

### 2. Start the stack

```bash
cd backend
docker compose -f docker-compose.local.yml up --build
```

First run can take several minutes (image builds, Python wheels, NLTK data). To run detached: add `-d`. To stop: `docker compose -f docker-compose.local.yml down`.

### 3. Services

| Service | Container | Host port | Purpose |
|---------|-------------|-----------|---------|
| **django** | `app_local_django` | 8000 | REST API (Uvicorn, auto-migrate on start) |
| **postgres** | `app_local_postgres` | 5432 | Application database |
| **redis** | `app_local_redis` | — | Celery broker |
| **mailpit** | `app_local_mailpit` | 8025 | Dev email UI (SMTP on 1025 inside network) |
| **ollama** | `app_local_ollama` | 11434 | Local LLM runtime |
| **minio** | `app_local_minio` | 9200 (API), 9201 (console) | Object storage |
| **qdrant** | `app_local_qdrant` | 6333, 6334 | Vector database |
| **celeryworker** | `app_local_celeryworker` | — | Background tasks |
| **celerybeat** | `app_local_celerybeat` | — | Scheduled tasks |
| **flower** | `app_local_flower` | 5555 | Celery monitoring UI |

### 4. Pull an Ollama model

```bash
docker exec -it app_local_ollama ollama pull llama3
```

The API defaults to `llama3`. Override with `OLLAMA_MODEL` in `.rag`.

### 5. Create the MinIO bucket

RAG stores extracted PDF images in the bucket defined by `S3_BUCKET_NAME` (default: `pdf-images`).

1. Open **MinIO Console**: http://localhost:9201
2. Log in: `minioadmin` / `minioadmin`
3. Create a bucket named **`pdf-images`**.

### 6. Create a Django superuser (optional)

```bash
docker exec -it app_local_django python manage.py createsuperuser
```

Django admin: http://localhost:8000/admin/

### 7. API endpoints

| URL | Description |
|-----|-------------|
| http://localhost:8000/api/docs/ | Swagger UI |
| http://localhost:8000/api/schema/ | OpenAPI schema |
| http://localhost:8025 | Mailpit dev email UI |

**Auth**

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/api/auth/register` | Create account |
| `POST` | `/api/auth/login` | Get JWT tokens |
| `GET` | `/api/auth/me` | Current user (requires token) |

**LLM / RAG**

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/api/llm/models` | List available Ollama models |
| `POST` | `/api/llm/chat` | Chat with an Ollama model |
| `POST` | `/api/llm/rag/process` | Ingest and index a PDF |
| `POST` | `/api/llm/rag/query` | Query indexed PDF content |

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

# LangSmith RAG evals (requires indexed PDFs + OPENAI_API_KEY)
docker exec -it app_local_django python manage.py run_rag_eval

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

| Variable | Description |
|----------|-------------|
| `VITE_HOST_API` | Base URL for all Axios API calls |
| `VITE_ASSETS_API` | Base URL for static/media assets |

Restart the dev server after changing `.env`.

### 3. Start the dev server

```bash
npm run dev
```

Open: **http://localhost:8081**

### 4. Available routes

| Path | Description |
|------|-------------|
| `/login` | Sign in with email + password |
| `/register` | Create a new account |
| `/dashboard` | Overview landing page (requires auth) |
| `/dashboard/llm-chat` | Chat with a local Ollama model |
| `/dashboard/multimodal-rag` | Upload PDFs and query them with RAG |
| `/playground` | LLM playground with model/preset/temperature controls |

JWT tokens are stored client-side; all authenticated requests include `Authorization: Bearer <token>`.

### 5. Frontend scripts

| Command | Description |
|---------|-------------|
| `npm run dev` | Dev server with HMR (port 8081) |
| `npm run build` | Production build to `dist/` |
| `npm run preview` | Preview the production build |
| `npm run lint` | Run ESLint |
| `npm run lint:fix` | ESLint with auto-fix |
| `npm run fm:fix` | Prettier formatting |
| `npm run fix:all` | Lint + format in one step |
| `npm run tsc:watch` | TypeScript type-check in watch mode |

### 6. Key frontend dependencies

| Package | Role |
|---------|------|
| `react` 19, `react-dom` | UI framework |
| `react-router-dom` v7 | Client-side routing with lazy loading |
| `axios` | HTTP client (configured in `src/utils/axios.ts`) |
| `react-hook-form` + `zod` | Form state and schema validation |
| `@radix-ui/*` + `shadcn/ui` | Accessible, unstyled UI primitives |
| `tailwindcss` 4 | Utility-first styling |
| `framer-motion` | Animations |
| `@excalidraw/excalidraw` | Embedded whiteboard / diagram tool |
| `lucide-react` | Icon library |

---

## LangSmith tracing and evals

1. Create an API key at [smith.langchain.com](https://smith.langchain.com) and set `LANGSMITH_API_KEY` in `backend/.envs/.local/.rag`.
2. Restart Django: `docker compose -f docker-compose.local.yml restart django`.
3. Process a PDF via `POST /api/llm/rag/process`, then query via `POST /api/llm/rag/query` — the ReAct agent's tool calls and LLM steps appear as nested traces under `LANGSMITH_PROJECT`.
4. Run offline evals:

```bash
docker exec -it app_local_django python manage.py run_rag_eval
```

**Eval flags**

| Flag | Description |
|------|-------------|
| `--local` | Run evaluators without uploading to LangSmith |
| `--sync-dataset` | Push examples to a LangSmith dataset first |
| `--dataset-file <path>` | JSON file of eval examples (`inputs.question`, optional `outputs.answer`) |
| `--dataset-name <name>` | LangSmith dataset name (default: `promptly-multimodal-rag`) |
| `--experiment-prefix <str>` | Prefix for the experiment name (default: `promptly-rag`) |
| `--max-concurrency <n>` | Parallel eval runs (default: 1) |

**Built-in evaluators** (defined in `backend/app/llm/evals/rag_eval.py`)

| Evaluator | What it checks |
|-----------|----------------|
| `has_context` | `vector_rag_tool` was called by the agent and returned real content (not the "no context" fallback) |
| `answer_not_empty` | Answer is non-empty and does not fall back to "don't have enough context" |
| `reference_overlap` | Word-overlap ratio between the generated answer and a reference answer (skipped when no reference is provided) |

Customise `backend/app/llm/evals/sample_dataset.json` with reference answers once you know what your indexed PDFs should return.

---

## End-to-end checklist

- [ ] `backend/.envs/.local/.django`, `.postgres`, and `.rag` files exist
- [ ] `docker compose -f docker-compose.local.yml up --build` completes without errors
- [ ] Ollama model pulled (`ollama list` shows e.g. `llama3`)
- [ ] MinIO bucket `pdf-images` created at http://localhost:9201
- [ ] http://localhost:8000/api/docs/ loads
- [ ] `frontend/.env` points to `http://localhost:8000`
- [ ] `npm run dev` starts and http://localhost:8081 loads
- [ ] Register / login succeeds
- [ ] LLM chat returns a response
- [ ] (Optional) RAG: upload a PDF, then query it (requires valid `OPENAI_API_KEY`)

---

## Troubleshooting

### Docker / backend

| Issue | What to try |
|-------|-------------|
| Port already in use | Stop other services on 8000, 5432, 11434, 6333, 9200, 9201, or change Compose port mappings |
| `PostgreSQL is available` never appears | Check `app_local_postgres` logs; verify `.postgres` env file |
| Ollama chat 502 / "Failed to reach Ollama" | Ensure `app_local_ollama` is running and a model has been pulled |
| RAG fails on S3/MinIO | Create the `pdf-images` bucket in the MinIO console |
| RAG OpenAI errors | Set a valid `OPENAI_API_KEY` in `.rag` and restart Django |
| CORS errors from frontend | `CORS_ALLOWED_ORIGINS` must include `http://localhost:8081` (default in local settings) |

### Frontend

| Issue | What to try |
|-------|-------------|
| API calls go to wrong host | Check `VITE_HOST_API` in `.env` and restart `npm run dev` |
| 401 on dashboard routes | Log in again; JWT may have expired |
| Blank page after `.env` change | Restart Vite and clear browser storage for the site |

### Windows notes

- Run Compose from the `backend/` directory using `.\docker-compose.local.yml` in PowerShell.
- Ensure Docker Desktop is running with WSL2 or Linux containers enabled.
- If line-ending issues appear in shell scripts, the Dockerfiles already strip `\r` in entrypoint scripts.

---

## License

MIT — see [LICENSE](LICENSE).
