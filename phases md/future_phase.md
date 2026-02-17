• Next phase is production hardening + pilot readiness.

  1. Enterprise Auth Hardening

  - Password reset/rotation policy
  - Account lifecycle controls
  - Optional SSO integration
  - Session security tuning and admin audit reports

  2. Scale the Data/RAG Layer

  - Move from SQLite to Postgres
  - Add hybrid retrieval (BM25 + vector)
  - Background async ingest workers for realtime data growth

  3. Observability + Reliability

  - Metrics dashboard: latency, fallback rates, confidence distribution,
    flow-mode distribution
  - Structured error tracking and alerting
  - Basic load/concurrency validation

  4. Grounding Quality Guardrails

  - Stronger citation-to-answer checks
  - Flow validation telemetry and failure analysis
  - Better semantic clustering for knowledge gaps

  5. Pilot UAT

  - Run defined operator scenarios
  - Measure time-to-diagnose and resolution success
  - Tune ranking/flows from pilot feedback

  If you want, I can convert this into a concrete Day 1-10 execution plan
  with deliverables and exit criteria next.


› Lets do this Password reset/rotation policy, Account lifecycle controls,
  Add hybrid retrieval (BM25 + vector). Create a plan first


• Plan: Security + Lifecycle + Hybrid Retrieval (10 working days)

  ## 1. Scope Lock and Design (Day 1)

  1. Freeze requirements for:

  - Password reset
  - Password rotation policy
  - Account lifecycle controls
  - Hybrid retrieval scoring behavior

  2. Define policy defaults:

  - Password max age (for example 90 days)
  - Reset token expiry (for example 15 minutes)
  - Lockout threshold (for example 5 failed attempts)
  - Roles allowed to manage users

  3. Finalize hybrid ranking formula:

  - final_score = w_bm25 * bm25 + w_vec * cosine + bonuses

  Exit criteria: signed-off policy/config defaults and scoring formula.

  ## 2. Password Reset + Rotation (Days 2-4)

  1. DB/schema additions:

  - password_resets (token hash, user_id, expires_at, used_at)
  - users additions: password_changed_at, must_change_password,
    failed_login_attempts, locked_until

  2. Auth service updates:

  - Request reset token
  - Confirm reset token + set new password
  - Enforce max password age and must_change_password
  - Enforce lockout/backoff on repeated failed login

  3. API endpoints:

  - POST /api/auth/request-reset
  - POST /api/auth/confirm-reset
  - POST /api/auth/change-password

  4. Admin controls:

  - Force password reset
  - Unlock account

  Exit criteria: reset + rotation fully enforced in backend, audited, and
  test-covered.

  ## 3. Account Lifecycle Controls (Days 5-6)

  1. Lifecycle states and transitions:

  - Active
  - Locked (temporary)
  - Disabled (admin)
  - Soft-deleted (optional)

  2. Admin user-management expansion:

  - Disable/enable account
  - Lock/unlock account
  - Force reset/must-change-password
  - Preserve “cannot remove last active admin” safeguard

  3. Audit log events:

  - auth_reset_requested, auth_reset_completed
  - auth_account_locked, auth_account_unlocked
  - auth_account_disabled, auth_password_forced_reset

  Exit criteria: lifecycle transitions work end-to-end in admin UI/API.

  ## 4. Hybrid Retrieval (BM25 + Vector) (Days 7-9)

  1. Vector index pipeline:

  - Generate embeddings for chunks (local embedding model)
  - Store vectors + metadata
  - Rebuild/incremental update on ingest/realtime document add

  2. Query-time hybrid retrieval:

  - BM25 top-k
  - Vector top-k
  - Normalize and fuse with weighted score
  - Dedupe by chunk id

  3. Response observability:

  - Include retrieval breakdown in debug/audit metadata:
      - bm25 rank/score
      - vector score
      - fused score

  4. Config flags:

  - DIGITAL_BRAIN_RETRIEVAL_MODE (bm25|vector|hybrid)
  - Weight knobs and top-k knobs

  Exit criteria: hybrid mode improves relevance on benchmark queries and can
  be toggled safely.

  ## 5. Validation, Docs, and Rollout (Day 10)

  1. Tests:

  - Auth reset/rotation/lifecycle tests
  - Hybrid retrieval unit + smoke tests

  2. Docs:

  - API changes
  - Admin runbook
  - Security policy config
  - Retrieval tuning guide

  3. Migration + rollout:

  - Backfill script for password fields and embeddings
  - Safe fallback to BM25 if vector model/index unavailable

  Exit criteria: all tests pass, docs updated, feature flags allow staged
  rollout.