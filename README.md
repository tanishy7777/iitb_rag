# Digital Brain MVP (Seed-Data End-to-End)

This implementation starts the end-to-end system using your uploaded subset:

- PDFs: `1_SOP.pdf`, `1_POLICY.pdf`, `3_RECEPIES.pdf`, `7_manuals.pdf`
- SQL dumps: `eqp-process_resources.sql`, `equipment_complaint.sql`, `trouble_track.sql`, `facility_resources.sql`, `safety_resources.sql`, `lab_incharge.sql`

## What is implemented

- SQL ingestion for machine metadata, complaint history, and troubleshooting events.
- PDF text extraction and chunking.
- Retrieval engine (BM25) with machine-filtered manual citations.
- Optional LLM-backed RAG synthesis (OpenAI-compatible) with grounded fallback.
- Optional local LLM-backed RAG synthesis via Ollama (`llama3`) with grounded fallback.
- Historical workaround suggestions mined from `equipment_complaint` + `trouble_track`.
- Dynamic troubleshooting flow with yes/no branching generated from machine-specific history signals.
- Persistent troubleshooting sessions with server-side state transitions.
- Confidence gating + citation guardrail for low-evidence queries.
- Audit logs and recent-machine tracking.
- Feedback capture (`thumbs up/down` + workaround text).
- Admin analytics: machine/category/month breakdowns + unresolved queue + failed feedback + knowledge gaps.
- React Operator/Admin pages (legacy HTML pages kept as fallback).

## Project layout

- `src/digital_brain/sql_dump.py` - parser for MySQL dump INSERT blocks.
- `src/digital_brain/pdf_ingest.py` - PDF extraction and document typing.
- `src/digital_brain/service.py` - ingest/query/feedback/admin orchestration.
- `src/digital_brain/api_server.py` - HTTP API + static web serving.
- `frontend/src/pages/OperatorPage.tsx` - operator workflow (canonical route: `/operator`).
- `frontend/src/pages/AdminPage.tsx` - admin dashboard (canonical route: `/admin`).
- `frontend/src/pages/LoginPage.tsx` - login page (canonical route: `/login`).
- `web/*.html` - legacy fallback pages.

## Run locally

### 1. Ingest the seed data

```bash
PYTHONPATH=src python3 -m digital_brain ingest --data-dir data
```

### 2. Run a CLI query

```bash
PYTHONPATH=src python3 -m digital_brain query --machine-id 7 --question "vacuum leak and pressure instability"
```

### 2b. Persistent troubleshooting session via CLI

```bash
PYTHONPATH=src python3 -m digital_brain troubleshoot-start --machine-id 7 --question "vacuum leak and pressure instability"
PYTHONPATH=src python3 -m digital_brain troubleshoot-next --session-id <SESSION_ID> --response yes
PYTHONPATH=src python3 -m digital_brain troubleshoot-session --session-id <SESSION_ID>
```

### 2c. Realtime updates via CLI

```bash
PYTHONPATH=src python3 -m digital_brain realtime-add-document --path data/7_manuals.pdf --machine-id 7 --doc-type manual
PYTHONPATH=src python3 -m digital_brain realtime-add-complaint --machine-id 7 --description "Realtime complaint"
PYTHONPATH=src python3 -m digital_brain realtime-add-trouble-event --complaint-id <ID> --action "Applied workaround"
```

### 3. Start the local server

```bash
PYTHONPATH=src python3 -m digital_brain serve --host 127.0.0.1 --port 8080
```

Open:

- `http://127.0.0.1:8080/operator`
- `http://127.0.0.1:8080/admin`

### 3c. React frontend (canonical routes)

A React + TypeScript app in `frontend/` serves canonical UI routes:

- `/login`
- `/operator`
- `/admin`

Build it with:

```bash
cd frontend
npm install
npm run build
```

Then run the Python server with React UI mode:

```bash
export DIGITAL_BRAIN_UI_MODE=react
PYTHONPATH=src python3 -m digital_brain serve --host 127.0.0.1 --port 8080
```

Notes:

- Recommended: `DIGITAL_BRAIN_UI_MODE=react` for canonical route behavior.
- `DIGITAL_BRAIN_UI_MODE=auto` uses React only when `frontend/dist/index.html` exists.
- `DIGITAL_BRAIN_UI_MODE=legacy` keeps existing `web/*.html` fallback pages.
- Backend API endpoints remain unchanged during migration.

### 3b. Enable authentication + RBAC (operator/admin)

By default, auth is off for local compatibility. Enable it with:

```bash
export DIGITAL_BRAIN_AUTH_ENABLED=1
export DIGITAL_BRAIN_BOOTSTRAP_ADMIN_USER=admin
export DIGITAL_BRAIN_BOOTSTRAP_ADMIN_PASSWORD=admin123
```

Then start server and open:

- `http://127.0.0.1:8080/login`

Role rules:

- `operator`: operator APIs and `/operator`
- `admin`: operator + admin APIs, realtime ingest APIs, and `/admin`

Create extra users from CLI:

```bash
PYTHONPATH=src python3 -m digital_brain create-user --username operator1 --password operator123 --role operator --upsert
PYTHONPATH=src python3 -m digital_brain create-user --username admin2 --password admin456 --role admin --upsert
```

### Troubleshooting session APIs

- `POST /api/troubleshoot/start` with `{ "machine_id": 7, "question": "..." }`
- `POST /api/troubleshoot/next` with `{ "session_id": "...", "response": "yes|no|done" }`
- `GET /api/troubleshoot/session?session_id=...`
- `GET /api/machines/recent?limit=8`

### Optional LLM RAG mode

Set environment variables before running query/server:

```bash
export DIGITAL_BRAIN_LLM_PROVIDER=ollama
export DIGITAL_BRAIN_OLLAMA_MODEL=llama3
export DIGITAL_BRAIN_OLLAMA_BASE_URL=http://127.0.0.1:11434
```

Optional hybrid-flow toggle (LLM-assisted flow + deterministic validation/fallback):

```bash
export DIGITAL_BRAIN_FLOW_LLM_ASSIST=1
```

When enabled, troubleshooting flow uses:

- LLM-assisted proposal when LLM answer mode is active
- strict flow validation (node kinds/transitions)
- deterministic fallback with `flow_reason` when proposal is invalid

Start Ollama and pull model if needed:

```bash
ollama pull llama3
ollama serve
```

If Ollama is unavailable, the system falls back to deterministic grounded responses.

To use hosted OpenAI instead:

```bash
export DIGITAL_BRAIN_LLM_PROVIDER=openai
export OPENAI_API_KEY=<your_key>
export DIGITAL_BRAIN_OPENAI_MODEL=gpt-4.1-mini
```

### Realtime ingest APIs

- `POST /api/realtime/document` with `{ "path": "data/new_manual.pdf", "machine_id": 7, "doc_type": "manual" }`
- `POST /api/realtime/complaint` with `{ "machine_id": 7, "complaint_description": "...", "status": 0 }`
- `POST /api/realtime/trouble-event` with `{ "complaint_id": 123, "action_taken": "...", "diagnosis": "..."}`

### Auth APIs

- `POST /api/auth/login` with `{ "username": "...", "password": "..." }`
- `POST /api/auth/logout`
- `GET /api/auth/me`

### Admin User Management APIs (admin role)

- `GET /api/admin/users`
- `POST /api/admin/users` with `{ "username": "...", "password": "...", "role": "operator|admin", "is_active": true, "upsert": true }`
- `POST /api/admin/users/update` with `{ "user_id": 2, "role": "operator|admin", "is_active": true, "password": "optional_new_password" }`
- `GET /api/admin/analytics` with optional filters:
  - `machine_id=<int>`
  - `category=<string>`
  - `date_from=YYYY-MM-DD`
  - `date_to=YYYY-MM-DD`

These updates are applied immediately. Document ingest rebuilds retrieval index in-process, and complaint/trouble/feedback updates affect ranking on the next query.

## Run tests

```bash
PYTHONPATH=src python3 -m unittest discover -s tests -v
```

## Notes

- This MVP is intentionally local-first and dependency-light (standard library + `pdftotext`).
- Vision-based and voice-dialect pipelines are deferred for next phase.
- Some SQL rows contain legacy date/value quirks; parser is tolerant by design.
