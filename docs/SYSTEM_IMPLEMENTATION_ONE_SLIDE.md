# Slide 1: Digital Brain - Executive Snapshot

## Vision
A self-evolving industrial troubleshooting platform combining manual-grounded RAG, realtime feedback learning, and role-based access control.

## What Is Live Now
- Auth + RBAC (`operator`, `admin`) with login/session APIs
- End-to-end operator flow: machine selection -> diagnosis -> troubleshooting -> outcome feedback
- Grounded answers with manual citations + historical fixes
- Hybrid troubleshooting flow:
  - LLM-assisted generation when available
  - deterministic validation/fallback with explicit reason
- Realtime updates from new documents, complaints, trouble events, and feedback
- Admin visibility into breakdowns, unresolved/risk issues, knowledge gaps, and user access management
- Optional local LLM synthesis via **Ollama llama3** with deterministic answer fallback

## Architecture (Simplified)
`Login + Operator/Admin UI + CLI` -> `API (Auth/RBAC)` -> `Service (RAG + Hybrid Flow + Learning)` -> `SQLite State + Retrieval Index` -> `Ollama/OpenAI optional`

## Business Value
- Faster diagnosis with evidence-based guidance
- Reduced repeat failures through workaround memory
- Controlled access and auditable actions by role
- Immediate visibility of where manuals/process are failing

## Current Maturity
MVP is operational with RBAC and hybrid flow; next focus is production hardening (scale, enterprise auth, telemetry, stricter grounding).
