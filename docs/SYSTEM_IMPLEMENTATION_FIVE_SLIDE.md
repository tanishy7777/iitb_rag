# Slide 1: Problem and Vision

## Problem
- Operators face noisy, high-pressure troubleshooting conditions.
- Manuals are long and static; practical fixes live in tribal knowledge.
- Management lacks realtime visibility into unresolved and recurring failures.

## Vision
Build a self-evolving digital brain that:
- answers with manual-grounded evidence,
- adapts from actual repair outcomes,
- and exposes operational intelligence to management.

---

# Slide 2: System Architecture

## Core Stack
- **UI:** Operator + Admin web interfaces
- **API/Service:** session workflow, retrieval, ranking, feedback loop
- **Storage:** SQLite canonical tables + session/event logs
- **Retrieval:** chunked manual index (BM25)
- **Synthesis:** Ollama llama3 (default) or deterministic fallback

## Data Inputs
- PDF docs: SOP/Policy/Recipe/Manual
- SQL history: machines, complaints, trouble events
- Realtime feeds: new docs, complaints, trouble events, feedback

## Safety Layer
- Confidence scoring
- Low-evidence guardrail responses
- Audit logging

---

# Slide 3: Operator Experience (End-to-End)

## Workflow
1. Select machine + describe issue
2. Receive grounded diagnosis with citations and confidence
3. Execute interactive yes/no troubleshooting session
4. Submit fix outcome (thumbs up/down + workaround)
5. System reuses fresh feedback in the next similar case

## UX Features
- Triage quick chips: Power / Hydraulics / Tooling
- Recent machine shortcuts
- Loading indicators for LLM latency
- Persistent troubleshooting sessions (server-side state)

---

# Slide 4: Learning Loop and Realtime RAG

## Realtime Learning Sources
- `equipment_complaint` history
- `trouble_track` actions
- operator feedback workarounds

## What Happens Realtime
- New complaint/trouble event upserts are instantly queryable
- New feedback influences ranking on next query
- New PDF ingestion rebuilds relevant retrieval index immediately

## Guidance Style
- “Manual says X” (citations)
- “Historically worked Y” (traceable source)

---

# Slide 5: Outcomes, Status, and Next Steps

## Delivered Outcomes
- Roadmap phases 1-4 implemented in MVP form
- Phase 5 core hardening controls in place (confidence, audit, tests)
- Optional local LLM (Ollama llama3) integrated

## KPI-ready Signals Available
- Top breakdown machines
- Unresolved and at-risk queues
- Feedback trend by machine
- Category/month breakdown trends
- Knowledge-gap clusters

## Next Steps
1. Production data layer (Postgres + scalable retrieval)
2. Auth/role governance
3. Deeper observability (latency/fallback/confidence dashboards)
4. Stronger semantic clustering and citation span verification
