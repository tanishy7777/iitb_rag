# Slide 1: Digital Brain - Executive Snapshot

## Vision
A self-evolving industrial troubleshooting platform that combines manual-grounded RAG with realtime field feedback learning.

## What Is Live Now
- End-to-end operator flow: machine selection -> diagnosis -> yes/no troubleshooting -> outcome feedback
- Grounded answers with manual citations + historical fixes
- Realtime updates from new documents, complaints, trouble events, and feedback
- Admin visibility into breakdowns, unresolved issues, risk queue, and knowledge gaps
- Optional local LLM synthesis via **Ollama llama3** with deterministic fallback

## Architecture (Simplified)
`Operator/Admin UI + CLI` -> `API` -> `Service (RAG + Workflow + Learning)` -> `SQLite State + Retrieval Index` -> `Ollama/OpenAI optional`

## Business Value
- Faster diagnosis with evidence-based guidance
- Reduced repeat failures through workaround memory
- Continuous improvement from floor-level feedback
- Immediate visibility of where manuals/process are failing

## Current Maturity
MVP complete and operational; next focus is production hardening (scale, auth, telemetry, stricter grounding).
