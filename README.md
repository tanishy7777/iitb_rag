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
- Operator/Admin web pages.

## Project layout

- `src/digital_brain/sql_dump.py` - parser for MySQL dump INSERT blocks.
- `src/digital_brain/pdf_ingest.py` - PDF extraction and document typing.
- `src/digital_brain/service.py` - ingest/query/feedback/admin orchestration.
- `src/digital_brain/api_server.py` - HTTP API + static web serving.
- `web/operator.html` - operator workflow.
- `web/admin.html` - admin dashboard.

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

- `http://127.0.0.1:8080/operator.html`
- `http://127.0.0.1:8080/admin.html`

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

These updates are applied immediately. Document ingest rebuilds retrieval index in-process, and complaint/trouble/feedback updates affect ranking on the next query.

## Run tests

```bash
PYTHONPATH=src python3 -m unittest discover -s tests -v
```

## Notes

- This MVP is intentionally local-first and dependency-light (standard library + `pdftotext`).
- Vision-based and voice-dialect pipelines are deferred for next phase.
- Some SQL rows contain legacy date/value quirks; parser is tolerant by design.
