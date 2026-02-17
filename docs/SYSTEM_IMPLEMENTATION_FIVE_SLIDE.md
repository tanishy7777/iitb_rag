# Slide 1: Problem and Vision

## Problem
- Operators troubleshoot under noisy, high-pressure conditions.
- Manuals are static; practical fixes live in tribal knowledge.
- Without access control, governance and accountability are weak.

## Vision
Build a self-evolving digital brain that:
- answers with manual-grounded evidence,
- adapts from real repair outcomes,
- enforces role-based access for operator/admin workflows,
- and exposes operational intelligence to management.

---

# Slide 2: System Architecture

## Core Stack
- **UI:** Login + Operator + Admin interfaces
- **API/Service:** auth/RBAC, retrieval, ranking, troubleshooting sessions
- **Storage:** SQLite canonical tables + auth/session/event logs
- **Retrieval:** chunked manual index (BM25)
- **Synthesis:** Ollama llama3 (default) or deterministic fallback
- **Flow engine:** hybrid mode (LLM-assisted proposal + deterministic validation/fallback)

## Data Inputs
- PDF docs: SOP/Policy/Recipe/Manual
- SQL history: machines, complaints, trouble events
- Realtime feeds: new docs, complaints, trouble events, feedback

## Safety Layer
- Confidence scoring and low-evidence guardrail
- Flow schema/transition validation
- Audit logging

---

# Slide 3: Operator Experience (End-to-End)

## Workflow
1. Login as operator/admin
2. Select machine + describe issue
3. Receive grounded diagnosis with citations and confidence
4. Execute interactive troubleshooting nodes
5. Submit fix outcome (thumbs up/down + workaround)
6. System reuses fresh feedback in the next similar case

## UX Features
- Triage quick chips: Power / Hydraulics / Tooling
- Recent machine shortcuts
- Loading indicators for LLM latency
- Persistent troubleshooting sessions (server-side state)
- Flow mode visibility (`llm_assisted` vs fallback reason)

---

# Slide 4: Learning Loop and Realtime RAG

## Realtime Learning Sources
- `equipment_complaint` history
- `trouble_track` actions
- operator feedback workarounds

## What Happens Realtime
- New complaint/trouble event upserts are instantly queryable
- New feedback influences ranking on next query
- New PDF ingestion rebuilds retrieval index immediately

## Guidance Style
- “Manual says X” (citations)
- “Historically worked Y” (traceable source)
- Troubleshooting flow:
  - LLM-assisted when valid
  - deterministic fallback when invalid/unavailable

---

# Slide 5: Outcomes, Status, and Next Steps

## Delivered Outcomes
- Roadmap phases 1-4 implemented in MVP form
- Phase 5 core hardening controls in place (confidence, audit, tests)
- Auth + RBAC implemented
- Admin user management implemented
- Optional local LLM (Ollama llama3) integrated

## KPI-ready Signals Available
- Top breakdown machines
- Unresolved and at-risk queues
- Feedback trend by machine
- Category/month breakdown trends
- Knowledge-gap clusters
- Flow mode/fallback behavior (auditable)

## Next Steps
1. Production data layer (Postgres + scalable retrieval)
2. Enterprise auth hardening (reset policy, SSO, governance controls)
3. Deeper observability (latency/fallback/confidence dashboards)
4. Stronger semantic clustering and citation span verification
