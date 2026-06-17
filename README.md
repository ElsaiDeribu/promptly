# Promptly

Promptly is a full-stack app for experimenting with LLMs: JWT auth, an Ollama chat proxy, and a multimodal RAG pipeline over PDFs (Qdrant, MinIO, OpenAI).

| Layer | Stack |
|-------|--------|
| **Backend** | Django REST Framework, Celery, PostgreSQL, Redis, Ollama, Qdrant, MinIO |
| **Frontend** | React 19, TypeScript, Vite, Tailwind CSS |

---

## Prerequisites

Install these before you start:

| Tool | Version / notes |
|------|------------------|
| [Docker Desktop](https://www.docker.com/products/docker-desktop/) | Required for the backend and all supporting services |
| [Node.js](https://nodejs.org/) | **20+** recommended (for the frontend) |
| npm or yarn | Comes with Node; the frontend scripts work with either |

Optional:

- [Git](https://git-scm.com/) — clone the repo
- OpenAI API key — required for **multimodal RAG** (embeddings + chat)
- Enough disk/RAM for Docker images and Ollama models (models are large)

---

## Repository layout

```text
promptly/
├── backend/                        # Django API + Docker Compose stack
│   ├── docker-compose.local.yml
│   ├── justfile                    # Just recipes for common dev tasks
│   ├── .envs/.local/               # Local secrets (not committed; you create these)
│   └── app/llm/
│       ├── evals/                  # LangSmith offline eval harness
│       │   ├── rag_eval.py         # Evaluators + run_rag_evaluation()
│       │   └── sample_dataset.json # Starter eval examples (customise me)
│       ├── management/commands/
│       │   └── run_rag_eval.py     # `manage.py run_rag_eval` entry point
│       └── services/multimodal_rag/
│           └── rag_pipeline.py     # LangGraph RAG graph + run_rag_query()
└── frontend/                       # React SPA (Vite dev server on port 8081)
```

---

## Quick start (local development)

1. Configure backend environment files (see [Backend setup](#backend-setup)).
2. Start the backend with Docker Compose.
3. Pull at least one Ollama model and create the MinIO bucket.
4. Configure the frontend `.env` and run the dev server.
5. Open the app, register or log in, and use the dashboard.

Detailed steps for each part are below.

---

## Backend setup

All backend services run via Docker Compose from the `backend` directory.

### 1. Create environment files

The backend loads env from `backend/.envs/.local/`. These paths are **gitignored** — create them locally (do not commit API keys).

#### `backend/.envs/.local/.django`

```env
# General
USE_DOCKER=yes
IPYTHONDIR=/app/.ipython

# Redis
REDIS_URL=redis://redis:6379/0

# Celery Flower (monitoring UI)
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

`DATABASE_URL` is built automatically in the Django container entrypoint from these variables.

#### `backend/.envs/.local/.rag`

Required for multimodal RAG (PDF processing and queries). Use **Docker service hostnames** (not `localhost`) so containers can reach each other.

```env
# OpenAI (required for RAG embeddings and summarization)
OPENAI_API_KEY=your-openai-api-key

# Optional: LangSmith tracing and evals
LANGSMITH_TRACING=true
LANGSMITH_ENDPOINT=https://api.smith.langchain.com
LANGSMITH_API_KEY=your-langsmith-api-key
LANGSMITH_PROJECT=promptly-rag

# Qdrant (vector store)
QDRANT_HOST=qdrant
QDRANT_PORT=6333

# MinIO (S3-compatible object storage for extracted images)
MINIO_HOST=minio
MINIO_PORT=9000
MINIO_ACCESS_KEY=minioadmin
MINIO_SECRET_KEY=minioadmin

S3_BUCKET_NAME=pdf-images
S3_ENDPOINT_URL=http://minio:9000
AWS_ACCESS_KEY_ID=minioadmin
AWS_SECRET_ACCESS_KEY=minioadmin
AWS_DEFAULT_REGION=us-east-1

# Ollama (local chat; optional overrides)
OLLAMA_BASE_URL=http://ollama:11434
OLLAMA_MODEL=llama3
```

Chat-only features can work without `OPENAI_API_KEY`; RAG endpoints will fail without it.

### 2. Start the stack

From the repository root:

```bash
cd backend
docker compose -f docker-compose.local.yml up --build
```

First run can take several minutes (image builds, Python wheels, NLTK data).

To run detached:

```bash
docker compose -f docker-compose.local.yml up --build -d
```

To stop:

```bash
docker compose -f docker-compose.local.yml down
```

### 3. Services started by Compose

| Service | Container | Host port | Purpose |
|---------|-------------|-----------|---------|
| **django** | `app_local_django` | 8000 | REST API (Uvicorn + auto-migrate on start) |
| **postgres** | `app_local_postgres` | 5432 | Application database |
| **redis** | `app_local_redis` | — | Celery broker |
| **mailpit** | `app_local_mailpit` | 8025 | Dev email UI (SMTP on 1025 inside network) |
| **ollama** | `app_local_ollama` | 11434 | Local LLM runtime |
| **minio** | `app_local_minio` | 9200 (API), 9201 (console) | Object storage |
| **qdrant** | `app_local_qdrant` | 6333, 6334 | Vector database |
| **celeryworker** | `app_local_celeryworker` | — | Background tasks |
| **celerybeat** | `app_local_celerybeat` | — | Scheduled tasks |
| **flower** | `app_local_flower` | 5555 | Celery monitoring |

Django also exposes port **8501** for optional Streamlit tooling (not started by default).

### 4. Pull an Ollama model

The API defaults to model name `llama3`. Pull it (or another model and set `OLLAMA_MODEL`):

```bash
docker exec -it app_local_ollama ollama pull llama3
```

List models:

```bash
docker exec -it app_local_ollama ollama list
```

### 5. Create the MinIO bucket

RAG stores extracted PDF images in the bucket named in `S3_BUCKET_NAME` (default: `pdf-images`).

1. Open **MinIO Console**: http://localhost:9201  
2. Login: `minioadmin` / `minioadmin` (defaults from Compose)  
3. Create a bucket named **`pdf-images`** (or match your `S3_BUCKET_NAME`).

### 6. Create a Django superuser (optional)

For Django admin and API docs restricted to admins:

```bash
docker exec -it app_local_django python manage.py createsuperuser
```

Admin: http://localhost:8000/admin/

### 7. Verify the API

| URL | Description |
|-----|-------------|
| http://localhost:8000/api/docs/ | Swagger UI (admin login may be required) |
| http://localhost:8000/api/schema/ | OpenAPI schema |
| http://localhost:8025 | Mailpit — emails sent in dev |

**Main API prefixes:**

- `POST /api/auth/register` — create account  
- `POST /api/auth/login` — JWT login  
- `GET /api/auth/me` — current user (authenticated)  
- `GET /api/llm/models` — list Ollama models  
- `POST /api/llm/chat` — chat via Ollama  
- `POST /api/llm/rag/process` — ingest a PDF  
- `POST /api/llm/rag/query` — query indexed content  

CORS is configured for `http://localhost:8081` (frontend dev server).

### 8. Useful backend commands

```bash
# Run migrations manually (also run on container start)
docker exec -it app_local_django python manage.py migrate

# Django shell
docker exec -it app_local_django python manage.py shell

# Run tests
docker exec -it app_local_django pytest

# View logs for one service
docker compose -f docker-compose.local.yml logs -f django

# Run LangSmith RAG evals (requires indexed PDFs + OPENAI_API_KEY)
docker exec -it app_local_django python manage.py run_rag_eval

# Run evals locally without uploading to LangSmith
docker exec -it app_local_django python manage.py run_rag_eval --local

# Shorthand via just
just rag-eval
just rag-eval --local
```

More backend notes: [backend/README.md](backend/README.md) (Cookiecutter Django boilerplate docs).

### LangSmith tracing and evals

1. Create an API key at [smith.langchain.com](https://smith.langchain.com) and set `LANGSMITH_API_KEY` in `backend/.envs/.local/.rag` (see env block above).
2. Restart Django so tracing env vars load: `docker compose -f docker-compose.local.yml restart django`.
3. Process at least one PDF via `POST /api/llm/rag/process`, then hit `POST /api/llm/rag/query` — traces appear under the `LANGSMITH_PROJECT` (default: `promptly-rag`).
4. Run offline evals against the sample dataset:

```bash
docker exec -it app_local_django python manage.py run_rag_eval
```

Options:

| Flag | Description |
|------|-------------|
| `--local` | Run evaluators without uploading to LangSmith |
| `--sync-dataset` | Push examples to a LangSmith dataset before evaluating |
| `--dataset-file <path>` | Path to a JSON file of eval examples (`inputs.question`, optional `outputs.answer`) |
| `--dataset-name <name>` | LangSmith dataset name (default: `promptly-multimodal-rag`) |
| `--experiment-prefix <str>` | Prefix for the experiment name (default: `promptly-rag`) |
| `--max-concurrency <n>` | Parallel eval runs (default: 1) |

**Built-in evaluators** (defined in `backend/app/llm/evals/rag_eval.py`):

| Evaluator | What it checks |
|-----------|----------------|
| `has_context` | Retrieved context contains at least one text chunk or image |
| `answer_not_empty` | Answer is non-empty and does not fall back to "don't have enough context" |
| `reference_overlap` | Word-overlap ratio between the generated answer and a reference answer (skipped when no reference is provided) |

Customize `backend/app/llm/evals/sample_dataset.json` with reference answers after you know what your indexed PDFs should return.

---

## Frontend setup

The frontend is a Vite + React SPA that talks to the Django API on port **8000**. The dev server runs on port **8081**.

### 1. Install dependencies

```bash
cd frontend
npm install
```

Or with Yarn:

```bash
cd frontend
yarn install
```

### 2. Environment variables

Create `frontend/.env` (gitignored):

```env
VITE_HOST_API=http://localhost:8000
VITE_ASSETS_API=http://localhost:8000
```

| Variable | Description |
|----------|-------------|
| `VITE_HOST_API` | Base URL for Axios API calls (must match Django) |
| `VITE_ASSETS_API` | Base URL for static/media assets |

Restart the dev server after changing `.env`.

### 3. Start the dev server

```bash
npm run dev
```

Or:

```bash
yarn dev
```

Open: **http://localhost:8081**

### 4. Use the app

1. Ensure the backend is up (`docker compose` in `backend/`).
2. Register at http://localhost:8081/register or log in at http://localhost:8081/login.
3. After login you are redirected to the dashboard:
   - **LLM chat** — Ollama-backed chat (`/dashboard/llm-chat`)
   - **Multimodal RAG** — upload/query PDFs (`/dashboard/multimodal-rag`)

JWT tokens are stored client-side; API requests use `Authorization: Bearer <token>`.

### 5. Frontend scripts

| Command | Description |
|---------|-------------|
| `npm run dev` | Dev server with HMR (port 8081) |
| `npm run build` | Production build to `dist/` |
| `npm run preview` | Preview production build |
| `npm run lint` | ESLint |
| `npm run lint:fix` | ESLint with auto-fix |

### 6. Production build (optional)

```bash
npm run build
```

Serve the `frontend/dist` folder with any static host. Set `VITE_HOST_API` to your deployed API URL at **build time**.

---

## End-to-end checklist

Use this to confirm everything works:

- [ ] `backend/.envs/.local/.django`, `.postgres`, and `.rag` exist  
- [ ] `docker compose -f docker-compose.local.yml up --build` runs without errors  
- [ ] Ollama model pulled (`ollama list` shows e.g. `llama3`)  
- [ ] MinIO bucket `pdf-images` exists  
- [ ] http://localhost:8000/api/docs/ loads  
- [ ] `frontend/.env` points to `http://localhost:8000`  
- [ ] `npm run dev` → http://localhost:8081 loads  
- [ ] Register/login succeeds  
- [ ] LLM chat returns a response  
- [ ] (Optional) RAG: upload PDF, then query (needs valid `OPENAI_API_KEY`)

---

## Troubleshooting

### Docker / backend

| Issue | What to try |
|-------|-------------|
| Port already in use | Stop other services on 8000, 5432, 11434, 6333, 9200, 9201, or change Compose port mappings |
| `PostgreSQL is available` never appears | Check `app_local_postgres` logs; verify `.postgres` env file |
| Ollama chat 502 / “Failed to reach Ollama” | Ensure `app_local_ollama` is running; pull a model (`ollama pull llama3`) |
| RAG fails on S3/MinIO | Create the `pdf-images` bucket in MinIO console |
| RAG OpenAI errors | Set a valid `OPENAI_API_KEY` in `.rag` and restart Django |
| CORS errors from frontend | Backend `CORS_ALLOWED_ORIGINS` must include `http://localhost:8081` (default in local settings) |

### Frontend

| Issue | What to try |
|-------|-------------|
| API calls go to wrong host | Check `VITE_HOST_API` in `.env`; restart `npm run dev` |
| 401 on dashboard routes | Log in again; JWT may have expired |
| Blank page after env change | Restart Vite; clear browser storage for the site |

### Windows notes

- Run Compose from `backend` with forward slashes or `.\docker-compose.local.yml` as in PowerShell examples above.
- Ensure Docker Desktop is running with WSL2 or Linux containers enabled.
- If line-ending issues appear in shell scripts, the Dockerfiles already strip `\r` in entrypoint scripts.

---

## License

MIT — see [LICENSE](LICENSE).
