# Client Review Demo Script (Feb 23-28, 2026)

## Goal
Show that the project is no longer in planning mode and already delivers a working end-to-end MVP:

1. Grounded diagnosis from manuals with citations.
2. Operator workflow with branching troubleshooting.
3. Realtime learning from new complaints, trouble events, and feedback.
4. Admin visibility into breakdowns and unresolved patterns.

## Demo Length
25-30 minutes total.

## Environment Setup (5 minutes)
Run these commands before the meeting:

```bash
cd /home/tanishy7777/coding/iitb_mock
PYTHONPATH=src python3 -m digital_brain ingest --data-dir data
export DIGITAL_BRAIN_AUTH_ENABLED=1
export DIGITAL_BRAIN_BOOTSTRAP_ADMIN_USER=admin
export DIGITAL_BRAIN_BOOTSTRAP_ADMIN_PASSWORD=admin123
export DIGITAL_BRAIN_LLM_PROVIDER=ollama
export DIGITAL_BRAIN_OLLAMA_MODEL=llama3
export DIGITAL_BRAIN_OLLAMA_BASE_URL=http://127.0.0.1:11434
export DIGITAL_BRAIN_FLOW_LLM_ASSIST=1
PYTHONPATH=src python3 -m digital_brain serve --host 127.0.0.1 --port 8080
```

Open:

- `http://127.0.0.1:8080/login.html`
- then `operator.html` and `admin.html` after login

## Suggested Talk Track

### Part 0: RBAC Proof (2 minutes)
Steps:

1. Open `login.html` and sign in as `admin`.
2. Show `admin.html` loads and includes User Access Management.
3. Sign out and login as operator account.
4. Show operator access works and admin-only actions are restricted.

Narrate:

"Access is role-governed now: operators run floor workflows, admins manage analytics/realtime ingest/users."

### Part 1: Data Ingestion Proof (2 minutes)
Narrate:

"We ingested your seed subset into the platform and built searchable machine memory."

Evidence:

- Confirm ingest output includes:
  - `machines: 264`
  - `complaints: 3423`
  - `trouble_events: 5890`
  - `documents: 4`
  - `chunks: 815`

### Part 2: Grounded Query + Citations (5 minutes)
Steps:

1. Login as operator/admin and open `operator.html`.
2. Enter issue text, for example: `vacuum leak and pressure instability`.
3. Submit query.
4. Show response sections:
   - answer
   - confidence
   - citations (manual snippets/path)
   - historical suggestions

Narrate:

"This answer is grounded in retrieved manual chunks and historical fixes, not pure free-form generation."

### Part 3: Troubleshooting Session Flow (6 minutes)
Steps:

1. Start a troubleshoot session from the same issue.
2. Answer `yes/no` to move across at least 3 nodes.
3. Show that allowed responses change by node type (`yes/no` for question, `done` for action).
4. Show `Flow mode` in the UI (`llm_assisted` or deterministic fallback reason).
5. Reach final node and close the session.

Narrate:

"This combines LLM flexibility with deterministic validation, so flow execution remains safe and auditable."

### Part 4: Learning Loop (Realtime) (7 minutes)
Steps:

1. Submit feedback from operator view:
   - thumbs down on one attempt
   - workaround comment describing what actually worked
2. Add a new complaint and trouble event through realtime APIs (terminal):

```bash
curl -s -X POST http://127.0.0.1:8080/api/realtime/complaint \
  -H 'Content-Type: application/json' \
  -d '{"machine_id":7,"complaint_description":"Realtime review demo issue","time_of_complaint":"2026-02-17 17:40:00","status":0,"status_resolved":"open"}'
```

Use the returned `complaint_id`:

```bash
COMPLAINT_ID=<returned_from_previous_call>
curl -s -X POST http://127.0.0.1:8080/api/realtime/trouble-event \
  -H 'Content-Type: application/json' \
  -d "{\"complaint_id\":${COMPLAINT_ID},\"timestamp\":\"2026-02-17 18:05:00\",\"diagnosis\":\"Review demo diagnosis\",\"action_taken\":\"Re-seat valve and replace fuse\",\"comments\":\"Recovered in one retry\"}"
```

3. Re-run a related query in operator UI.
4. Show updated historical suggestion with traceability.

Narrate:

"New field knowledge is available immediately on the next query. No retraining job required."

### Part 5: Admin Dashboard Evidence (5 minutes)
In `admin.html`, show:

1. Top breakdown machines.
2. Category and monthly trends.
3. Unresolved queue.
4. Failed feedback (at-risk) list.
5. Knowledge-gap keywords.
6. User Access Management panel (create/update role/active user).

Narrate:

"Management gets both operational analytics and role-governed access control."

## Expected Questions And Short Answers

1. "Is this production-ready?"
   - "No. It is an MVP proving end-to-end value. Next step is hardening: enterprise auth controls, scale, observability."
2. "Is LLM mandatory?"
   - "No. System still works with deterministic grounded fallback; LLM improves synthesis quality."
3. "Can it ingest new data continuously?"
   - "Yes. Realtime APIs already support new PDF documents, complaints, and trouble events."

## Demo Success Criteria

1. One issue is diagnosed with citations.
2. One troubleshoot session is completed end-to-end.
3. One new event is added and reflected in subsequent suggestions.
4. Admin dashboard shows actionable unresolved/risk signals.
