# Client Review Checklist (Execution)

## T-24 Hours

- [ ] Confirm machine and browser for demo are fixed (avoid last-minute hardware swap).
- [ ] Run full ingest and save output:
  - `PYTHONPATH=src python3 -m digital_brain ingest --data-dir data`
- [ ] Run tests:
  - `PYTHONPATH=src python3 -m unittest discover -s tests -v`
- [ ] Confirm Ollama model exists:
  - `ollama list` should include `llama3`
- [ ] Confirm auth env is set for RBAC demo:
  - `export DIGITAL_BRAIN_AUTH_ENABLED=1`
  - `export DIGITAL_BRAIN_BOOTSTRAP_ADMIN_USER=admin`
  - `export DIGITAL_BRAIN_BOOTSTRAP_ADMIN_PASSWORD=admin123`
- [ ] Confirm server can start cleanly:
  - `PYTHONPATH=src python3 -m digital_brain serve --host 127.0.0.1 --port 8080`
- [ ] Verify both pages load:
  - `http://127.0.0.1:8080/login.html`
  - `http://127.0.0.1:8080/operator.html`
  - `http://127.0.0.1:8080/admin.html`

## T-60 Minutes

- [ ] Re-ingest to ensure fresh local state:
  - `PYTHONPATH=src python3 -m digital_brain ingest --data-dir data`
- [ ] Export runtime env:
  - `export DIGITAL_BRAIN_AUTH_ENABLED=1`
  - `export DIGITAL_BRAIN_BOOTSTRAP_ADMIN_USER=admin`
  - `export DIGITAL_BRAIN_BOOTSTRAP_ADMIN_PASSWORD=admin123`
  - `export DIGITAL_BRAIN_LLM_PROVIDER=ollama`
  - `export DIGITAL_BRAIN_OLLAMA_MODEL=llama3`
  - `export DIGITAL_BRAIN_OLLAMA_BASE_URL=http://127.0.0.1:11434`
  - `export DIGITAL_BRAIN_FLOW_LLM_ASSIST=1`
- [ ] Confirm Ollama endpoint responds:
  - `curl -s http://127.0.0.1:11434/api/tags`
- [ ] Start app server and keep terminal visible.
- [ ] Create one operator demo user:
  - `PYTHONPATH=src python3 -m digital_brain create-user --username operator1 --password operator123 --role operator --upsert`
- [ ] Close unrelated CPU/memory-heavy apps.

## T-15 Minutes

- [ ] Dry-run one operator query and one troubleshoot flow.
- [ ] Verify flow meta shows `llm_assisted` or deterministic fallback reason.
- [ ] Dry-run login as admin and access `User Access Management`.
- [ ] Dry-run one realtime complaint + trouble event insert.
- [ ] Confirm admin page reflects unresolved/risk data.
- [ ] Keep fallback plan ready:
  - deterministic mode demo if Ollama latency/failure occurs

## During Review

- [ ] Start with ingest proof counts.
- [ ] Show one citation-grounded diagnosis.
- [ ] Show one branching troubleshooting session.
- [ ] Show role-based access (operator vs admin pages).
- [ ] Show one realtime update affecting next recommendation.
- [ ] Show admin unresolved/knowledge-gap signals.
- [ ] End with explicit next 2-week hardening plan.

## Risk Controls

- [ ] If `ollama serve` says `address already in use`, do not restart repeatedly.
  - Reason: service is already running on `127.0.0.1:11434`.
- [ ] If LLM times out, continue demo with deterministic fallback mode.
- [ ] If browser tab hangs, refresh only the current page, not full environment.
- [ ] Keep API terminal commands in a text file for fast copy/paste.

## Completion Evidence To Capture

- [ ] Screenshot of operator answer with citations.
- [ ] Screenshot of troubleshooting session final node.
- [ ] Screenshot of admin dashboard unresolved and knowledge-gap sections.
- [ ] Terminal output showing realtime insert success.
